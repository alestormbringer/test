from abc import ABC, abstractmethod
from typing import Optional, List
from app.market.models import MarketSignal, Candle, Ticker
import numpy as np


class BaseStrategy(ABC):
    name: str = "base"
    timeframe: str = "5m"
    min_candles: int = 50

    @abstractmethod
    async def analyze(self, symbol: str, candles: List[Candle], ticker: Optional[Ticker]) -> Optional[MarketSignal]:
        pass

    def _compute_rsi(self, closes: np.ndarray, period: int = 14) -> np.ndarray:
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
            avg_gain[i] = (avg_gain[i-1] * (period-1) + gains[i-1]) / period
            avg_loss[i] = (avg_loss[i-1] * (period-1) + losses[i-1]) / period

        with np.errstate(divide='ignore', invalid='ignore'):
            rs = np.where(avg_loss > 0, avg_gain / avg_loss, 100)
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def _compute_ema(self, closes: np.ndarray, period: int) -> np.ndarray:
        ema = np.zeros_like(closes)
        if len(closes) < period:
            return ema
        ema[period-1] = np.mean(closes[:period])
        multiplier = 2 / (period + 1)
        for i in range(period, len(closes)):
            ema[i] = closes[i] * multiplier + ema[i-1] * (1 - multiplier)
        return ema

    def _compute_atr(self, highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> float:
        if len(closes) < period + 1:
            return 0.0
        tr = np.maximum(
            highs[1:] - lows[1:],
            np.maximum(
                np.abs(highs[1:] - closes[:-1]),
                np.abs(lows[1:] - closes[:-1])
            )
        )
        return float(np.mean(tr[-period:]))

    def _compute_bollinger_bands(self, closes: np.ndarray, period: int = 20, std_dev: float = 2.0):
        if len(closes) < period:
            return None, None, None
        rolling_mean = np.convolve(closes, np.ones(period)/period, mode='valid')
        rolling_std = np.array([np.std(closes[i:i+period]) for i in range(len(closes)-period+1)])
        upper = rolling_mean + std_dev * rolling_std
        lower = rolling_mean - std_dev * rolling_std
        return rolling_mean, upper, lower

    def _compute_macd(self, closes: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9):
        if len(closes) < slow:
            return None, None, None
        ema_fast = self._compute_ema(closes, fast)
        ema_slow = self._compute_ema(closes, slow)
        macd_line = ema_fast - ema_slow
        signal_line = self._compute_ema(macd_line[slow:], signal)
        full_signal = np.zeros_like(macd_line)
        full_signal[slow + signal - 1:] = signal_line[signal-1:]
        histogram = macd_line - full_signal
        return macd_line, full_signal, histogram
