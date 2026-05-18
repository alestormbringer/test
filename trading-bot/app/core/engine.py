import asyncio
from datetime import datetime, time
from typing import Dict, List, Optional
from loguru import logger
from app.core.config import settings
from app.core.events import event_bus, Event, EventType
from app.market.data_feed import BinanceDataFeed
from app.market.scanner import MarketScanner
from app.strategies.selector import StrategySelector
from app.risk.manager import RiskManager
from app.paper_trading.engine import PaperTradingEngine
from app.portfolio.manager import PortfolioManager
from app.analytics.engine import AnalyticsEngine
from app.reporting.reporter import DailyReporter
from app.notifications.telegram import TelegramNotifier
from app.dashboard.api import app as dashboard_app, set_trading_engine


class TradingEngine:
    def __init__(self):
        self.data_feed = BinanceDataFeed()
        self.market_scanner = MarketScanner(self.data_feed)
        self.strategy_selector = StrategySelector()
        self.risk_manager = RiskManager()
        self.paper_engine = PaperTradingEngine()
        self.portfolio_manager = PortfolioManager(self.paper_engine)
        self.analytics_engine = AnalyticsEngine()
        self.notifier = TelegramNotifier()
        self.reporter = DailyReporter(self.analytics_engine, self.portfolio_manager, self.paper_engine)

        self._running = False
        self._last_signal_time: Dict[str, datetime] = {}
        self._min_signal_interval_seconds = 60  # throttle per symbol

    async def start(self):
        logger.info("=" * 60)
        logger.info("CRYPTO TRADING BOT STARTING")
        logger.info(f"Mode: {settings.trading_mode.upper()}")
        logger.info(f"Capital: ${settings.initial_capital:.2f}")
        logger.info(f"Symbols: {settings.symbols_list}")
        logger.info("=" * 60)

        self._running = True

        # Register event handlers
        event_bus.subscribe(EventType.POSITION_OPENED, self._on_position_opened)
        event_bus.subscribe(EventType.POSITION_CLOSED, self._on_position_closed)
        event_bus.subscribe(EventType.KILL_SWITCH_TRIGGERED, self._on_kill_switch)

        # Initialize components
        await self.risk_manager.initialize(settings.initial_capital)
        await self.notifier.start()
        set_trading_engine(self)

        # Start data feed
        await self.data_feed.start(settings.symbols_list, ["1m", "5m"])
        self.data_feed.on_ticker(self._on_ticker_update)
        self.data_feed.on_candle(self._on_candle_update)

        # Wait for initial data
        logger.info("Waiting for initial market data (30s)...")
        await asyncio.sleep(30)

        # Run all components concurrently
        await asyncio.gather(
            event_bus.run(),
            self.market_scanner.start(),
            self._trading_loop(),
            self._position_monitor_loop(),
            self._analytics_update_loop(),
            self._daily_report_loop(),
            self._run_dashboard(),
        )

    async def stop(self):
        logger.info("Stopping trading engine...")
        self._running = False
        self.market_scanner.stop()
        event_bus.stop()
        await self.data_feed.stop()
        await self.notifier.stop()
        logger.info("Trading engine stopped")

    async def _run_dashboard(self):
        import uvicorn
        config = uvicorn.Config(
            dashboard_app,
            host=settings.dashboard_host,
            port=settings.dashboard_port,
            log_level="warning",
        )
        server = uvicorn.Server(config)
        await server.serve()

    async def _trading_loop(self):
        while self._running:
            try:
                if self.risk_manager.kill_switch_active:
                    await asyncio.sleep(10)
                    continue

                symbols = settings.symbols_list
                best_symbols = self.market_scanner.get_best_symbols(n=len(symbols))
                if not best_symbols:
                    best_symbols = symbols

                for symbol in best_symbols:
                    await self._process_symbol(symbol)

                await asyncio.sleep(5)

            except Exception as e:
                logger.error(f"Trading loop error: {e}")
                await asyncio.sleep(10)

    async def _process_symbol(self, symbol: str):
        try:
            # Throttle signals per symbol
            last_time = self._last_signal_time.get(symbol)
            if last_time:
                elapsed = (datetime.utcnow() - last_time).total_seconds()
                if elapsed < self._min_signal_interval_seconds:
                    return

            # Don't trade if already have position in this symbol
            existing_positions = [
                p for p in self.paper_engine.positions.values()
                if p.symbol == symbol
            ]
            if existing_positions:
                return

            candles_by_tf = {
                "1m": self.data_feed.get_candles(symbol, "1m"),
                "5m": self.data_feed.get_candles(symbol, "5m"),
            }
            ticker = self.data_feed.get_ticker(symbol)

            if not any(candles_by_tf.values()):
                return

            signals = await self.strategy_selector.get_signals(symbol, candles_by_tf, ticker)

            for signal in signals:
                await self._execute_signal(signal)
                self._last_signal_time[symbol] = datetime.utcnow()

        except Exception as e:
            logger.error(f"Error processing symbol {symbol}: {e}")

    async def _execute_signal(self, signal):
        try:
            position_size_usd = self.risk_manager.calculate_position_size(
                signal.entry_price, signal.stop_loss
            )

            if position_size_usd < 1.0:
                logger.debug(f"Position size too small for {signal.symbol}: ${position_size_usd:.2f}")
                return

            can_trade, reason = await self.risk_manager.can_open_trade(signal.symbol, position_size_usd)
            if not can_trade:
                logger.debug(f"Cannot trade {signal.symbol}: {reason}")
                return

            position = await self.paper_engine.open_position(signal, position_size_usd)
            if position:
                self.risk_manager.register_trade_open(position_size_usd)
                await self.notifier.notify_trade_opened(
                    signal.symbol, signal.direction, signal.entry_price,
                    position_size_usd, signal.strategy
                )

        except Exception as e:
            logger.error(f"Error executing signal for {signal.symbol}: {e}")

    async def _position_monitor_loop(self):
        while self._running:
            try:
                current_prices = {
                    sym: ticker.last
                    for sym, ticker in self.data_feed.tickers.items()
                    if ticker
                }
                await self.paper_engine.monitor_positions(current_prices)
                self.portfolio_manager.update_metrics()
                await asyncio.sleep(2)
            except Exception as e:
                logger.error(f"Position monitor error: {e}")
                await asyncio.sleep(5)

    async def _analytics_update_loop(self):
        while self._running:
            try:
                self.analytics_engine.update(self.paper_engine.closed_positions)
                await asyncio.sleep(60)
            except Exception as e:
                logger.error(f"Analytics update error: {e}")
                await asyncio.sleep(60)

    async def _daily_report_loop(self):
        while self._running:
            try:
                now = datetime.utcnow()
                # Run report at 23:59 UTC
                if now.hour == 23 and now.minute == 59:
                    report = await self.reporter.generate_daily_report()
                    await self.notifier.notify_daily_report(report)
                    await asyncio.sleep(61)
                else:
                    await asyncio.sleep(30)
            except Exception as e:
                logger.error(f"Daily report error: {e}")
                await asyncio.sleep(60)

    async def _on_ticker_update(self, ticker):
        self.paper_engine.update_price(ticker.symbol, ticker.last)

    async def _on_candle_update(self, candle):
        pass

    async def _on_position_opened(self, event: Event):
        data = event.data
        logger.info(f"Position opened event: {data['symbol']} {data['direction']} @ {data['entry_price']}")

    async def _on_position_closed(self, event: Event):
        data = event.data
        pnl = data.get("pnl", 0)
        # Update risk manager
        # Find position size from closed positions
        closed = [p for p in self.paper_engine.closed_positions if p.id == data.get("id")]
        size_usd = closed[-1].size_usd if closed else 0.0
        self.risk_manager.register_trade_close(size_usd, pnl)
        # Update strategy performance
        if closed:
            self.strategy_selector.update_performance(closed[-1].strategy, pnl)
        await self.notifier.notify_trade_closed(data["symbol"], pnl, data.get("reason", ""))

    async def _on_kill_switch(self, event: Event):
        reason = event.data.get("reason", "Unknown")
        logger.critical(f"Kill switch event received: {reason}")
        await self.notifier.notify_kill_switch(reason)
        # Close all positions
        current_prices = {
            sym: ticker.last
            for sym, ticker in self.data_feed.tickers.items()
            if ticker
        }
        for pos_id in list(self.paper_engine.positions.keys()):
            pos = self.paper_engine.positions.get(pos_id)
            if pos:
                price = current_prices.get(pos.symbol, pos.entry_price)
                await self.paper_engine.close_position(pos_id, price, "kill_switch")
