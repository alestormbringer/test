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

    async def notify_trade_opened(self, symbol: str, direction: str, entry: float, size: float, strategy: str):
        emoji = "Long" if direction == "long" else "Short"
        msg = (
            f"[{emoji}] <b>TRADE OPENED</b>\n"
            f"Symbol: {symbol}\n"
            f"Direction: {direction.upper()}\n"
            f"Entry: {entry:.6f}\n"
            f"Size: ${size:.2f}\n"
            f"Strategy: {strategy}"
        )
        await self.send_message(msg)

    async def notify_trade_closed(self, symbol: str, pnl: float, reason: str):
        result = "WIN" if pnl > 0 else "LOSS"
        msg = (
            f"[{result}] <b>TRADE CLOSED</b>\n"
            f"Symbol: {symbol}\n"
            f"PnL: {pnl:+.4f} USDT\n"
            f"Reason: {reason}"
        )
        await self.send_message(msg)

    async def notify_kill_switch(self, reason: str):
        msg = f"[ALERT] <b>KILL SWITCH TRIGGERED</b>\nReason: {reason}"
        await self.send_message(msg)

    async def notify_daily_report(self, report: dict):
        perf = report.get("daily_performance", {})
        portfolio = report.get("portfolio", {})
        msg = (
            f"[REPORT] <b>DAILY REPORT - {report.get('report_date')}</b>\n"
            f"Trades: {perf.get('total_trades', 0)}\n"
            f"Win Rate: {perf.get('win_rate', 0):.1%}\n"
            f"Daily PnL: {perf.get('total_pnl', 0):+.4f} USDT\n"
            f"Equity: {portfolio.get('equity', 0):.2f} USDT\n"
            f"Max DD: {perf.get('max_drawdown', 0):.2%}"
        )
        await self.send_message(msg)
