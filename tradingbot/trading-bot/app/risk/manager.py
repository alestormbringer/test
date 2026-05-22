import asyncio
from typing import Dict, Optional
from datetime import datetime, date
from loguru import logger
from app.core.config import settings
from app.core.events import event_bus, Event, EventType


class RiskManager:
    def __init__(self):
        self.kill_switch_active = False
        self.daily_pnl = 0.0
        self.daily_start_capital = settings.initial_capital
        self.open_positions_count = 0
        self.total_exposure = 0.0
        self.current_capital = settings.initial_capital
        self._last_reset_date: Optional[date] = None
        self._api_errors = 0
        self._max_api_errors = 5

    async def initialize(self, current_capital: float):
        self.current_capital = current_capital
        self.daily_start_capital = current_capital
        self._last_reset_date = date.today()
        logger.info(f"RiskManager initialized. Capital: {current_capital:.2f}")

    def check_daily_reset(self):
        today = date.today()
        if self._last_reset_date != today:
            self.daily_pnl = 0.0
            self.daily_start_capital = self.current_capital
            self._last_reset_date = today
            self._api_errors = 0
            logger.info(f"Daily risk reset. New start capital: {self.daily_start_capital:.2f}")

    async def can_open_trade(self, symbol: str, position_size_usd: float) -> tuple[bool, str]:
        self.check_daily_reset()

        if self.kill_switch_active:
            return False, "Kill switch active"

        if self.open_positions_count >= settings.max_open_positions:
            return False, f"Max positions reached ({settings.max_open_positions})"

        daily_drawdown_pct = abs(min(self.daily_pnl, 0)) / self.daily_start_capital
        if daily_drawdown_pct >= settings.daily_drawdown_limit:
            await self._trigger_kill_switch(f"Daily drawdown limit hit: {daily_drawdown_pct:.2%}")
            return False, "Daily drawdown limit hit"

        max_exposure = self.current_capital * 0.8
        if self.total_exposure + position_size_usd > max_exposure:
            return False, f"Max total exposure would be exceeded"

        return True, "OK"

    def register_trade_open(self, position_size_usd: float):
        self.open_positions_count += 1
        self.total_exposure += position_size_usd
        logger.debug(f"Trade opened. Open positions: {self.open_positions_count}, Exposure: {self.total_exposure:.2f}")

    def register_trade_close(self, position_size_usd: float, pnl: float):
        self.open_positions_count = max(0, self.open_positions_count - 1)
        self.total_exposure = max(0.0, self.total_exposure - position_size_usd)
        self.daily_pnl += pnl
        self.current_capital += pnl
        logger.debug(f"Trade closed. PnL: {pnl:.4f}, Daily PnL: {self.daily_pnl:.4f}")

    def calculate_position_size(self, entry_price: float, stop_loss: float) -> float:
        risk_amount = self.current_capital * settings.risk_per_trade
        price_risk = abs(entry_price - stop_loss) / entry_price
        if price_risk == 0:
            return 0.0
        position_size_usd = risk_amount / price_risk
        max_allowed = self.current_capital * 0.05
        return min(position_size_usd, max_allowed)

    async def report_api_error(self):
        self._api_errors += 1
        if self._api_errors >= self._max_api_errors:
            await self._trigger_kill_switch(f"Too many API errors: {self._api_errors}")

    async def _trigger_kill_switch(self, reason: str):
        self.kill_switch_active = True
        logger.critical(f"KILL SWITCH TRIGGERED: {reason}")
        await event_bus.publish(Event(
            type=EventType.KILL_SWITCH_TRIGGERED,
            data={"reason": reason, "timestamp": datetime.utcnow().isoformat()},
            source="risk_manager",
        ))

    def reset_kill_switch(self):
        self.kill_switch_active = False
        self._api_errors = 0
        logger.info("Kill switch reset manually")
