import json
import os
import numpy as np
from typing import Optional, List, Dict
from loguru import logger
from app.strategies.base import BaseStrategy
from app.strategies.trend_following import TrendFollowingStrategy
from app.strategies.mean_reversion import MeanReversionStrategy
from app.strategies.breakout import BreakoutStrategy
from app.strategies.momentum_scalping import MomentumScalpingStrategy
from app.strategies.volatility_scalping import VolatilityScalpingStrategy
from app.strategies.trend_continuation import TrendContinuationStrategy
from app.strategies.micro_scalp import MicroScalpStrategy
from app.market.models import MarketSignal, Candle, Ticker

PERF_FILE = "data/strategy_performance.json"
MIN_TRADES_FOR_ADAPTATION = 15


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
            TrendContinuationStrategy(),
            MicroScalpStrategy(),
        ]
        self.strategy_performance: Dict[str, Dict] = {
            s.name: {"wins": 0, "losses": 0, "total_pnl": 0.0} for s in self.strategies
        }
        self._load_performance()

    def _load_performance(self):
        if not os.path.exists(PERF_FILE):
            return
        try:
            with open(PERF_FILE) as f:
                saved = json.load(f)
            for name, data in saved.items():
                if name in self.strategy_performance:
                    self.strategy_performance[name] = data
            logger.info(f"Loaded strategy performance from {PERF_FILE}")
        except Exception as e:
            logger.warning(f"Could not load strategy performance: {e}")

    def _save_performance(self):
        try:
            os.makedirs("data", exist_ok=True)
            with open(PERF_FILE, "w") as f:
                json.dump(self.strategy_performance, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not save strategy performance: {e}")

    def _strategy_score(self, strategy_name: str) -> float:
        perf = self.strategy_performance.get(strategy_name, {})
        wins = perf.get("wins", 0)
        losses = perf.get("losses", 0)
        total = wins + losses
        if total < MIN_TRADES_FOR_ADAPTATION:
            return 1.0
        win_rate = wins / total
        pnl_factor = 1.0 + min(max(perf.get("total_pnl", 0) / 10, -0.3), 0.5)
        return win_rate * pnl_factor

    def get_performance_multiplier(self, strategy_name: str) -> float:
        perf = self.strategy_performance.get(strategy_name, {})
        wins = perf.get("wins", 0)
        losses = perf.get("losses", 0)
        total = wins + losses
        if total < MIN_TRADES_FOR_ADAPTATION:
            return 1.0
        win_rate = wins / total
        if win_rate >= 0.60:
            return 1.2
        elif win_rate >= 0.40:
            return 1.0
        else:
            return 0.85

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

    async def get_signals(self, symbol: str, candles_by_tf: Dict[str, List[Candle]], ticker: Optional[Ticker], global_regime: Optional[str] = None) -> List[MarketSignal]:
        candles_5m = candles_by_tf.get("5m", [])
        candles_1m = candles_by_tf.get("1m", [])

        if global_regime == "BEARISH":
            active_strategies = [s for s in self.strategies if s.name in ["trend_following", "momentum_scalping", "breakout", "volatility_scalping", "trend_continuation", "micro_scalp"]]
        elif global_regime == "BULLISH":
            regime = self._detect_regime(candles_5m if candles_5m else candles_1m)
            active_strategies = self._get_strategies_for_regime(regime) + [s for s in self.strategies if s.name == "micro_scalp"]
        else:
            regime = self._detect_regime(candles_5m if candles_5m else candles_1m)
            active_strategies = self._get_strategies_for_regime(regime) + [s for s in self.strategies if s.name == "micro_scalp"]

        signals = []
        for strategy in active_strategies:
            try:
                candles = candles_1m if strategy.timeframe == "1m" else candles_5m
                if len(candles) >= strategy.min_candles:
                    signal = await strategy.analyze(symbol, candles, ticker)
                    if signal:
                        signals.append(signal)
                        logger.debug(f"Signal: {symbol} {strategy.name} {signal.direction} strength={signal.strength:.2f} score={self._strategy_score(strategy.name):.2f}")
            except Exception as e:
                logger.error(f"Strategy {strategy.name} error for {symbol}: {e}")

        if signals:
            best = max(signals, key=lambda s: s.strength * self._strategy_score(s.strategy))
            return [best]
        return []

    def update_performance(self, strategy_name: str, pnl: float):
        if strategy_name in self.strategy_performance:
            perf = self.strategy_performance[strategy_name]
            perf["total_pnl"] = round(perf["total_pnl"] + pnl, 6)
            if pnl > 0:
                perf["wins"] += 1
            else:
                perf["losses"] += 1
            self._save_performance()
            wins = perf["wins"]
            losses = perf["losses"]
            total = wins + losses
            win_rate = wins / total if total > 0 else 0
            logger.info(f"Strategy {strategy_name} performance: {wins}W/{losses}L ({win_rate:.0%}) PnL={perf['total_pnl']:.4f} multiplier={self.get_performance_multiplier(strategy_name):.1f}x")
