import asyncio
import aiohttp
import json
from typing import Dict, List, Optional, Callable
from datetime import datetime
from loguru import logger
from app.market.models import Candle, Ticker, OrderBook
from app.core.config import settings

BINANCE_REST_BASE = "https://api.binance.com"
BINANCE_WS_BASE = "wss://stream.binance.com:9443"


class BinanceDataFeed:
    def __init__(self):
        self.tickers: Dict[str, Ticker] = {}
        self.candles: Dict[str, Dict[str, List[Candle]]] = {}  # symbol -> timeframe -> candles
        self.orderbooks: Dict[str, OrderBook] = {}
        self._ticker_callbacks: List[Callable] = []
        self._candle_callbacks: List[Callable] = []
        self._ws_task: Optional[asyncio.Task] = None
        self._running = False
        self._session: Optional[aiohttp.ClientSession] = None

    def on_ticker(self, callback: Callable):
        self._ticker_callbacks.append(callback)

    def on_candle(self, callback: Callable):
        self._candle_callbacks.append(callback)

    async def start(self, symbols: List[str], timeframes: List[str] = ["1m", "5m"]):
        self._running = True
        self._session = aiohttp.ClientSession()

        # Always include BTCUSDT 15m for regime detection
        all_symbols = list(dict.fromkeys(["BTCUSDT"] + symbols))
        all_timeframes = list(dict.fromkeys(timeframes + ["15m"]))

        for symbol in all_symbols:
            for tf in all_timeframes:
                await self._load_historical_candles(symbol, tf)

        self._ws_task = asyncio.create_task(
            self._run_websocket(all_symbols, all_timeframes)
        )
        logger.info(f"BinanceDataFeed started for {symbols}")

    async def stop(self):
        self._running = False
        if self._ws_task:
            self._ws_task.cancel()
        if self._session:
            await self._session.close()

    async def _load_historical_candles(self, symbol: str, timeframe: str, limit: int = 200):
        try:
            interval_map = {"1m": "1m", "5m": "5m", "15m": "15m", "1h": "1h"}
            interval = interval_map.get(timeframe, "1m")
            url = f"{BINANCE_REST_BASE}/api/v3/klines"
            params = {"symbol": symbol, "interval": interval, "limit": limit}

            async with self._session.get(url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    candles = []
                    for k in data:
                        candles.append(Candle(
                            symbol=symbol,
                            timeframe=timeframe,
                            open_time=datetime.utcfromtimestamp(k[0] / 1000),
                            open=float(k[1]),
                            high=float(k[2]),
                            low=float(k[3]),
                            close=float(k[4]),
                            volume=float(k[5]),
                            close_time=datetime.utcfromtimestamp(k[6] / 1000),
                            is_closed=True,
                        ))
                    if symbol not in self.candles:
                        self.candles[symbol] = {}
                    self.candles[symbol][timeframe] = candles
                    logger.debug(f"Loaded {len(candles)} {timeframe} candles for {symbol}")
                else:
                    logger.warning(f"Failed to load candles for {symbol} {timeframe}: {resp.status}")
        except Exception as e:
            logger.error(f"Error loading historical candles for {symbol}: {e}")

    async def _run_websocket(self, symbols: List[str], timeframes: List[str]):
        import websockets

        streams = []
        for sym in symbols:
            streams.append(f"{sym.lower()}@ticker")
            for tf in timeframes:
                streams.append(f"{sym.lower()}@kline_{tf}")

        stream_path = "/".join(streams)
        url = f"{BINANCE_WS_BASE}/stream?streams={stream_path}"

        while self._running:
            try:
                async with websockets.connect(url, ping_interval=20, ping_timeout=10) as ws:
                    logger.info("WebSocket connected to Binance")
                    async for message in ws:
                        if not self._running:
                            break
                        await self._handle_ws_message(json.loads(message))
            except Exception as e:
                if self._running:
                    logger.warning(f"WebSocket disconnected: {e}. Reconnecting in 5s...")
                    await asyncio.sleep(5)

    async def _handle_ws_message(self, msg: dict):
        try:
            data = msg.get("data", msg)
            stream = msg.get("stream", "")

            if "@ticker" in stream:
                await self._handle_ticker(data)
            elif "@kline" in stream:
                await self._handle_kline(data)
        except Exception as e:
            logger.error(f"Error handling WS message: {e}")

    async def _handle_ticker(self, data: dict):
        try:
            symbol = data.get("s", "")
            ticker = Ticker(
                symbol=symbol,
                bid=float(data.get("b", 0)),
                ask=float(data.get("a", 0)),
                last=float(data.get("c", 0)),
                volume_24h=float(data.get("v", 0)),
                price_change_pct=float(data.get("P", 0)),
            )
            self.tickers[symbol] = ticker

            for cb in self._ticker_callbacks:
                try:
                    if asyncio.iscoroutinefunction(cb):
                        await cb(ticker)
                    else:
                        cb(ticker)
                except Exception as e:
                    logger.error(f"Ticker callback error: {e}")
        except Exception as e:
            logger.error(f"Error handling ticker: {e}")

    async def _handle_kline(self, data: dict):
        try:
            k = data.get("k", {})
            symbol = k.get("s", "")
            timeframe = k.get("i", "1m")

            candle = Candle(
                symbol=symbol,
                timeframe=timeframe,
                open_time=datetime.utcfromtimestamp(k["t"] / 1000),
                open=float(k["o"]),
                high=float(k["h"]),
                low=float(k["l"]),
                close=float(k["c"]),
                volume=float(k["v"]),
                close_time=datetime.utcfromtimestamp(k["T"] / 1000),
                is_closed=k.get("x", False),
            )

            if symbol not in self.candles:
                self.candles[symbol] = {}
            if timeframe not in self.candles[symbol]:
                self.candles[symbol][timeframe] = []

            candles = self.candles[symbol][timeframe]
            if candle.is_closed:
                if candles and candles[-1].open_time == candle.open_time:
                    candles[-1] = candle
                else:
                    candles.append(candle)
                    if len(candles) > 500:
                        candles.pop(0)

                for cb in self._candle_callbacks:
                    try:
                        if asyncio.iscoroutinefunction(cb):
                            await cb(candle)
                        else:
                            cb(candle)
                    except Exception as e:
                        logger.error(f"Candle callback error: {e}")
        except Exception as e:
            logger.error(f"Error handling kline: {e}")

    def get_candles(self, symbol: str, timeframe: str) -> List[Candle]:
        return self.candles.get(symbol, {}).get(timeframe, [])

    def get_ticker(self, symbol: str) -> Optional[Ticker]:
        return self.tickers.get(symbol)

    async def fetch_ticker_rest(self, symbol: str) -> Optional[Ticker]:
        try:
            url = f"{BINANCE_REST_BASE}/api/v3/ticker/bookTicker"
            params = {"symbol": symbol}
            async with self._session.get(url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()

                    url2 = f"{BINANCE_REST_BASE}/api/v3/ticker/24hr"
                    async with self._session.get(url2, params=params) as resp2:
                        data2 = await resp2.json()

                    return Ticker(
                        symbol=symbol,
                        bid=float(data.get("bidPrice", 0)),
                        ask=float(data.get("askPrice", 0)),
                        last=float(data2.get("lastPrice", 0)),
                        volume_24h=float(data2.get("volume", 0)),
                        price_change_pct=float(data2.get("priceChangePercent", 0)),
                    )
        except Exception as e:
            logger.error(f"REST ticker fetch error for {symbol}: {e}")
        return None
