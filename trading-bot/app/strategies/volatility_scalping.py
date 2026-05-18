import numpy as np
from typing import Optional, List
from app.strategies.base import BaseStrategy
from app.market.models import MarketSignal, Candle, Ticker


class VolatilityScalpingStrategy(BaseStrategy):
    name = "volatility_scalping"
    timeframe = "1m"
    min_candles = 30

    async def analyze(self, symbol: str, candles: List[Candle], ticker: Optional[Ticker]) -> Optional[MarketSignal]:
        if len(candles) < self.min_candles:
            return None

        closes = np.array([c.close for c in candles])
        highs = np.array([c.high for c in candles])
        lows = np.array([c.low for c in candles])

        atr_short = self._compute_atr(highs, lows, closes, 5)
        atr_long = self._compute_atr(highs, lows, closes, 20)
        rsi = self._compute_rsi(closes, 9)
        middle, upper, lower = self._compute_bollinger_bands(closes, 10, 1.5)

        if middle is None or atr_long == 0:
            return None

        current_price = closes[-1]
        curr_rsi = rsi[-1]
        volatility_ratio = atr_short / atr_long if atr_long > 0 else 1.0

        # High volatility squeeze then breakout
        if volatility_ratio > 1.3:
            bb_width = (upper[-1] - lower[-1]) / middle[-1]

            if current_price > upper[-1] and curr_rsi > 50:
                return MarketSignal(
                    symbol=symbol,
                    strategy=self.name,
                    direction="long",
                    strength=min(volatility_ratio - 1.0, 1.0),
                    entry_price=current_price,
                    stop_loss=current_price - atr_short * 1.5,
                    take_profit=current_price + atr_short * 2.0,
                    timeframe=self.timeframe,
                    metadata={"atr_ratio": volatility_ratio, "bb_width": bb_width, "rsi": curr_rsi},
                )

            if current_price < lower[-1] and curr_rsi < 50:
                return MarketSignal(
                    symbol=symbol,
                    strategy=self.name,
                    direction="short",
                    strength=min(volatility_ratio - 1.0, 1.0),
                    entry_price=current_price,
                    stop_loss=current_price + atr_short * 1.5,
                    take_profit=current_price - atr_short * 2.0,
                    timeframe=self.timeframe,
                    metadata={"atr_ratio": volatility_ratio, "bb_width": bb_width, "rsi": curr_rsi},
                )

        return None
