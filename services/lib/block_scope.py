from __future__ import annotations

from typing import Any, Iterable

ACTIVE = "current"
ALL_BLOCKS = "all"
BLOCK_SCOPED_RECORD_FIELDS = ("diet_notes", "supplements", "supplement_phases", "competitions")
SCOPED_PROGRAM_LISTS = ("phases", "sessions", *BLOCK_SCOPED_RECORD_FIELDS)


def current_block_id(program: dict | None) -> str:
    meta = (program or {}).get("meta") or {}
    return str(meta.get("current_block_id") or ACTIVE)


def resolve_block_id(program: dict | None, block_id: str | None) -> str:
    if not block_id or block_id == ACTIVE:
        return current_block_id(program)
    return str(block_id)


def record_block_key(record: dict) -> str:
    return str(record.get("block_id") or record.get("block") or ACTIVE)


def in_block(record: Any, block_id: str, active_block_id: str) -> bool:
    if not isinstance(record, dict):
        return False
    key = record_block_key(record)
    if block_id == active_block_id:
        return key in {active_block_id, ACTIVE}
    return key == block_id


def scope_entries(entries: Iterable[Any] | None, block_id: str, active_block_id: str) -> list:
    return [entry for entry in entries or [] if in_block(entry, block_id, active_block_id)]


def scope_program(program: dict, block_id: str | None = None) -> dict:
    active = current_block_id(program)
    target = resolve_block_id(program, block_id)
    scoped = dict(program)
    for field in SCOPED_PROGRAM_LISTS:
        if isinstance(program.get(field), list):
            scoped[field] = scope_entries(program[field], target, active)
    meta = program.get("meta")
    if isinstance(meta, dict) and isinstance(meta.get("block_notes"), list):
        scoped["meta"] = {**meta, "block_notes": scope_entries(meta["block_notes"], target, active)}
    if isinstance(program.get("weight_log"), list):
        scoped["weight_log"] = scope_entries(program["weight_log"], target, active)
    return scoped


def stamp(record: dict, program: dict | None) -> dict:
    if not record.get("block_id"):
        record["block_id"] = current_block_id(program)
    return record


def active_block_id_for(pk: str, table: Any = None) -> str:
    if table is None:
        import os
        from services.lib.aws import table as dynamodb_table
        table = dynamodb_table(os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"), os.environ.get("AWS_REGION", "ca-central-1"))
    pointer = table.get_item(Key={"pk": pk, "sk": "program#current"}).get("Item") or {}
    if pointer.get("current_block_id"):
        return str(pointer["current_block_id"])
    if not pointer.get("ref_sk"):
        return ACTIVE
    program = table.get_item(Key={"pk": pk, "sk": pointer["ref_sk"]}).get("Item") or {}
    return current_block_id(program)
