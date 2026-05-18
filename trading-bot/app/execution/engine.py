from typing import Optional
from loguru import logger
from app.market.models import MarketSignal
from app.core.config import settings


class ExecutionEngine:
    """Routes trade execution to paper or live trading engine."""

    def __init__(self, paper_engine=None, live_engine=None):
        self.paper_engine = paper_engine
        self.live_engine = live_engine
        self.mode = settings.trading_mode

    async def execute_signal(self, signal: MarketSignal, size_usd: float):
        if self.mode == "paper" and self.paper_engine:
            return await self.paper_engine.open_position(signal, size_usd)
        elif self.mode == "live" and self.live_engine:
            return await self.live_engine.open_position(signal, size_usd)
        else:
            logger.warning(f"No execution engine available for mode: {self.mode}")
            return None

    async def close_position(self, position_id: str, current_price: float, reason: str = "manual"):
        if self.mode == "paper" and self.paper_engine:
            return await self.paper_engine.close_position(position_id, current_price, reason)
        elif self.mode == "live" and self.live_engine:
            return await self.live_engine.close_position(position_id, current_price, reason)
        return None
