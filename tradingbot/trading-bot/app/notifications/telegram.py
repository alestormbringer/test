import asyncio
import aiohttp
from typing import Optional
from loguru import logger
from app.core.config import settings


class TelegramNotifier:
    def __init__(self):
        self.token = settings.telegram_bot_token
        self.chat_id = settings.telegram_chat_id
        self.enabled = bool(self.token and self.chat_id)
        self._session: Optional[aiohttp.ClientSession] = None

    async def start(self):
        if self.enabled:
            self._session = aiohttp.ClientSession()
            logger.info("Telegram notifier started")

    async def stop(self):
        if self._session:
            await self._session.close()

    async def send_message(self, text: str):
        if not self.enabled or not self._session:
            return
        try:
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            payload = {"chat_id": self.chat_id, "text": text, "parse_mode": "HTML"}
            async with self._session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    logger.warning(f"Telegram send failed: {resp.status}")
        except Exception as e:
            logger.error(f"Telegram error: {e}")

    async def notify_trade_opened(self, symbol: str, direction: str, entry: float, size: float, strategy: str, regime: str = ""):
        label = "OPEN LONG" if direction == "long" else "OPEN SHORT"
        regime_line = f"\nRegime: {regime}" if regime else ""
        msg = (
            f"<b>{symbol} {label}</b>\n"
            f"Entry: ${entry:.6f}\n"
            f"Size: ${size:.2f}\n"
            f"Strategy: {strategy}{regime_line}"
        )
        await self.send_message(msg)

    async def notify_trade_closed(self, symbol: str, direction: str, entry: float, exit_price: float, pnl: float, pnl_pct: float, reason: str, regime: str = ""):
        result = "SELL" if direction == "long" else "BUY"
        emoji = "✅" if pnl > 0 else "❌"
        msg = (
            f"{symbol} CLOSE {'LONG' if direction == 'long' else 'SHORT'}\n"
            f"{emoji} <b>{result} | {symbol}</b>\n"
            f"Entry:  ${entry:.4f}\n"
            f"Exit:   ${exit_price:.4f}\n"
            f"PnL:    {pnl_pct:+.2f}%\n"
            f"P&amp;L $: {pnl:+.2f} USDT\n"
            f"Reason: {reason}\n"
            f"Regime: {regime}"
        )
        await self.send_message(msg)

    async def notify_regime_change(self, regime: str, daily_losses: int, max_losses: int):
        emoji = "🟢" if regime == "BULLISH" else "🔴"
        msg = f"{emoji} <b>Regime: {regime}</b> | Daily losses: {daily_losses}/{max_losses}"
        await self.send_message(msg)

    async def notify_status(self, regime: str, daily_losses: int, max_losses: int):
        emoji = "🟢" if regime == "BULLISH" else "🔴"
        msg = f"📊 Regime: <b>{regime}</b> | Daily losses: {daily_losses}/{max_losses}"
        await self.send_message(msg)

    async def notify_kill_switch(self, reason: str):
        msg = f"🚨 <b>KILL SWITCH TRIGGERED</b>\nReason: {reason}"
        await self.send_message(msg)

    async def notify_daily_report(self, report: dict):
        perf = report.get("daily_performance", {})
        portfolio = report.get("portfolio", {})
        msg = (
            f"📊 <b>DAILY REPORT - {report.get('report_date')}</b>\n"
            f"Trades: {perf.get('total_trades', 0)}\n"
            f"Win Rate: {perf.get('win_rate', 0):.1%}\n"
            f"Daily PnL: {perf.get('total_pnl', 0):+.4f} USDT\n"
            f"Equity: {portfolio.get('equity', 0):.2f} USDT\n"
            f"Max DD: {perf.get('max_drawdown', 0):.2%}"
        )
        await self.send_message(msg)
