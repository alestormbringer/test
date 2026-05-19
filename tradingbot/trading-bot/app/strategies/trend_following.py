import numpy as np
from typing import Optional, List
from app.strategies.base import BaseStrategy
from app.market.models import MarketSignal, Candle, Ticker
from app.core.config import settings


class TrendFollowingStrategy(BaseStrategy):
    name = "trend_following"
    timeframe = "5m"
    min_candles = 100

    async def analyze(self, symbol: str, candles: List[Candle], ticker: Optional[Ticker]) -> Optional[MarketSignal]:
        if len(candles) < self.min_candles:
            return None

        closes = np.array([c.close for c in candles])
        highs = np.array([c.high for c in candles])
        lows = np.array([c.low for c in candles])

        ema_20 = self._compute_ema(closes, 20)
        ema_50 = self._compute_ema(closes, 50)
        rsi = self._compute_rsi(closes, 14)
        atr = self._compute_atr(highs, lows, closes, 14)

        current_price = closes[-1]
        current_ema20 = ema_20[-1]
        current_ema50 = ema_50[-1]
        current_rsi = rsi[-1]
        prev_ema20 = ema_20[-2]
        prev_ema50 = ema_50[-2]

        # Bullish crossover
        if (prev_ema20 <= prev_ema50 and current_ema20 > current_ema50 and
                40 < current_rsi < 70 and current_price > current_ema20):
            strength = min((current_ema20 - current_ema50) / current_ema50 * 100, 1.0)
            return MarketSignal(
                symbol=symbol,
                strategy=self.name,
                direction="long",
                strength=max(strength, 0.3),
                entry_price=current_price,
                stop_loss=current_price - atr * 1.5,
                take_profit=current_price + atr * 2.0,
                timeframe=self.timeframe,
                metadata={"ema20": current_ema20, "ema50": current_ema50, "rsi": current_rsi},
            )

        # Bearish crossover
        if (prev_ema20 >= prev_ema50 and current_ema20 < current_ema50 and
                30 < current_rsi < 60 and current_price < current_ema20):
            strength = min((current_ema50 - current_ema20) / current_ema50 * 100, 1.0)
            return MarketSignal(
                symbol=symbol,
                strategy=self.name,
                direction="short",
                strength=max(strength, 0.3),
                entry_price=current_price,
                stop_loss=current_price + atr * 1.5,
                take_profit=current_price - atr * 2.0,
                timeframe=self.timeframe,
                metadata={"ema20": current_ema20, "ema50": current_ema50, "rsi": current_rsi},
            )

        return None
