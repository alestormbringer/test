import asyncio
from datetime import datetime, date
from typing import Dict, List, Optional
from loguru import logger
from app.core.config import settings
from app.core.events import event_bus, Event, EventType
from app.market.data_feed import BinanceDataFeed
from app.market.scanner import MarketScanner
from app.market.regime_detector import RegimeDetector, BULLISH, BEARISH
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
        self.regime_detector = RegimeDetector(self.data_feed)
        self.strategy_selector = StrategySelector()
        self.risk_manager = RiskManager()
        self.paper_engine = PaperTradingEngine()
        self.portfolio_manager = PortfolioManager(self.paper_engine)
        self.analytics_engine = AnalyticsEngine()
        self.notifier = TelegramNotifier()
        self.reporter = DailyReporter(self.analytics_engine, self.portfolio_manager, self.paper_engine)

        self._running = False
        self._last_signal_time: Dict[str, datetime] = {}
        self._min_signal_interval_seconds = 10

        self._daily_losses = 0
        self._last_loss_reset: Optional[date] = None

    async def start(self):
        logger.info("=" * 60)
        logger.info("CRYPTO TRADING BOT STARTING")
        logger.info(f"Mode: {settings.trading_mode.upper()}")
        logger.info(f"Capital: ${settings.initial_capital:.2f}")
        logger.info(f"Symbols: {settings.symbols_list}")
        logger.info("=" * 60)

        self._running = True

        event_bus.subscribe(EventType.POSITION_OPENED, self._on_position_opened)
        event_bus.subscribe(EventType.POSITION_CLOSED, self._on_position_closed)
        event_bus.subscribe(EventType.KILL_SWITCH_TRIGGERED, self._on_kill_switch)
        event_bus.subscribe(EventType.REGIME_CHANGED, self._on_regime_changed)

        await self.risk_manager.initialize(settings.initial_capital)
        await self.notifier.start()
        set_trading_engine(self)

        await self.data_feed.start(settings.symbols_list, ["1m", "5m"])
        self.data_feed.on_ticker(self._on_ticker_update)
        self.data_feed.on_candle(self._on_candle_update)

        logger.info("Waiting for initial market data (30s)...")
        await asyncio.sleep(30)

        await asyncio.gather(
            event_bus.run(),
            self.market_scanner.start(),
            self.regime_detector.start(),
            self._trading_loop(),
            self._position_monitor_loop(),
            self._analytics_update_loop(),
            self._daily_report_loop(),
            self._status_loop(),
            self._run_dashboard(),
        )

    async def stop(self):
        logger.info("Stopping trading engine...")
        self._running = False
        self.market_scanner.stop()
        self.regime_detector.stop()
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

    def _check_daily_loss_reset(self):
        today = date.today()
        if self._last_loss_reset != today:
            self._daily_losses = 0
            self._last_loss_reset = today

    @property
    def _max_daily_losses_hit(self) -> bool:
        self._check_daily_loss_reset()
        return self._daily_losses >= settings.max_daily_losses

    async def _trading_loop(self):
        while self._running:
            try:
                if self.risk_manager.kill_switch_active:
                    await asyncio.sleep(10)
                    continue

                if self._max_daily_losses_hit:
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
            last_time = self._last_signal_time.get(symbol)
            if last_time:
                elapsed = (datetime.utcnow() - last_time).total_seconds()
                if elapsed < self._min_signal_interval_seconds:
                    return

            candles_by_tf = {
                "1m": self.data_feed.get_candles(symbol, "1m"),
                "5m": self.data_feed.get_candles(symbol, "5m"),
            }
            ticker = self.data_feed.get_ticker(symbol)

            if not any(candles_by_tf.values()):
                return

            signals = await self.strategy_selector.get_signals(symbol, candles_by_tf, ticker, self.regime_detector.current_regime)

            for signal in signals:
                await self._execute_signal(signal)
                self._last_signal_time[symbol] = datetime.utcnow()

        except Exception as e:
            logger.error(f"Error processing symbol {symbol}: {e}")

    async def _execute_signal(self, signal):
        try:
            regime = self.regime_detector.current_regime
            is_micro_scalp = signal.strategy == "micro_scalp"
            if regime == BEARISH and signal.direction == "long" and not is_micro_scalp:
                logger.debug(f"Skipping long signal for {signal.symbol} — regime BEARISH")
                return
            if regime == BULLISH and signal.direction == "short" and not is_micro_scalp:
                logger.debug(f"Skipping short signal for {signal.symbol} — regime BULLISH")
                return

            position_size_usd = self.risk_manager.calculate_position_size(
                signal.entry_price, signal.stop_loss
            )
            perf_multiplier = self.strategy_selector.get_performance_multiplier(signal.strategy)
            position_size_usd *= perf_multiplier

            if position_size_usd < 0.10:
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
                    position_size_usd, signal.strategy,
                    regime=self.regime_detector.current_regime,
                )

        except Exception as e:
            logger.error(f"Error executing signal for {signal.symbol}: {e}")

    async def _close_all_positions(self, reason: str):
        current_prices = {
            sym: ticker.last
            for sym, ticker in self.data_feed.tickers.items()
            if ticker
        }
        for pos_id in list(self.paper_engine.positions.keys()):
            pos = self.paper_engine.positions.get(pos_id)
            if pos:
                price = current_prices.get(pos.symbol, pos.entry_price)
                await self.paper_engine.close_position(pos_id, price, reason)

    async def _close_positions_by_direction(self, direction: str, reason: str):
        current_prices = {
            sym: ticker.last
            for sym, ticker in self.data_feed.tickers.items()
            if ticker
        }
        for pos_id in list(self.paper_engine.positions.keys()):
            pos = self.paper_engine.positions.get(pos_id)
            if pos and pos.direction == direction:
                price = current_prices.get(pos.symbol, pos.entry_price)
                await self.paper_engine.close_position(pos_id, price, reason)

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
                if now.hour == 23 and now.minute == 59:
                    report = await self.reporter.generate_daily_report()
                    await self.notifier.notify_daily_report(report)
                    await asyncio.sleep(61)
                else:
                    await asyncio.sleep(30)
            except Exception as e:
                logger.error(f"Daily report error: {e}")
                await asyncio.sleep(60)

    async def _status_loop(self):
        """Send regime + daily losses status to Telegram every 20 minutes."""
        await asyncio.sleep(120)  # wait 2 min after startup before first status
        while self._running:
            try:
                self._check_daily_loss_reset()
                await self.notifier.notify_status(
                    self.regime_detector.current_regime,
                    self._daily_losses,
                    settings.max_daily_losses,
                )
                await asyncio.sleep(1200)  # 20 minutes
            except Exception as e:
                logger.error(f"Status loop error: {e}")
                await asyncio.sleep(60)

    async def _on_ticker_update(self, ticker):
        self.paper_engine.update_price(ticker.symbol, ticker.last)

    async def _on_candle_update(self, candle):
        pass

    async def _on_position_opened(self, event: Event):
        data = event.data
        logger.info(f"Position opened: {data['symbol']} {data['direction']} @ {data['entry_price']}")

    async def _on_position_closed(self, event: Event):
        data = event.data
        pnl = data.get("pnl", 0)

        closed = [p for p in self.paper_engine.closed_positions if p.id == data.get("id")]
        size_usd = closed[-1].size_usd if closed else 0.0
        self.risk_manager.register_trade_close(size_usd, pnl)

        if closed:
            self.strategy_selector.update_performance(closed[-1].strategy, pnl)

        if pnl < 0:
            self._check_daily_loss_reset()
            self._daily_losses += 1
            if self._max_daily_losses_hit:
                logger.warning(f"Daily loss limit reached: {self._daily_losses}/{settings.max_daily_losses}")

        entry = data.get("entry_price", 0)
        exit_price = data.get("exit_price", 0)
        pnl_pct = ((exit_price - entry) / entry * 100) if entry > 0 else 0
        direction = closed[-1].direction if closed else "long"

        await self.notifier.notify_trade_closed(
            data["symbol"], direction, entry, exit_price,
            pnl, pnl_pct, data.get("reason", ""),
            regime=self.regime_detector.current_regime,
        )

    async def _on_regime_changed(self, event: Event):
        regime = event.data.get("regime", BEARISH)
        self._check_daily_loss_reset()
        logger.info(f"Regime event received: {regime}")

        await self.notifier.notify_regime_change(
            regime, self._daily_losses, settings.max_daily_losses
        )

        if regime == BEARISH:
            logger.info("Regime BEARISH — closing long positions")
            await self._close_positions_by_direction("long", "regime_change_exit")
        elif regime == BULLISH:
            logger.info("Regime BULLISH — closing short positions")
            await self._close_positions_by_direction("short", "regime_change_exit")

    async def _on_kill_switch(self, event: Event):
        reason = event.data.get("reason", "Unknown")
        logger.critical(f"Kill switch event received: {reason}")
        await self.notifier.notify_kill_switch(reason)
        await self._close_all_positions("kill_switch")
