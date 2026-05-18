import numpy as np
from typing import Optional, List
from app.strategies.base import BaseStrategy
from app.market.models import MarketSignal, Candle, Ticker
from app.core.config import settings


class MeanReversionStrategy(BaseStrategy):
    name = "mean_reversion"
    timeframe = "5m"
    min_candles = 60

    async def analyze(self, symbol: str, candles: List[Candle], ticker: Optional[Ticker]) -> Optional[MarketSignal]:
        if len(candles) < self.min_candles:
            return None

        closes = np.array([c.close for c in candles])
        highs = np.array([c.high for c in candles])
        lows = np.array([c.low for c in candles])

        middle, upper, lower = self._compute_bollinger_bands(closes, 20, 2.0)
        if middle is None:
            return None

        rsi = self._compute_rsi(closes, 14)
        atr = self._compute_atr(highs, lows, closes, 14)

        current_price = closes[-1]
        curr_upper = upper[-1]
        curr_lower = lower[-1]
        curr_middle = middle[-1]
        curr_rsi = rsi[-1]

        # Price below lower band + oversold RSI -> long reversal
        if current_price < curr_lower and curr_rsi < 35:
            strength = min((curr_lower - current_price) / atr, 1.0) if atr > 0 else 0.5
            return MarketSignal(
                symbol=symbol,
                strategy=self.name,
                direction="long",
                strength=max(strength, 0.4),
                entry_price=current_price,
                stop_loss=current_price - atr * 1.0,
                take_profit=curr_middle,
                timeframe=self.timeframe,
                metadata={"bb_lower": curr_lower, "bb_middle": curr_middle, "rsi": curr_rsi},
            )

        # Price above upper band + overbought RSI -> short reversal
        if current_price > curr_upper and curr_rsi > 65:
            strength = min((current_price - curr_upper) / atr, 1.0) if atr > 0 else 0.5
            return MarketSignal(
                symbol=symbol,
                strategy=self.name,
                direction="short",
                strength=max(strength, 0.4),
                entry_price=current_price,
                stop_loss=current_price + atr * 1.0,
                take_profit=curr_middle,
                timeframe=self.timeframe,
                metadata={"bb_upper": curr_upper, "bb_middle": curr_middle, "rsi": curr_rsi},
            )

        return None
