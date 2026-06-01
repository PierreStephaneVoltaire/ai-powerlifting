from __future__ import annotations

from datetime import date, timedelta
from typing import Any

WEEK_START_DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
WEEKDAY_INDEX = {day: idx for idx, day in enumerate(WEEK_START_DAYS)}

def normalize_week_start_day(value: Any, default: str = "Monday") -> str:
    if isinstance(value, str):
        cleaned = value.strip().capitalize()
        if cleaned in WEEKDAY_INDEX:
            return cleaned
    return default if default in WEEKDAY_INDEX else "Monday"

def week_start_for_block(program: dict[str, Any] | None, block: str = "current") -> str:
    """Resolve the configured week-start day for a block."""
    meta = (program or {}).get("meta", {}) if isinstance(program, dict) else {}
    block_name = block or "current"
    stored = meta.get("block_week_start_days") if isinstance(meta, dict) else None
    if isinstance(stored, dict) and block_name in stored:
        return normalize_week_start_day(stored.get(block_name), "Monday")
    return "Monday"

def week_anchor(program_start: date, week_start_day: str) -> date:
    target = WEEKDAY_INDEX[normalize_week_start_day(week_start_day)]
    offset = (program_start.weekday() - target) % 7
    return program_start - timedelta(days=offset)

def week_for_date(day: date, program_start: date, week_start_day: str) -> int:
    anchor = week_anchor(program_start, week_start_day)
    return max(1, ((day - anchor).days // 7) + 1)

def week_start_date(program_start: date, week_number: int, week_start_day: str) -> date:
    anchor = week_anchor(program_start, week_start_day)
    return anchor + timedelta(days=(max(1, int(week_number)) - 1) * 7)
