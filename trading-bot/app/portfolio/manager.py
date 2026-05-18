from typing import Dict, List, Optional
from datetime import datetime
from loguru import logger
from app.core.config import settings


class PortfolioManager:
    def __init__(self, paper_engine=None):
        self.paper_engine = paper_engine
        self.initial_capital = settings.initial_capital
        self._equity_history: List[Dict] = []
        self._peak_equity = settings.initial_capital
        self._max_drawdown = 0.0

    def get_balance(self) -> float:
        if self.paper_engine:
            return self.paper_engine.balance
        return self.initial_capital

    def get_equity(self) -> float:
        if self.paper_engine:
            return self.paper_engine.get_equity()
        return self.initial_capital

    def get_unrealized_pnl(self) -> float:
        if self.paper_engine:
            return self.paper_engine.get_unrealized_pnl()
        return 0.0

    def get_total_pnl(self) -> float:
        return self.get_equity() - self.initial_capital

    def get_total_pnl_pct(self) -> float:
        return (self.get_total_pnl() / self.initial_capital) * 100

    def update_metrics(self):
        equity = self.get_equity()
        self._equity_history.append({"timestamp": datetime.utcnow().isoformat(), "equity": equity})

        if equity > self._peak_equity:
            self._peak_equity = equity

        current_drawdown = (self._peak_equity - equity) / self._peak_equity
        if current_drawdown > self._max_drawdown:
            self._max_drawdown = current_drawdown

        if len(self._equity_history) > 10000:
            self._equity_history.pop(0)

    def get_max_drawdown(self) -> float:
        return self._max_drawdown

    def get_summary(self) -> Dict:
        return {
            "initial_capital": self.initial_capital,
            "current_balance": self.get_balance(),
            "equity": self.get_equity(),
            "unrealized_pnl": self.get_unrealized_pnl(),
            "total_pnl": self.get_total_pnl(),
            "total_pnl_pct": self.get_total_pnl_pct(),
            "max_drawdown": self.get_max_drawdown(),
            "peak_equity": self._peak_equity,
        }
