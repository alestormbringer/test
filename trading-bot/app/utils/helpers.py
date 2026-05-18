import hashlib
from datetime import datetime
from typing import Any, Dict


def round_to_precision(value: float, precision: int = 8) -> float:
    return round(value, precision)


def calculate_pct_change(old_val: float, new_val: float) -> float:
    if old_val == 0:
        return 0.0
    return (new_val - old_val) / old_val * 100


def format_pnl(pnl: float) -> str:
    sign = "+" if pnl >= 0 else ""
    return f"{sign}{pnl:.4f}"


def utcnow_iso() -> str:
    return datetime.utcnow().isoformat()
