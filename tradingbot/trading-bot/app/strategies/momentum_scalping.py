import numpy as np
from typing import Optional, List
from app.strategies.base import BaseStrategy
from app.market.models import MarketSignal, Candle, Ticker


class MomentumScalpingStrategy(BaseStrategy):
    name = "momentum_scalping"
    timeframe = "1m"
    min_candles = 30

    async def analyze(self, symbol: str, candles: List[Candle], ticker: Optional[Ticker]) -> Optional[MarketSignal]:
        if len(candles) < self.min_candles:
            return None

        closes = np.array([c.close for c in candles])
        highs = np.array([c.high for c in candles])
        lows = np.array([c.low for c in candles])
        volumes = np.array([c.volume for c in candles])

        rsi = self._compute_rsi(closes, 7)
        macd_line, signal_line, histogram = self._compute_macd(closes, 6, 13, 5)
        atr = self._compute_atr(highs, lows, closes, 7)

        if macd_line is None:
            return None

        current_price = closes[-1]
        curr_rsi = rsi[-1]
        curr_macd = macd_line[-1]
        prev_macd = macd_line[-2]
        curr_signal = signal_line[-1]
        prev_signal = signal_line[-2]
        curr_hist = histogram[-1]
        prev_hist = histogram[-2]

        # Volume confirmation
        recent_vol = np.mean(volumes[-3:])
        avg_vol = np.mean(volumes[-20:])
        vol_ok = recent_vol > avg_vol * 1.2

        # Long momentum signal
        if (prev_macd < prev_signal and curr_macd > curr_signal and
                45 < curr_rsi < 70 and curr_hist > 0 and vol_ok):
            return MarketSignal(
                symbol=symbol,
                strategy=self.name,
                direction="long",
                strength=min(abs(curr_hist) / (atr + 1e-8), 1.0),
                entry_price=current_price,
                stop_loss=current_price - atr * 1.2,
                take_profit=current_price + atr * 1.5,
                timeframe=self.timeframe,
                metadata={"rsi": curr_rsi, "macd": curr_macd, "histogram": curr_hist},
            )

        # Short momentum signal
        if (prev_macd > prev_signal and curr_macd < curr_signal and
                30 < curr_rsi < 55 and curr_hist < 0 and vol_ok):
            return MarketSignal(
                symbol=symbol,
                strategy=self.name,
                direction="short",
                strength=min(abs(curr_hist) / (atr + 1e-8), 1.0),
                entry_price=current_price,
                stop_loss=current_price + atr * 1.2,
                take_profit=current_price - atr * 1.5,
                timeframe=self.timeframe,
                metadata={"rsi": curr_rsi, "macd": curr_macd, "histogram": curr_hist},
            )

        return None
