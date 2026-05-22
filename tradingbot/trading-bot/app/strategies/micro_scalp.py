import numpy as np
from typing import Optional, List
from app.strategies.base import BaseStrategy
from app.market.models import MarketSignal, Candle, Ticker


class MicroScalpStrategy(BaseStrategy):
    name = "micro_scalp"
    timeframe = "1m"
    min_candles = 15

    async def analyze(self, symbol: str, candles: List[Candle], ticker: Optional[Ticker]) -> Optional[MarketSignal]:
        if len(candles) < self.min_candles:
            return None

        closes = np.array([c.close for c in candles])
        highs = np.array([c.high for c in candles])
        lows = np.array([c.low for c in candles])

        rsi = self._compute_rsi(closes, 7)
        middle, upper, lower = self._compute_bollinger_bands(closes, 10, 2.0)
        atr = self._compute_atr(highs, lows, closes, 7)

        if middle is None or atr == 0:
            return None

        current_price = closes[-1]
        curr_rsi = rsi[-1]

        # SHORT: overbought bounce — price above upper BB, RSI > 68
        if current_price >= upper[-1] and curr_rsi > 68:
            strength = min((curr_rsi - 68) / 30 + 0.3, 1.0)
            return MarketSignal(
                symbol=symbol,
                strategy=self.name,
                direction="short",
                strength=max(strength, 0.3),
                entry_price=current_price,
                stop_loss=current_price + atr * 0.8,
                take_profit=current_price - atr * 1.2,
                timeframe=self.timeframe,
                metadata={"rsi": curr_rsi, "bb_upper": upper[-1]},
            )

        # LONG: oversold bounce — price below lower BB, RSI < 32
        if current_price <= lower[-1] and curr_rsi < 32:
            strength = min((32 - curr_rsi) / 30 + 0.3, 1.0)
            return MarketSignal(
                symbol=symbol,
                strategy=self.name,
                direction="long",
                strength=max(strength, 0.3),
                entry_price=current_price,
                stop_loss=current_price - atr * 0.8,
                take_profit=current_price + atr * 1.2,
                timeframe=self.timeframe,
                metadata={"rsi": curr_rsi, "bb_lower": lower[-1]},
            )

        return None
