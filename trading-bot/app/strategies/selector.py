import numpy as np
from typing import Optional, List, Dict, Tuple
from datetime import datetime
from loguru import logger
from app.strategies.base import BaseStrategy
from app.strategies.trend_following import TrendFollowingStrategy
from app.strategies.mean_reversion import MeanReversionStrategy
from app.strategies.breakout import BreakoutStrategy
from app.strategies.momentum_scalping import MomentumScalpingStrategy
from app.strategies.volatility_scalping import VolatilityScalpingStrategy
from app.market.models import MarketSignal, Candle, Ticker


class MarketRegime:
    TRENDING = "trending"
    RANGING = "ranging"
    VOLATILE = "volatile"
    QUIET = "quiet"


class StrategySelector:
    def __init__(self):
        self.strategies: List[BaseStrategy] = [
            TrendFollowingStrategy(),
            MeanReversionStrategy(),
            BreakoutStrategy(),
            MomentumScalpingStrategy(),
            VolatilityScalpingStrategy(),
        ]
        self.strategy_performance: Dict[str, Dict] = {
            s.name: {"wins": 0, "losses": 0, "total_pnl": 0.0} for s in self.strategies
        }

    def _detect_regime(self, candles: List[Candle]) -> str:
        if len(candles) < 30:
            return MarketRegime.RANGING

        closes = np.array([c.close for c in candles[-50:]])
        highs = np.array([c.high for c in candles[-50:]])
        lows = np.array([c.low for c in candles[-50:]])

        returns = np.diff(closes) / closes[:-1]
        volatility = np.std(returns) * 100

        x = np.arange(len(closes))
        coeffs = np.polyfit(x, closes, 1)
        trend_strength = abs(coeffs[0]) / np.mean(closes)

        atr = np.mean(highs - lows) / np.mean(closes)

        if volatility > 0.3 and atr > 0.015:
            return MarketRegime.VOLATILE
        elif trend_strength > 0.001 and volatility > 0.1:
            return MarketRegime.TRENDING
        elif volatility < 0.05:
            return MarketRegime.QUIET
        else:
            return MarketRegime.RANGING

    def _get_strategies_for_regime(self, regime: str) -> List[BaseStrategy]:
        regime_strategies = {
            MarketRegime.TRENDING: ["trend_following", "momentum_scalping"],
            MarketRegime.RANGING: ["mean_reversion", "volatility_scalping"],
            MarketRegime.VOLATILE: ["breakout", "volatility_scalping"],
            MarketRegime.QUIET: ["mean_reversion"],
        }
        names = regime_strategies.get(regime, [s.name for s in self.strategies])
        return [s for s in self.strategies if s.name in names]

    async def get_signals(self, symbol: str, candles_by_tf: Dict[str, List[Candle]], ticker: Optional[Ticker]) -> List[MarketSignal]:
        candles_5m = candles_by_tf.get("5m", [])
        candles_1m = candles_by_tf.get("1m", [])

        regime = self._detect_regime(candles_5m if candles_5m else candles_1m)
        active_strategies = self._get_strategies_for_regime(regime)

        signals = []
        for strategy in active_strategies:
            try:
                candles = candles_1m if strategy.timeframe == "1m" else candles_5m
                if len(candles) >= strategy.min_candles:
                    signal = await strategy.analyze(symbol, candles, ticker)
                    if signal:
                        signals.append(signal)
                        logger.debug(f"Signal: {symbol} {strategy.name} {signal.direction} strength={signal.strength:.2f}")
            except Exception as e:
                logger.error(f"Strategy {strategy.name} error for {symbol}: {e}")

        # Return strongest signal
        if signals:
            return [max(signals, key=lambda s: s.strength)]
        return []

    def update_performance(self, strategy_name: str, pnl: float):
        if strategy_name in self.strategy_performance:
            perf = self.strategy_performance[strategy_name]
            perf["total_pnl"] += pnl
            if pnl > 0:
                perf["wins"] += 1
            else:
                perf["losses"] += 1
