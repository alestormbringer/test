from dataclasses import dataclass, field
from typing import Optional, List
from datetime import datetime


@dataclass
class Candle:
    symbol: str
    timeframe: str
    open_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    close_time: datetime
    is_closed: bool = True


@dataclass
class Ticker:
    symbol: str
    bid: float
    ask: float
    last: float
    volume_24h: float
    price_change_pct: float
    timestamp: datetime = field(default_factory=datetime.utcnow)

    @property
    def spread(self) -> float:
        return (self.ask - self.bid) / self.bid if self.bid > 0 else 0.0

    @property
    def spread_pct(self) -> float:
        return self.spread * 100


@dataclass
class OrderBook:
    symbol: str
    bids: List[List[float]]  # [[price, qty], ...]
    asks: List[List[float]]
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class MarketSignal:
    symbol: str
    strategy: str
    direction: str  # "long" or "short"
    strength: float  # 0.0 to 1.0
    entry_price: float
    stop_loss: float
    take_profit: float
    timeframe: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: dict = field(default_factory=dict)


@dataclass
class AssetScore:
    symbol: str
    volatility_score: float
    liquidity_score: float
    trend_score: float
    momentum_score: float
    volume_score: float
    spread_score: float
    total_score: float
    timestamp: datetime = field(default_factory=datetime.utcnow)
