from __future__ import annotations

from datetime import date
from typing import Any, Iterable

ACTIVE = "current"
ALL_BLOCKS = "all"
BLOCK_SCOPED_RECORD_FIELDS = ("diet_notes", "supplements", "supplement_phases", "competitions")
SCOPED_PROGRAM_LISTS = ("phases", "sessions", *BLOCK_SCOPED_RECORD_FIELDS)
DATE_FIELDS = ("date", "start_date", "meet_date", "competition_date", "entry_date")


def _block_id(block: dict) -> str:
    return str(block.get("id") or block.get("block_id") or "")


def _blocks(program: dict | None) -> list[dict]:
    meta = (program or {}).get("meta") or {}
    blocks = [block for block in meta.get("blocks") or [] if isinstance(block, dict) and _block_id(block)]
    return sorted(
        blocks,
        key=lambda block: (parse_iso_date(block.get("start_date")) or date.min, _block_id(block)),
    )


def current_block_id(program: dict | None) -> str:
    meta = (program or {}).get("meta") or {}
    configured = str(meta.get("current_block_id") or "")
    if configured and configured != ACTIVE:
        return configured
    active = [block for block in _blocks(program) if block.get("status") == "active"]
    if active:
        return _block_id(active[-1])
    return configured or ACTIVE


def resolve_block_id(program: dict | None, block_id: str | None) -> str:
    if not block_id or block_id == ACTIVE:
        return current_block_id(program)
    return str(block_id)


def record_block_key(record: dict) -> str:
    return str(record.get("block_id") or record.get("block") or "")


def in_block(record: Any, block_id: str, active_block_id: str) -> bool:
    if not isinstance(record, dict):
        return False
    key = record_block_key(record)
    if block_id in {active_block_id, ACTIVE}:
        return key in {active_block_id, ACTIVE}
    return key == block_id


def record_date(record: dict | None) -> str | None:
    if not isinstance(record, dict):
        return None
    for field in DATE_FIELDS:
        value = record.get(field)
        if value:
            return str(value)[:10]
    return None


def parse_iso_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None


def _most_recent_completed_block(program: dict) -> str | None:
    completed = [block for block in _blocks(program) if block.get("status") == "completed"]
    if not completed:
        return None
    return _block_id(max(completed, key=lambda block: (str(block.get("completed_at") or ""), str(block.get("start_date") or ""))))


def _block_for_date(record_day: date, program: dict) -> str:
    blocks = [block for block in _blocks(program) if parse_iso_date(block.get("start_date"))]
    active = current_block_id(program)
    if not blocks:
        return active
    active_start = next((parse_iso_date(block.get("start_date")) for block in blocks if _block_id(block) == active), None)
    if active_start and record_day >= active_start:
        return active
    if record_day < parse_iso_date(blocks[0].get("start_date")):
        return _block_id(blocks[0])
    for index, block in enumerate(blocks):
        start = parse_iso_date(block.get("start_date"))
        next_start = parse_iso_date(blocks[index + 1].get("start_date")) if index + 1 < len(blocks) else None
        if start and start <= record_day and (next_start is None or record_day < next_start):
            return _block_id(block)
    return _block_id(blocks[-1])


def record_block(record: Any, field: str, program: dict) -> str:
    active = current_block_id(program)
    if not isinstance(record, dict):
        return active
    record_day = parse_iso_date(record_date(record))
    if record_day and _blocks(program):
        return _block_for_date(record_day, program)
    stamped = record_block_key(record)
    if stamped:
        return active if stamped == ACTIVE else stamped
    if field == "supplement_phases":
        return _most_recent_completed_block(program) or active
    return active


def scope_entries(entries: Iterable[Any] | None, block_id: str, program: dict, field: str) -> list:
    target = resolve_block_id(program, block_id)
    return [
        entry
        for entry in entries or []
        if isinstance(entry, dict) and (
            record_block(entry, field, program) == target
        )
    ]


def scope_program(program: dict, block_id: str | None = None) -> dict:
    target = resolve_block_id(program, block_id)
    scoped = dict(program)
    for field in SCOPED_PROGRAM_LISTS:
        if isinstance(program.get(field), list):
            scoped[field] = scope_entries(program[field], target, program, field)
    meta = program.get("meta")
    if isinstance(meta, dict) and isinstance(meta.get("block_notes"), list):
        scoped["meta"] = {**meta, "block_notes": scope_entries(meta["block_notes"], target, program, "meta.block_notes")}
    if isinstance(program.get("block_notes"), list):
        scoped["block_notes"] = scope_entries(program["block_notes"], target, program, "block_notes")
    if isinstance(scoped.get("competitions"), list):
        competition_dates = sorted(str(item.get("date") or "")[:10] for item in scoped["competitions"] if item.get("date"))
        scoped_meta = dict(scoped.get("meta") or {})
        if competition_dates:
            scoped_meta["comp_date"] = competition_dates[0]
        else:
            scoped_meta.pop("comp_date", None)
        scoped["meta"] = scoped_meta
    if isinstance(program.get("weight_log"), list):
        scoped["weight_log"] = scope_entries(program["weight_log"], target, program, "weight_log")
    return scoped


def stamp(record: dict, program: dict | None, block_id: str | None = None, field: str = "") -> dict:
    if not record.get("block_id"):
        record["block_id"] = str(block_id or record_block(record, field, program or {}))
    return record


def active_block_id_for(pk: str, table: Any = None) -> str:
    if table is None:
        import os
        from services.lib.aws import table as dynamodb_table
        table = dynamodb_table(os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"), os.environ.get("AWS_REGION", "ca-central-1"))
    pointer = table.get_item(Key={"pk": pk, "sk": "program#current"}).get("Item") or {}
    if pointer.get("current_block_id") and pointer["current_block_id"] != ACTIVE:
        return str(pointer["current_block_id"])
    if not pointer.get("ref_sk"):
        return current_block_id(pointer)
    program = table.get_item(Key={"pk": pk, "sk": pointer["ref_sk"]}).get("Item") or {}
    return current_block_id(program)


def current_program_for(pk: str, table: Any = None) -> dict:
    if table is None:
        import os
        from services.lib.aws import table as dynamodb_table
        table = dynamodb_table(os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"), os.environ.get("AWS_REGION", "ca-central-1"))
    pointer = table.get_item(Key={"pk": pk, "sk": "program#current"}).get("Item") or {}
    ref_sk = pointer.get("ref_sk")
    if not ref_sk:
        return pointer
    return table.get_item(Key={"pk": pk, "sk": ref_sk}).get("Item") or {}
