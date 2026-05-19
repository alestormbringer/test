import asyncio
import numpy as np
from loguru import logger
from app.market.data_feed import BinanceDataFeed
from app.core.events import event_bus, Event, EventType

BULLISH = "BULLISH"
BEARISH = "BEARISH"
REGIME_SYMBOL = "BTCUSDT"
REGIME_TIMEFRAME = "15m"


class RegimeDetector:
    def __init__(self, data_feed: BinanceDataFeed):
        self.data_feed = data_feed
        self.current_regime: str = BEARISH  # start conservative
        self._running = False

    async def start(self):
        self._running = True
        while self._running:
            try:
                await self._detect_and_broadcast()
                await asyncio.sleep(60)
            except Exception as e:
                logger.error(f"RegimeDetector error: {e}")
                await asyncio.sleep(10)

    def stop(self):
        self._running = False

    async def _detect_and_broadcast(self):
        candles = self.data_feed.get_candles(REGIME_SYMBOL, REGIME_TIMEFRAME)
        if len(candles) < 55:
            return

        closes = np.array([c.close for c in candles[-100:]])
        regime = self._compute_regime(closes)

        if regime != self.current_regime:
            previous = self.current_regime
            self.current_regime = regime
            logger.info(f"Market regime changed: {previous} → {regime}")
            await event_bus.publish(Event(
                type=EventType.REGIME_CHANGED,
                data={"regime": regime, "previous": previous},
                source="regime_detector",
            ))

    def _compute_regime(self, closes: np.ndarray) -> str:
        ema20 = self._ema(closes, 20)
        ema50 = self._ema(closes, 50)
        rsi = self._rsi(closes, 14)

        bullish_ema = ema20[-1] > ema50[-1]
        bullish_rsi = rsi[-1] > 50

        logger.info(f"Regime check — EMA20={ema20[-1]:.4f} EMA50={ema50[-1]:.4f} RSI={rsi[-1]:.1f} bullish_ema={bullish_ema} bullish_rsi={bullish_rsi}")
        if bullish_ema and bullish_rsi:
            return BULLISH
        elif not bullish_ema and not bullish_rsi:
            return BEARISH
        # Mixed signals — keep current regime to avoid flip-flopping
        return self.current_regime

    def _ema(self, closes: np.ndarray, period: int) -> np.ndarray:
        ema = np.zeros_like(closes)
        ema[period - 1] = np.mean(closes[:period])
        k = 2 / (period + 1)
        for i in range(period, len(closes)):
            ema[i] = closes[i] * k + ema[i - 1] * (1 - k)
        return ema

    def _rsi(self, closes: np.ndarray, period: int = 14) -> np.ndarray:
        deltas = np.diff(closes)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        avg_gain = np.zeros_like(closes)
        avg_loss = np.zeros_like(closes)

        if len(gains) < period:
            return np.full_like(closes, 50.0)

        avg_gain[period] = np.mean(gains[:period])
        avg_loss[period] = np.mean(losses[:period])

        for i in range(period + 1, len(closes)):
            avg_gain[i] = (avg_gain[i - 1] * (period - 1) + gains[i - 1]) / period
            avg_loss[i] = (avg_loss[i - 1] * (period - 1) + losses[i - 1]) / period

        rs = np.where(avg_loss > 0, avg_gain / avg_loss, 100)
        return 100 - (100 / (1 + rs))
