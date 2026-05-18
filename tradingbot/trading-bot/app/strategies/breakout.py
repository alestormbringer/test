import numpy as np
from typing import Optional, List
from app.strategies.base import BaseStrategy
from app.market.models import MarketSignal, Candle, Ticker


class BreakoutStrategy(BaseStrategy):
    name = "breakout"
    timeframe = "5m"
    min_candles = 50
    lookback = 20

    async def analyze(self, symbol: str, candles: List[Candle], ticker: Optional[Ticker]) -> Optional[MarketSignal]:
        if len(candles) < self.min_candles:
            return None

        closes = np.array([c.close for c in candles])
        highs = np.array([c.high for c in candles])
        lows = np.array([c.low for c in candles])
        volumes = np.array([c.volume for c in candles])

        atr = self._compute_atr(highs, lows, closes, 14)

        lookback_highs = highs[-self.lookback-1:-1]
        lookback_lows = lows[-self.lookback-1:-1]
        resistance = float(np.max(lookback_highs))
        support = float(np.min(lookback_lows))

        current_price = closes[-1]
        current_volume = volumes[-1]
        avg_volume = np.mean(volumes[-self.lookback:])
        volume_surge = current_volume > avg_volume * 1.5

        # Bullish breakout
        if current_price > resistance and volume_surge:
            strength = min((current_price - resistance) / atr, 1.0) if atr > 0 else 0.5
            return MarketSignal(
                symbol=symbol,
                strategy=self.name,
                direction="long",
                strength=max(strength, 0.5),
                entry_price=current_price,
                stop_loss=resistance - atr * 0.5,
                take_profit=current_price + atr * 2.0,
                timeframe=self.timeframe,
                metadata={"resistance": resistance, "support": support, "volume_surge": volume_surge},
            )

        # Bearish breakout
        if current_price < support and volume_surge:
            strength = min((support - current_price) / atr, 1.0) if atr > 0 else 0.5
            return MarketSignal(
                symbol=symbol,
                strategy=self.name,
                direction="short",
                strength=max(strength, 0.5),
                entry_price=current_price,
                stop_loss=support + atr * 0.5,
                take_profit=current_price - atr * 2.0,
                timeframe=self.timeframe,
                metadata={"resistance": resistance, "support": support, "volume_surge": volume_surge},
            )

        return None
