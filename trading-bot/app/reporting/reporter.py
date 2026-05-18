import json
import csv
import os
from typing import Dict, List
from datetime import datetime
from pathlib import Path
from loguru import logger
from app.analytics.engine import AnalyticsEngine
from app.portfolio.manager import PortfolioManager
from app.paper_trading.engine import PaperTradingEngine


class DailyReporter:
    def __init__(self, analytics: AnalyticsEngine, portfolio: PortfolioManager, paper_engine: PaperTradingEngine):
        self.analytics = analytics
        self.portfolio = portfolio
        self.paper_engine = paper_engine
        self.report_dir = Path("data/reports")
        self.report_dir.mkdir(parents=True, exist_ok=True)

    async def generate_daily_report(self) -> Dict:
        now = datetime.utcnow()
        date_str = now.strftime("%Y-%m-%d")

        daily_metrics = self.analytics.get_daily_metrics()
        all_metrics = self.analytics.get_all_metrics()
        portfolio_summary = self.portfolio.get_summary()

        closed_today = [
            p for p in self.paper_engine.closed_positions
            if p.closed_at and p.closed_at.date() == now.date()
        ]

        trades_detail = []
        for p in closed_today:
            trades_detail.append({
                "id": p.id,
                "symbol": p.symbol,
                "direction": p.direction,
                "strategy": p.strategy,
                "entry_price": p.entry_price,
                "exit_price": p.exit_price,
                "size_usd": p.size_usd,
                "pnl": p.pnl,
                "entry_fee": p.entry_fee,
                "exit_fee": p.exit_fee,
                "opened_at": p.opened_at.isoformat() if p.opened_at else None,
                "closed_at": p.closed_at.isoformat() if p.closed_at else None,
                "exit_reason": p.exit_reason,
                "signal_strength": p.signal_strength,
                "duration_minutes": (
                    (p.closed_at - p.opened_at).total_seconds() / 60
                    if p.closed_at and p.opened_at else 0
                ),
            })

        report = {
            "report_date": date_str,
            "generated_at": now.isoformat(),
            "trading_mode": "paper",
            "portfolio": portfolio_summary,
            "daily_performance": daily_metrics,
            "cumulative_performance": all_metrics,
            "trades_today": trades_detail,
            "open_positions": len(self.paper_engine.positions),
        }

        # Save JSON
        json_path = self.report_dir / f"report_{date_str}.json"
        with open(json_path, "w") as f:
            json.dump(report, f, indent=2, default=str)

        # Save CSV
        csv_path = self.report_dir / f"trades_{date_str}.csv"
        if trades_detail:
            fieldnames = list(trades_detail[0].keys())
            with open(csv_path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(trades_detail)

        logger.info(f"Daily report generated: {json_path}")
        return report
