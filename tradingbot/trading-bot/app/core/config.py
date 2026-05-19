from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Trading mode
    trading_mode: str = "paper"

    # Binance
    binance_api_key: str = ""
    binance_api_secret: str = ""
    binance_testnet: bool = False

    # Database
    database_url: str = "postgresql+asyncpg://trader:trading123@postgres:5432/tradingbot"

    # Redis
    redis_url: str = "redis://redis:6379"

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

    # Max daily losses before pausing
    max_daily_losses: int = 5

    # Assets
    monitored_symbols: str = "SOLUSDT,XRPUSDT,ADAUSDT,DOGEUSDT,BNBUSDT"

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


settings = Settings()
