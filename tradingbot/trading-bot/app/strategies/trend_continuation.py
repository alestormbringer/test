import numpy as np
from typing import Optional, List
from app.strategies.base import BaseStrategy
from app.market.models import MarketSignal, Candle, Ticker


class TrendContinuationStrategy(BaseStrategy):
    name = "trend_continuation"
    timeframe = "5m"
    min_candles = 60

    async def analyze(self, symbol: str, candles: List[Candle], ticker: Optional[Ticker]) -> Optional[MarketSignal]:
        if len(candles) < self.min_candles:
            return None

        closes = np.array([c.close for c in candles])
        highs = np.array([c.high for c in candles])
        lows = np.array([c.low for c in candles])

        ema20 = self._compute_ema(closes, 20)
        ema50 = self._compute_ema(closes, 50)
        rsi = self._compute_rsi(closes, 14)
        atr = self._compute_atr(highs, lows, closes, 14)

        if atr == 0:
            return None

        current_price = closes[-1]
        curr_ema20 = ema20[-1]
        curr_ema50 = ema50[-1]
        curr_rsi = rsi[-1]

        # SHORT continuation: already in downtrend, RSI recovered from oversold
        if (curr_ema20 < curr_ema50
                and current_price < curr_ema50
                and 35 < curr_rsi < 58):
            trend_strength = (curr_ema50 - curr_ema20) / curr_ema50
            strength = min(trend_strength * 50 + 0.3, 1.0)
            return MarketSignal(
                symbol=symbol,
                strategy=self.name,
                direction="short",
                strength=max(strength, 0.3),
                entry_price=current_price,
                stop_loss=current_price + atr * 1.5,
                take_profit=current_price - atr * 2.0,
                timeframe=self.timeframe,
                metadata={"ema20": curr_ema20, "ema50": curr_ema50, "rsi": curr_rsi},
            )

        # LONG continuation: already in uptrend, RSI pulled back from overbought
        if (curr_ema20 > curr_ema50
                and current_price > curr_ema50
                and 42 < curr_rsi < 65):
            trend_strength = (curr_ema20 - curr_ema50) / curr_ema50
            strength = min(trend_strength * 50 + 0.3, 1.0)
            return MarketSignal(
                symbol=symbol,
                strategy=self.name,
                direction="long",
                strength=max(strength, 0.3),
                entry_price=current_price,
                stop_loss=current_price - atr * 1.5,
                take_profit=current_price + atr * 2.0,
                timeframe=self.timeframe,
                metadata={"ema20": curr_ema20, "ema50": curr_ema50, "rsi": curr_rsi},
            )

        return None
