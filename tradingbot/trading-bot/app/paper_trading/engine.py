import asyncio
import random
from typing import Dict, List, Optional
from datetime import datetime
from dataclasses import dataclass, field
from loguru import logger
from app.market.models import MarketSignal
from app.core.config import settings
from app.core.events import event_bus, Event, EventType

BINANCE_MAKER_FEE = 0.001  # 0.1%
BINANCE_TAKER_FEE = 0.001  # 0.1%
SLIPPAGE_BPS = 3  # 0.03% typical slippage


@dataclass
class PaperPosition:
    id: str
    symbol: str
    direction: str
    entry_price: float
    quantity: float
    stop_loss: float
    take_profit: float
    strategy: str
    opened_at: datetime
    size_usd: float
    entry_fee: float
    signal_strength: float
    closed_at: Optional[datetime] = None
    exit_price: Optional[float] = None
    exit_fee: float = 0.0
    pnl: float = 0.0
    exit_reason: str = ""
    trailing_stop: Optional[float] = None


class PaperTradingEngine:
    def __init__(self):
        self.balance = settings.initial_capital
        self.positions: Dict[str, PaperPosition] = {}
        self.closed_positions: List[PaperPosition] = []
        self._position_counter = 0
        self._running = False
        self._current_prices: Dict[str, float] = {}

    def update_price(self, symbol: str, price: float):
        self._current_prices[symbol] = price

    async def open_position(self, signal: MarketSignal, size_usd: float) -> Optional[PaperPosition]:
        if size_usd <= 0 or size_usd > self.balance:
            return None

        # Simulate slippage
        slippage = signal.entry_price * (SLIPPAGE_BPS / 10000)
        if signal.direction == "long":
            actual_entry = signal.entry_price + slippage
        else:
            actual_entry = signal.entry_price - slippage

        # Simulate execution delay (realistic)
        await asyncio.sleep(random.uniform(0.05, 0.2))

        # Calculate fee
        fee = size_usd * BINANCE_TAKER_FEE
        quantity = (size_usd - fee) / actual_entry

        self._position_counter += 1
        position_id = f"PAPER_{self._position_counter:06d}"

        position = PaperPosition(
            id=position_id,
            symbol=signal.symbol,
            direction=signal.direction,
            entry_price=actual_entry,
            quantity=quantity,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            strategy=signal.strategy,
            opened_at=datetime.utcnow(),
            size_usd=size_usd,
            entry_fee=fee,
            signal_strength=signal.strength,
            trailing_stop=signal.stop_loss,
        )

        self.balance -= size_usd
        self.positions[position_id] = position

        await event_bus.publish(Event(
            type=EventType.POSITION_OPENED,
            data={
                "id": position_id,
                "symbol": signal.symbol,
                "direction": signal.direction,
                "entry_price": actual_entry,
                "size_usd": size_usd,
                "strategy": signal.strategy,
            },
            source="paper_trading",
        ))

        logger.info(f"[PAPER] Opened {signal.direction} {signal.symbol} @ {actual_entry:.6f} size={size_usd:.2f} id={position_id}")
        return position

    async def close_position(self, position_id: str, current_price: float, reason: str = "manual") -> Optional[float]:
        position = self.positions.get(position_id)
        if not position:
            return None

        # Simulate slippage on exit
        slippage = current_price * (SLIPPAGE_BPS / 10000)
        if position.direction == "long":
            exit_price = current_price - slippage
        else:
            exit_price = current_price + slippage

        # Calculate PnL
        if position.direction == "long":
            pnl = (exit_price - position.entry_price) * position.quantity
        else:
            pnl = (position.entry_price - exit_price) * position.quantity

        exit_fee = (position.quantity * exit_price) * BINANCE_TAKER_FEE
        net_pnl = pnl - exit_fee

        position.exit_price = exit_price
        position.exit_fee = exit_fee
        position.pnl = net_pnl
        position.exit_reason = reason
        position.closed_at = datetime.utcnow()

        self.balance += position.size_usd + net_pnl
        del self.positions[position_id]
        self.closed_positions.append(position)

        await event_bus.publish(Event(
            type=EventType.POSITION_CLOSED,
            data={
                "id": position_id,
                "symbol": position.symbol,
                "pnl": net_pnl,
                "reason": reason,
                "entry_price": position.entry_price,
                "exit_price": exit_price,
            },
            source="paper_trading",
        ))

        logger.info(f"[PAPER] Closed {position.symbol} {reason} @ {exit_price:.6f} PnL={net_pnl:.4f}")
        return net_pnl

    async def monitor_positions(self, current_prices: Dict[str, float]):
        positions_to_close = []

        for pos_id, position in list(self.positions.items()):
            symbol = position.symbol
            current_price = current_prices.get(symbol)
            if current_price is None:
                continue

            self._current_prices[symbol] = current_price

            # Update trailing stop
            if position.direction == "long":
                trail_distance = position.entry_price - position.stop_loss
                new_trail = current_price - trail_distance
                if new_trail > position.trailing_stop:
                    position.trailing_stop = new_trail

                if current_price <= position.trailing_stop:
                    positions_to_close.append((pos_id, current_price, "trailing_stop"))
                elif current_price >= position.take_profit:
                    positions_to_close.append((pos_id, current_price, "take_profit"))
                elif current_price <= position.stop_loss:
                    positions_to_close.append((pos_id, current_price, "stop_loss"))
            else:
                trail_distance = position.stop_loss - position.entry_price
                new_trail = current_price + trail_distance
                if position.trailing_stop is None or new_trail < position.trailing_stop:
                    position.trailing_stop = new_trail

                if current_price >= position.trailing_stop:
                    positions_to_close.append((pos_id, current_price, "trailing_stop"))
                elif current_price <= position.take_profit:
                    positions_to_close.append((pos_id, current_price, "take_profit"))
                elif current_price >= position.stop_loss:
                    positions_to_close.append((pos_id, current_price, "stop_loss"))

        for pos_id, price, reason in positions_to_close:
            await self.close_position(pos_id, price, reason)

    def get_open_positions_count(self) -> int:
        return len(self.positions)

    def get_total_exposure(self) -> float:
        return sum(p.size_usd for p in self.positions.values())

    def get_unrealized_pnl(self) -> float:
        total = 0.0
        for pos in self.positions.values():
            price = self._current_prices.get(pos.symbol, pos.entry_price)
            if pos.direction == "long":
                total += (price - pos.entry_price) * pos.quantity
            else:
                total += (pos.entry_price - price) * pos.quantity
        return total

    def get_equity(self) -> float:
        return self.balance + self.get_unrealized_pnl()
