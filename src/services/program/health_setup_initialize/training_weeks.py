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

def active_block_id(meta: dict[str, Any]) -> str | None:
    if meta.get("current_block_id"):
        return str(meta["current_block_id"])
    for block in meta.get("blocks") or []:
        if isinstance(block, dict) and block.get("status") == "active":
            block_id = str(block.get("id") or block.get("block_id") or "")
            if block_id and block_id != "current":
                return block_id
    return None


def week_anchor(program_start: date, week_start_day: str) -> date:
    target = WEEKDAY_INDEX[normalize_week_start_day(week_start_day)]
    offset = (program_start.weekday() - target) % 7
    return program_start - timedelta(days=offset)

def week_start_date(program_start: date, week_number: int, week_start_day: str) -> date:
    anchor = week_anchor(program_start, week_start_day)
    return anchor + timedelta(days=(max(1, int(week_number)) - 1) * 7)
