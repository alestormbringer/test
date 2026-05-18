from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import List
import os

class Settings(BaseSettings):
    # Trading mode
    trading_mode: str = "paper"

    # Binance
    binance_api_key: str = ""
    binance_api_secret: str = ""
    binance_testnet: bool = False

    # Database
    database_url: str = "postgresql+asyncpg://trader:trading123@localhost:5432/tradingbot"

    # Redis
    redis_url: str = "redis://localhost:6379"

    # Telegram
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # Capital
    initial_capital: float = 50.0

    # Risk
    risk_per_trade: float = 0.005
    daily_drawdown_limit: float = 0.03
    max_open_positions: int = 5
    take_profit_pct: float = 0.004
    stop_loss_pct: float = 0.0025

    # Assets
    monitored_symbols: str = "BTCUSDT,ETHUSDT,SOLUSDT"

    # Dashboard
    dashboard_host: str = "0.0.0.0"
    dashboard_port: int = 8080

    # Logging
    log_level: str = "INFO"

    @property
    def symbols_list(self) -> List[str]:
        return [s.strip() for s in self.monitored_symbols.split(",")]

    @property
    def is_paper_trading(self) -> bool:
        return self.trading_mode.lower() == "paper"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

settings = Settings()
