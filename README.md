# Crypto Trading Bot

Automated cryptocurrency trading bot built in Python, supporting paper trading and live trading on Binance. Features multiple strategies, risk management, a REST dashboard, Telegram notifications, and daily reports.

## Features

- **Paper trading** with realistic slippage, fees, and execution latency simulation
- **5 trading strategies**: Trend Following, Mean Reversion, Breakout, Momentum Scalping, Volatility Scalping
- **Automatic strategy selection** based on detected market regime (trending, ranging, volatile, quiet)
- **Risk management**: position sizing, daily drawdown limit, max exposure, kill switch
- **Trailing stop** on all positions
- **REST dashboard** (FastAPI) at `http://localhost:8080`
- **Telegram notifications** for trade opens, closes, kill switch and daily reports
- **Daily reports** in JSON and CSV format
- **Market scanner** scoring assets by volatility, liquidity, trend, momentum, volume and spread

## Project Structure

```
tradingbot/trading-bot/
├── main.py                   # Entry point
├── requirements.txt
├── docker-compose.yml
├── pytest.ini
├── .env.example
├── config/
│   └── trading_config.yaml   # Strategy and risk parameters
├── docker/
│   └── Dockerfile
├── scripts/
│   └── start.sh
├── tests/
│   └── test_risk_manager.py
└── app/
    ├── core/
    │   ├── config.py          # Settings (pydantic-settings)
    │   ├── engine.py          # Main trading engine
    │   ├── events.py          # Async event bus
    │   └── logger.py          # Loguru setup
    ├── market/
    │   ├── data_feed.py       # Binance WebSocket + REST feed
    │   ├── models.py          # Candle, Ticker, MarketSignal, etc.
    │   └── scanner.py         # Asset scoring and ranking
    ├── strategies/
    │   ├── base.py            # Abstract base + RSI, EMA, ATR, BB, MACD helpers
    │   ├── trend_following.py
    │   ├── mean_reversion.py
    │   ├── breakout.py
    │   ├── momentum_scalping.py
    │   ├── volatility_scalping.py
    │   └── selector.py        # Regime detection and strategy routing
    ├── risk/
    │   └── manager.py         # Position sizing, drawdown, kill switch
    ├── paper_trading/
    │   └── engine.py          # Simulated order execution
    ├── execution/
    │   ├── engine.py          # Execution router (paper / live)
    │   └── order_manager.py   # Order tracking
    ├── portfolio/
    │   └── manager.py         # Equity, PnL, drawdown tracking
    ├── analytics/
    │   └── engine.py          # Win rate, Sharpe, profit factor, etc.
    ├── reporting/
    │   └── reporter.py        # Daily JSON/CSV report generation
    ├── notifications/
    │   └── telegram.py        # Telegram bot notifications
    ├── dashboard/
    │   └── api.py             # FastAPI dashboard endpoints
    └── utils/
        └── helpers.py
```

## Quick Start

### With Docker Compose (recommended)

```bash
cd tradingbot/trading-bot
cp .env.example .env
# Edit .env if needed (Telegram token, Binance keys for live trading)
docker compose up -d
```

The bot starts in **paper trading** mode by default. Dashboard available at `http://localhost:8080`.

### Without Docker

```bash
cd tradingbot/trading-bot
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit DATABASE_URL and REDIS_URL to use 'localhost' instead of the Docker hostnames
python main.py
```

## Configuration

All settings can be overridden via environment variables or the `.env` file.

| Variable | Default | Description |
|---|---|---|
| `TRADING_MODE` | `paper` | `paper` or `live` |
| `BINANCE_API_KEY` | `` | Required for live trading |
| `BINANCE_API_SECRET` | `` | Required for live trading |
| `INITIAL_CAPITAL` | `50.0` | Starting capital in USDT |
| `RISK_PER_TRADE` | `0.005` | Risk per trade as fraction of capital (0.5%) |
| `DAILY_DRAWDOWN_LIMIT` | `0.03` | Daily drawdown limit before kill switch (3%) |
| `MAX_OPEN_POSITIONS` | `5` | Maximum simultaneous open positions |
| `MONITORED_SYMBOLS` | `BTCUSDT,ETHUSDT,SOLUSDT` | Comma-separated trading pairs |
| `TELEGRAM_BOT_TOKEN` | `` | Optional — Telegram notifications |
| `TELEGRAM_CHAT_ID` | `` | Optional — Telegram chat ID |
| `DASHBOARD_PORT` | `8080` | Dashboard port |
| `LOG_LEVEL` | `INFO` | Log level |

> **Note:** When running via Docker Compose, `DATABASE_URL` and `REDIS_URL` must use `postgres` and `redis` as hostnames. When running locally, use `localhost`.

## Dashboard Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/` | Health check |
| GET | `/status` | Bot status and kill switch state |
| GET | `/portfolio` | Balance, equity, PnL, drawdown |
| GET | `/positions` | Open positions with unrealized PnL |
| GET | `/trades?limit=50` | Recent closed trades |
| GET | `/analytics` | Cumulative performance metrics |
| GET | `/analytics/daily` | Today's performance metrics |
| GET | `/market/scores` | Asset scores from market scanner |
| GET | `/report/daily` | Generate and return daily report |
| POST | `/control/reset-kill-switch` | Reset kill switch manually |

## Running Tests

```bash
cd tradingbot/trading-bot
pip install -r requirements.txt
pytest tests/
```

## Risk Warning

This software is provided for educational and paper trading purposes. Live trading involves significant financial risk. Never trade with funds you cannot afford to lose.
