import asyncio
import numpy as np
import pandas as pd
from typing import Dict, List, Optional
from datetime import datetime
from loguru import logger
from app.market.models import AssetScore, Candle, Ticker
from app.market.data_feed import BinanceDataFeed
from app.core.config import settings


class MarketScanner:
    def __init__(self, data_feed: BinanceDataFeed):
        self.data_feed = data_feed
        self.asset_scores: Dict[str, AssetScore] = {}
        self.active_symbols: List[str] = []
        self._running = False
        self.scan_interval = 60  # seconds

    async def start(self):
        self._running = True
        while self._running:
            try:
                await self._scan_markets()
                await asyncio.sleep(self.scan_interval)
            except Exception as e:
                logger.error(f"MarketScanner error: {e}")
                await asyncio.sleep(10)

    def stop(self):
        self._running = False

    async def _scan_markets(self):
        symbols = settings.symbols_list
        scores = {}

        for symbol in symbols:
            try:
                score = await self._score_asset(symbol)
                if score:
                    scores[symbol] = score
            except Exception as e:
                logger.error(f"Error scoring {symbol}: {e}")

        self.asset_scores = scores
        self.active_symbols = sorted(
            scores.keys(),
            key=lambda s: scores[s].total_score,
            reverse=True
        )

        logger.info(f"Market scan complete. Active symbols: {self.active_symbols}")

    async def _score_asset(self, symbol: str) -> Optional[AssetScore]:
        candles_1m = self.data_feed.get_candles(symbol, "1m")
        candles_5m = self.data_feed.get_candles(symbol, "5m")
        ticker = self.data_feed.get_ticker(symbol)

        if not candles_1m or len(candles_1m) < 50:
            return None

        closes = np.array([c.close for c in candles_1m[-100:]])
        volumes = np.array([c.volume for c in candles_1m[-100:]])
        highs = np.array([c.high for c in candles_1m[-100:]])
        lows = np.array([c.low for c in candles_1m[-100:]])

        # Volatility: higher is better for scalping (but not too extreme)
        returns = np.diff(closes) / closes[:-1]
        volatility = np.std(returns) * 100
        vol_score = min(volatility * 20, 1.0) if volatility > 0.05 else 0.1

        # Liquidity: based on volume
        avg_volume = np.mean(volumes[-20:])
        liq_score = min(avg_volume / 1000, 1.0)

        # Trend strength: using linear regression R²
        x = np.arange(len(closes[-20:]))
        y = closes[-20:]
        coeffs = np.polyfit(x, y, 1)
        y_pred = np.polyval(coeffs, x)
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
        trend_score = abs(r_squared)

        # Momentum: rate of change
        roc_5 = (closes[-1] - closes[-6]) / closes[-6] if len(closes) >= 6 else 0
        momentum_score = min(abs(roc_5) * 100, 1.0)

        # Volume score: recent volume vs average
        recent_vol = np.mean(volumes[-5:])
        baseline_vol = np.mean(volumes[-20:])
        vol_ratio = recent_vol / baseline_vol if baseline_vol > 0 else 1
        volume_score = min(vol_ratio, 1.0)

        # Spread score (lower spread = higher score)
        spread_score = 0.8
        if ticker:
            spread_pct = ticker.spread_pct
            spread_score = max(1.0 - (spread_pct * 10), 0.0)

        total = (
            vol_score * 0.20 +
            liq_score * 0.25 +
            trend_score * 0.20 +
            momentum_score * 0.15 +
            volume_score * 0.10 +
            spread_score * 0.10
        )

        return AssetScore(
            symbol=symbol,
            volatility_score=round(vol_score, 4),
            liquidity_score=round(liq_score, 4),
            trend_score=round(trend_score, 4),
            momentum_score=round(momentum_score, 4),
            volume_score=round(volume_score, 4),
            spread_score=round(spread_score, 4),
            total_score=round(total, 4),
        )

    def get_best_symbols(self, n: int = 3) -> List[str]:
        return self.active_symbols[:n]

    def get_score(self, symbol: str) -> Optional[AssetScore]:
        return self.asset_scores.get(symbol)
