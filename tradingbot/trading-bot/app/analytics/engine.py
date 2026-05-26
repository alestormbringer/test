import numpy as np
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from loguru import logger
from app.paper_trading.engine import PaperPosition
from app.core.config import settings


class AnalyticsEngine:
    def __init__(self):
        self._closed_positions: List[PaperPosition] = []

    def update(self, positions: List[PaperPosition]):
        self._closed_positions = positions

    def _get_recent(self, days: int = 1) -> List[PaperPosition]:
        cutoff = datetime.utcnow() - timedelta(days=days)
        return [p for p in self._closed_positions if p.closed_at and p.closed_at >= cutoff]

    def compute_metrics(self, positions: Optional[List[PaperPosition]] = None) -> Dict:
        if positions is None:
            positions = self._closed_positions

        if not positions:
            return self._empty_metrics()

        pnls = [p.pnl for p in positions]
        wins = [p for p in positions if p.pnl > 0]
        losses = [p for p in positions if p.pnl <= 0]

        total_pnl = sum(pnls)
        win_rate = len(wins) / len(positions) if positions else 0

        avg_win = np.mean([p.pnl for p in wins]) if wins else 0
        avg_loss = np.mean([p.pnl for p in losses]) if losses else 0

        gross_profit = sum(p.pnl for p in wins)
        gross_loss = abs(sum(p.pnl for p in losses))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        expectancy = (win_rate * avg_win) + ((1 - win_rate) * avg_loss)

        # Sharpe ratio (simplified daily)
        if len(pnls) > 1:
            pnl_std = np.std(pnls)
            sharpe = (np.mean(pnls) / pnl_std) * np.sqrt(252) if pnl_std > 0 else 0
        else:
            sharpe = 0

        # Max drawdown from equity curve (anchored to initial capital)
        equity_curve = []
        running = settings.initial_capital
        for p in sorted(positions, key=lambda x: x.closed_at or datetime.utcnow()):
            running += p.pnl
            equity_curve.append(running)

        max_drawdown = 0.0
        peak = equity_curve[0] if equity_curve else settings.initial_capital
        for val in equity_curve:
            if val > peak:
                peak = val
            dd = (peak - val) / peak
            max_drawdown = max(max_drawdown, dd)

        # Duration
        durations = []
        for p in positions:
            if p.closed_at and p.opened_at:
                dur = (p.closed_at - p.opened_at).total_seconds() / 60
                durations.append(dur)
        avg_duration_min = np.mean(durations) if durations else 0

        total_fees = sum(p.entry_fee + p.exit_fee for p in positions)

        # Per strategy
        strategy_perf = {}
        for p in positions:
            s = p.strategy
            if s not in strategy_perf:
                strategy_perf[s] = {"trades": 0, "pnl": 0.0, "wins": 0}
            strategy_perf[s]["trades"] += 1
            strategy_perf[s]["pnl"] += p.pnl
            if p.pnl > 0:
                strategy_perf[s]["wins"] += 1

        # Per symbol
        symbol_perf = {}
        for p in positions:
            sym = p.symbol
            if sym not in symbol_perf:
                symbol_perf[sym] = {"trades": 0, "pnl": 0.0, "wins": 0}
            symbol_perf[sym]["trades"] += 1
            symbol_perf[sym]["pnl"] += p.pnl
            if p.pnl > 0:
                symbol_perf[sym]["wins"] += 1

        return {
            "total_trades": len(positions),
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "win_rate": round(win_rate, 4),
            "total_pnl": round(total_pnl, 6),
            "avg_win": round(avg_win, 6),
            "avg_loss": round(avg_loss, 6),
            "profit_factor": round(profit_factor, 4) if profit_factor != float("inf") else 999.0,
            "expectancy": round(expectancy, 6),
            "sharpe_ratio": round(sharpe, 4),
            "max_drawdown": round(max_drawdown, 4),
            "avg_duration_minutes": round(avg_duration_min, 2),
            "total_fees": round(total_fees, 6),
            "strategy_performance": strategy_perf,
            "symbol_performance": symbol_perf,
        }

    def _empty_metrics(self) -> Dict:
        return {
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate": 0.0,
            "total_pnl": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "profit_factor": 0.0,
            "expectancy": 0.0,
            "sharpe_ratio": 0.0,
            "max_drawdown": 0.0,
            "avg_duration_minutes": 0.0,
            "total_fees": 0.0,
            "strategy_performance": {},
            "symbol_performance": {},
        }

    def get_daily_metrics(self) -> Dict:
        daily_positions = self._get_recent(days=1)
        return self.compute_metrics(daily_positions)

    def get_all_metrics(self) -> Dict:
        return self.compute_metrics(self._closed_positions)
