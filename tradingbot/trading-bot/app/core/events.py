import asyncio
from typing import Dict, List, Callable, Any
from loguru import logger
from dataclasses import dataclass, field
from enum import Enum


class EventType(Enum):
    MARKET_UPDATE = "market_update"
    SIGNAL_GENERATED = "signal_generated"
    ORDER_PLACED = "order_placed"
    ORDER_FILLED = "order_filled"
    ORDER_CANCELLED = "order_cancelled"
    POSITION_OPENED = "position_opened"
    POSITION_CLOSED = "position_closed"
    RISK_LIMIT_HIT = "risk_limit_hit"
    KILL_SWITCH_TRIGGERED = "kill_switch_triggered"
    DAILY_REPORT = "daily_report"
    ERROR = "error"
    TICKER_UPDATE = "ticker_update"
    CANDLE_UPDATE = "candle_update"


@dataclass
class Event:
    type: EventType
    data: Any
    source: str = ""


class EventBus:
    def __init__(self):
        self._subscribers: Dict[EventType, List[Callable]] = {}
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=10000)
        self._running = False

    def subscribe(self, event_type: EventType, handler: Callable):
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)

    async def publish(self, event: Event):
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning(f"Event queue full, dropping event: {event.type}")

    async def run(self):
        self._running = True
        while self._running:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                handlers = self._subscribers.get(event.type, [])
                for handler in handlers:
                    try:
                        if asyncio.iscoroutinefunction(handler):
                            await handler(event)
                        else:
                            handler(event)
                    except Exception as e:
                        logger.error(f"Error in event handler {handler.__name__}: {e}")
                self._queue.task_done()
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"EventBus error: {e}")

    def stop(self):
        self._running = False


event_bus = EventBus()
