from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
import asyncio
from datetime import datetime

app = FastAPI(title="Crypto Trading Bot Dashboard", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global references (set by trading engine)
_trading_engine = None


def set_trading_engine(engine):
    global _trading_engine
    _trading_engine = engine


@app.get("/")
async def root():
    return {"status": "running", "timestamp": datetime.utcnow().isoformat()}


@app.get("/status")
async def get_status():
    if not _trading_engine:
        return {"status": "initializing"}
    return {
        "status": "running",
        "mode": "paper",
        "kill_switch": _trading_engine.risk_manager.kill_switch_active,
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/portfolio")
async def get_portfolio():
    if not _trading_engine:
        return {}
    return _trading_engine.portfolio_manager.get_summary()


@app.get("/positions")
async def get_positions():
    if not _trading_engine:
        return []
    engine = _trading_engine.paper_engine
    positions = []
    for pos_id, pos in engine.positions.items():
        current_price = engine._current_prices.get(pos.symbol, pos.entry_price)
        if pos.direction == "long":
            unrealized = (current_price - pos.entry_price) * pos.quantity
        else:
            unrealized = (pos.entry_price - current_price) * pos.quantity
        positions.append({
            "id": pos_id,
            "symbol": pos.symbol,
            "direction": pos.direction,
            "entry_price": pos.entry_price,
            "current_price": current_price,
            "quantity": pos.quantity,
            "size_usd": pos.size_usd,
            "unrealized_pnl": round(unrealized, 6),
            "stop_loss": pos.stop_loss,
            "take_profit": pos.take_profit,
            "strategy": pos.strategy,
            "opened_at": pos.opened_at.isoformat(),
        })
    return positions


@app.get("/analytics")
async def get_analytics():
    if not _trading_engine:
        return {}
    return _trading_engine.analytics_engine.get_all_metrics()


@app.get("/analytics/daily")
async def get_daily_analytics():
    if not _trading_engine:
        return {}
    return _trading_engine.analytics_engine.get_daily_metrics()


@app.get("/trades")
async def get_trades(limit: int = 50):
    if not _trading_engine:
        return []
    positions = _trading_engine.paper_engine.closed_positions[-limit:]
    result = []
    for p in reversed(positions):
        result.append({
            "id": p.id,
            "symbol": p.symbol,
            "direction": p.direction,
            "entry_price": p.entry_price,
            "exit_price": p.exit_price,
            "pnl": p.pnl,
            "strategy": p.strategy,
            "exit_reason": p.exit_reason,
            "opened_at": p.opened_at.isoformat() if p.opened_at else None,
            "closed_at": p.closed_at.isoformat() if p.closed_at else None,
        })
    return result


@app.get("/market/scores")
async def get_market_scores():
    if not _trading_engine:
        return {}
    return {
        sym: {
            "total_score": score.total_score,
            "volatility_score": score.volatility_score,
            "liquidity_score": score.liquidity_score,
            "trend_score": score.trend_score,
            "momentum_score": score.momentum_score,
        }
        for sym, score in _trading_engine.market_scanner.asset_scores.items()
    }


@app.post("/control/reset-kill-switch")
async def reset_kill_switch():
    if not _trading_engine:
        return {"error": "Engine not initialized"}
    _trading_engine.risk_manager.reset_kill_switch()
    return {"status": "kill switch reset"}


@app.get("/report/daily")
async def get_daily_report():
    if not _trading_engine:
        return {}
    return await _trading_engine.reporter.generate_daily_report()
