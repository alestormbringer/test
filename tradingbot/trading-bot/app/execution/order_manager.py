import asyncio
from typing import Dict, List, Optional, Set
from datetime import datetime
from dataclasses import dataclass, field
from loguru import logger


@dataclass
class Order:
    id: str
    symbol: str
    direction: str
    order_type: str  # "market", "limit", "stop"
    quantity: float
    price: Optional[float]
    status: str  # "pending", "filled", "cancelled", "rejected"
    created_at: datetime = field(default_factory=datetime.utcnow)
    filled_at: Optional[datetime] = None
    fill_price: Optional[float] = None
    strategy: str = ""


class OrderManager:
    """Tracks open orders and prevents duplicate submissions."""

    def __init__(self):
        self.orders: Dict[str, Order] = {}
        self.pending_symbols: Set[str] = set()
        self._order_counter = 0

    def has_pending_order(self, symbol: str) -> bool:
        return symbol in self.pending_symbols

    def register_order(self, symbol: str, direction: str, quantity: float,
                       price: Optional[float] = None, order_type: str = "market",
                       strategy: str = "") -> Order:
        self._order_counter += 1
        order_id = f"ORD_{self._order_counter:08d}"
        order = Order(
            id=order_id,
            symbol=symbol,
            direction=direction,
            order_type=order_type,
            quantity=quantity,
            price=price,
            status="pending",
            strategy=strategy,
        )
        self.orders[order_id] = order
        self.pending_symbols.add(symbol)
        logger.debug(f"Order registered: {order_id} {symbol} {direction} {quantity}")
        return order

    def fill_order(self, order_id: str, fill_price: float):
        order = self.orders.get(order_id)
        if order:
            order.status = "filled"
            order.fill_price = fill_price
            order.filled_at = datetime.utcnow()
            self.pending_symbols.discard(order.symbol)
            logger.debug(f"Order filled: {order_id} @ {fill_price}")

    def cancel_order(self, order_id: str):
        order = self.orders.get(order_id)
        if order:
            order.status = "cancelled"
            self.pending_symbols.discard(order.symbol)
            logger.debug(f"Order cancelled: {order_id}")

    def get_open_orders(self) -> List[Order]:
        return [o for o in self.orders.values() if o.status == "pending"]

    def get_orders_for_symbol(self, symbol: str) -> List[Order]:
        return [o for o in self.orders.values() if o.symbol == symbol]

    def cleanup_old_orders(self, max_orders: int = 1000):
        if len(self.orders) > max_orders:
            filled = [oid for oid, o in self.orders.items() if o.status in ("filled", "cancelled")]
            for oid in filled[:len(self.orders) - max_orders]:
                del self.orders[oid]
