from fastapi import FastAPI
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, date

app = FastAPI(title="Crypto Trading Bot Dashboard", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_trading_engine = None


def set_trading_engine(engine):
    global _trading_engine
    _trading_engine = engine


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return HTMLResponse(content=_build_html())


@app.get("/api/summary")
async def get_summary():
    if not _trading_engine:
        return {"status": "initializing"}

    engine = _trading_engine.paper_engine
    regime = _trading_engine.regime_detector.current_regime
    daily_losses = _trading_engine._daily_losses
    max_losses = 5

    # Open positions with unrealized PnL
    open_positions = []
    for pos_id, pos in engine.positions.items():
        current_price = engine._current_prices.get(pos.symbol, pos.entry_price)
        unrealized = (current_price - pos.entry_price) * pos.quantity if pos.direction == "long" \
            else (pos.entry_price - current_price) * pos.quantity
        pnl_pct = (current_price - pos.entry_price) / pos.entry_price * 100 if pos.direction == "long" \
            else (pos.entry_price - current_price) / pos.entry_price * 100
        open_positions.append({
            "id": pos_id,
            "symbol": pos.symbol,
            "direction": pos.direction.upper(),
            "entry_price": round(pos.entry_price, 6),
            "current_price": round(current_price, 6),
            "size_usd": round(pos.size_usd, 2),
            "unrealized_pnl": round(unrealized, 4),
            "pnl_pct": round(pnl_pct, 2),
            "strategy": pos.strategy,
            "opened_at": pos.opened_at.strftime("%H:%M:%S"),
        })

    # Today's closed trades
    today = date.today()
    today_trades = [
        p for p in engine.closed_positions
        if p.closed_at and p.closed_at.date() == today
    ]
    today_pnl = sum(p.pnl for p in today_trades)
    wins = sum(1 for p in today_trades if p.pnl > 0)
    win_rate = (wins / len(today_trades) * 100) if today_trades else 0

    closed_list = []
    for p in reversed(today_trades[-50:]):
        pnl_pct = (p.exit_price - p.entry_price) / p.entry_price * 100 if p.direction == "long" \
            else (p.entry_price - p.exit_price) / p.entry_price * 100
        closed_list.append({
            "symbol": p.symbol,
            "direction": p.direction.upper(),
            "entry_price": round(p.entry_price, 6),
            "exit_price": round(p.exit_price, 6),
            "pnl": round(p.pnl, 4),
            "pnl_pct": round(pnl_pct, 2),
            "exit_reason": p.exit_reason,
            "strategy": p.strategy,
            "opened_at": p.opened_at.strftime("%H:%M:%S") if p.opened_at else "",
            "closed_at": p.closed_at.strftime("%H:%M:%S") if p.closed_at else "",
        })

    return {
        "status": "running",
        "mode": "PAPER",
        "regime": regime,
        "daily_losses": daily_losses,
        "max_losses": max_losses,
        "equity": round(engine.get_equity(), 2),
        "balance": round(engine.balance, 2),
        "today_pnl": round(today_pnl, 4),
        "today_trades": len(today_trades),
        "win_rate": round(win_rate, 1),
        "open_positions": open_positions,
        "closed_trades": closed_list,
        "timestamp": datetime.utcnow().strftime("%H:%M:%S UTC"),
    }


@app.get("/api/trades")
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


@app.post("/api/reset-kill-switch")
async def reset_kill_switch():
    if not _trading_engine:
        return {"error": "Engine not initialized"}
    _trading_engine.risk_manager.reset_kill_switch()
    return {"status": "ok"}


def _build_html() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Trading Bot Dashboard</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: #0d1117; color: #e6edf3; font-family: 'Segoe UI', sans-serif; font-size: 14px; }
  header { background: #161b22; border-bottom: 1px solid #30363d; padding: 16px 24px; display: flex; align-items: center; justify-content: space-between; }
  header h1 { font-size: 18px; font-weight: 600; }
  .badge { padding: 4px 10px; border-radius: 20px; font-size: 12px; font-weight: 600; }
  .badge-paper { background: #1f4e79; color: #58a6ff; }
  .badge-bull { background: #0d2818; color: #3fb950; }
  .badge-bear { background: #2d1010; color: #f85149; }
  .badge-neutral { background: #21262d; color: #8b949e; }
  .timestamp { color: #8b949e; font-size: 12px; }
  .container { max-width: 1200px; margin: 0 auto; padding: 20px 24px; }
  .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-bottom: 24px; }
  .stat-card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px; }
  .stat-label { color: #8b949e; font-size: 12px; margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.5px; }
  .stat-value { font-size: 22px; font-weight: 700; }
  .green { color: #3fb950; }
  .red { color: #f85149; }
  .gray { color: #8b949e; }
  .section { background: #161b22; border: 1px solid #30363d; border-radius: 8px; margin-bottom: 20px; }
  .section-header { padding: 14px 18px; border-bottom: 1px solid #30363d; font-weight: 600; font-size: 14px; display: flex; align-items: center; gap: 8px; }
  .count-badge { background: #21262d; color: #8b949e; padding: 2px 8px; border-radius: 10px; font-size: 12px; }
  table { width: 100%; border-collapse: collapse; }
  th { padding: 10px 14px; text-align: left; color: #8b949e; font-size: 12px; font-weight: 500; border-bottom: 1px solid #21262d; text-transform: uppercase; }
  td { padding: 10px 14px; border-bottom: 1px solid #21262d; }
  tr:last-child td { border-bottom: none; }
  tr:hover td { background: #1c2128; }
  .empty { padding: 32px; text-align: center; color: #8b949e; }
  .dir-long { color: #3fb950; font-weight: 600; }
  .dir-short { color: #f85149; font-weight: 600; }
  .pnl-pos { color: #3fb950; font-weight: 600; }
  .pnl-neg { color: #f85149; font-weight: 600; }
  .reason-tag { background: #21262d; color: #8b949e; padding: 2px 7px; border-radius: 4px; font-size: 11px; }
  footer { text-align: center; padding: 20px; color: #8b949e; font-size: 12px; }
</style>
</head>
<body>
<header>
  <h1>&#9881; Trading Bot</h1>
  <div style="display:flex;align-items:center;gap:10px;">
    <span class="badge badge-paper">PAPER</span>
    <span id="regime-badge" class="badge badge-neutral">...</span>
    <span id="last-update" class="timestamp">Loading...</span>
  </div>
</header>

<div class="container">
  <div class="stats">
    <div class="stat-card">
      <div class="stat-label">Equity</div>
      <div class="stat-value" id="equity">—</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Today P&amp;L</div>
      <div class="stat-value" id="today-pnl">—</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Today Trades</div>
      <div class="stat-value" id="today-trades">—</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Win Rate</div>
      <div class="stat-value" id="win-rate">—</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Daily Losses</div>
      <div class="stat-value" id="daily-losses">—</div>
    </div>
  </div>

  <div class="section">
    <div class="section-header">
      Open Positions
      <span class="count-badge" id="open-count">0</span>
    </div>
    <div id="open-body">
      <table>
        <thead><tr>
          <th>Symbol</th><th>Dir</th><th>Entry</th><th>Current</th>
          <th>Size</th><th>Unreal. PnL</th><th>Strategy</th><th>Opened</th>
        </tr></thead>
        <tbody id="open-table"><tr><td colspan="8" class="empty">No open positions</td></tr></tbody>
      </table>
    </div>
  </div>

  <div class="section">
    <div class="section-header">
      Today's Trades
      <span class="count-badge" id="closed-count">0</span>
    </div>
    <table>
      <thead><tr>
        <th>Symbol</th><th>Dir</th><th>Entry</th><th>Exit</th>
        <th>PnL $</th><th>PnL %</th><th>Reason</th><th>Open</th><th>Close</th>
      </tr></thead>
      <tbody id="closed-table"><tr><td colspan="9" class="empty">No trades today</td></tr></tbody>
    </table>
  </div>
</div>

<footer>Auto-refresh every 10s &nbsp;|&nbsp; <span id="footer-time"></span></footer>

<script>
async function refresh() {
  try {
    const r = await fetch('/api/summary');
    const d = await r.json();

    document.getElementById('last-update').textContent = 'Updated: ' + d.timestamp;
    document.getElementById('footer-time').textContent = d.timestamp;

    // Regime badge
    const rb = document.getElementById('regime-badge');
    rb.textContent = d.regime || '...';
    rb.className = 'badge ' + (d.regime === 'BULLISH' ? 'badge-bull' : d.regime === 'BEARISH' ? 'badge-bear' : 'badge-neutral');

    // Stats
    document.getElementById('equity').textContent = '$' + d.equity;
    const pnlEl = document.getElementById('today-pnl');
    pnlEl.textContent = (d.today_pnl >= 0 ? '+' : '') + d.today_pnl + ' USDT';
    pnlEl.className = 'stat-value ' + (d.today_pnl >= 0 ? 'green' : 'red');
    document.getElementById('today-trades').textContent = d.today_trades;
    document.getElementById('win-rate').textContent = d.win_rate + '%';
    const dlEl = document.getElementById('daily-losses');
    dlEl.textContent = d.daily_losses + ' / ' + d.max_losses;
    dlEl.className = 'stat-value ' + (d.daily_losses >= d.max_losses ? 'red' : d.daily_losses > 0 ? 'gray' : 'green');

    // Open positions
    document.getElementById('open-count').textContent = d.open_positions.length;
    const ot = document.getElementById('open-table');
    if (d.open_positions.length === 0) {
      ot.innerHTML = '<tr><td colspan="8" class="empty">No open positions</td></tr>';
    } else {
      ot.innerHTML = d.open_positions.map(p => `
        <tr>
          <td><b>${p.symbol}</b></td>
          <td class="${p.direction === 'LONG' ? 'dir-long' : 'dir-short'}">${p.direction}</td>
          <td>${p.entry_price}</td>
          <td>${p.current_price}</td>
          <td>$${p.size_usd}</td>
          <td class="${p.unrealized_pnl >= 0 ? 'pnl-pos' : 'pnl-neg'}">${p.unrealized_pnl >= 0 ? '+' : ''}${p.unrealized_pnl} (${p.pnl_pct >= 0 ? '+' : ''}${p.pnl_pct}%)</td>
          <td>${p.strategy}</td>
          <td class="gray">${p.opened_at}</td>
        </tr>`).join('');
    }

    // Closed trades
    document.getElementById('closed-count').textContent = d.closed_trades.length;
    const ct = document.getElementById('closed-table');
    if (d.closed_trades.length === 0) {
      ct.innerHTML = '<tr><td colspan="9" class="empty">No trades today</td></tr>';
    } else {
      ct.innerHTML = d.closed_trades.map(p => `
        <tr>
          <td><b>${p.symbol}</b></td>
          <td class="${p.direction === 'LONG' ? 'dir-long' : 'dir-short'}">${p.direction}</td>
          <td>${p.entry_price}</td>
          <td>${p.exit_price}</td>
          <td class="${p.pnl >= 0 ? 'pnl-pos' : 'pnl-neg'}">${p.pnl >= 0 ? '+' : ''}${p.pnl}</td>
          <td class="${p.pnl_pct >= 0 ? 'pnl-pos' : 'pnl-neg'}">${p.pnl_pct >= 0 ? '+' : ''}${p.pnl_pct}%</td>
          <td><span class="reason-tag">${p.exit_reason}</span></td>
          <td class="gray">${p.opened_at}</td>
          <td class="gray">${p.closed_at}</td>
        </tr>`).join('');
    }
  } catch(e) {
    document.getElementById('last-update').textContent = 'Connection error';
  }
}

refresh();
setInterval(refresh, 10000);
</script>
</body>
</html>"""
