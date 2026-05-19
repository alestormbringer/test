import pytest
import pytest_asyncio
from app.risk.manager import RiskManager
from app.core.config import settings


@pytest_asyncio.fixture
async def risk_manager():
    rm = RiskManager()
    await rm.initialize(50.0)
    return rm


async def test_initial_state(risk_manager):
    assert risk_manager.current_capital == 50.0
    assert not risk_manager.kill_switch_active
    assert risk_manager.open_positions_count == 0


async def test_position_size_calculation(risk_manager):
    entry = 100.0
    stop_loss = 99.75  # 0.25% below entry
    size = risk_manager.calculate_position_size(entry, stop_loss)
    assert size > 0
    max_size = 50.0 * 0.15
    assert size <= max_size


async def test_can_open_trade(risk_manager):
    can_trade, reason = await risk_manager.can_open_trade("BTCUSDT", 2.0)
    assert can_trade
    assert reason == "OK"


async def test_max_positions(risk_manager):
    for _ in range(settings.max_open_positions):
        risk_manager.register_trade_open(2.0)

    can_trade, reason = await risk_manager.can_open_trade("ETHUSDT", 2.0)
    assert not can_trade
    assert "Max positions" in reason


async def test_daily_drawdown_limit(risk_manager):
    loss = risk_manager.current_capital * settings.daily_drawdown_limit + 0.01
    risk_manager.register_trade_close(10.0, -loss)

    can_trade, reason = await risk_manager.can_open_trade("SOLUSDT", 1.0)
    assert not can_trade


async def test_kill_switch(risk_manager):
    await risk_manager._trigger_kill_switch("test")
    assert risk_manager.kill_switch_active

    risk_manager.reset_kill_switch()
    assert not risk_manager.kill_switch_active
