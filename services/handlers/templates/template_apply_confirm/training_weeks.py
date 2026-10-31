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


def week_start_for_block(program: dict[str, Any] | None, block: str = "current") -> str:
    meta = (program or {}).get("meta", {}) if isinstance(program, dict) else {}
    meta = meta if isinstance(meta, dict) else {}
    block_name = block or "current"
    block_id = (active_block_id(meta) or "current") if block_name == "current" else block_name
    stored = meta.get("block_week_start_days") if isinstance(meta.get("block_week_start_days"), dict) else {}
    record = next(
        (b for b in meta.get("blocks") or [] if isinstance(b, dict) and str(b.get("id") or b.get("block_id") or "") == block_id),
        {},
    )
    candidates = [stored.get(block_id), record.get("week_start_day"), stored.get(block_name)]
    if block_name == "current":
        candidates.append(meta.get("program_week_start_day"))
    for value in candidates:
        if isinstance(value, str) and value.strip().capitalize() in WEEKDAY_INDEX:
            return value.strip().capitalize()
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
