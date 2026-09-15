from __future__ import annotations

import copy
import hashlib
import json
import os
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal


def _get_store(actor_pk):
    from program_store import ProgramStore
    return ProgramStore(table_name=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"), pk=actor_pk, region=os.environ.get("AWS_REGION", "ca-central-1"))


def _get_template_store():
    from template_store import TemplateStore
    return TemplateStore(table_name=os.environ.get("IF_TEMPLATES_TABLE_NAME", "if-health-templates"), pk=os.environ.get("IF_TEMPLATES_LIBRARY_PK", "template_library"), region=os.environ.get("AWS_REGION", "ca-central-1"))


def _get_glossary_store(actor_pk):
    from glossary_store import GlossaryStore
    return GlossaryStore(table_name=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"), pk=actor_pk, region=os.environ.get("AWS_REGION", "ca-central-1"))


def _template_phases(template: dict) -> list[dict]:
    phases = []
    for phase in template.get("phases") or []:
        if not isinstance(phase, dict):
            continue
        item = copy.deepcopy(phase)
        item["start_week"] = int(item.get("start_week", item.get("week_start", 1)) or 1)
        item["end_week"] = int(item.get("end_week", item.get("week_end", item["start_week"])) or item["start_week"])
        item.pop("week_start", None)
        item.pop("week_end", None)
        phases.append(item)
    return phases


def _new_sessions(sessions: list[dict], idempotency_key: str) -> list[dict]:
    prepared = []
    for index, session in enumerate(sessions):
        item = copy.deepcopy(session)
        blueprint_id = str(item.get("id") or item.get("session_id") or "")
        session_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"template-session:{idempotency_key}:{index}:{blueprint_id}"))
        item["id"] = session_id
        item["session_id"] = session_id
        item["status"] = "planned"
        item["completed"] = False
        prepared.append(item)
    return prepared


def _has_logged_work(session: dict) -> bool:
    if session.get("completed") or session.get("status") in {"logged", "completed", "skipped"}:
        return True
    for exercise in session.get("exercises") or []:
        if not isinstance(exercise, dict):
            continue
        if any(status != "pending" for status in (exercise.get("set_statuses") or [])):
            return True
        if exercise.get("sets_completed") or exercise.get("actual_kg") is not None:
            return True
    return False


def _idempotency_key(sk, target, start_date, week_start_day, block_id, block_name, backfilled_maxes):
    payload = json.dumps({"sk": sk, "target": target, "start_date": start_date, "week_start_day": week_start_day, "block_id": block_id, "block_name": block_name, "backfilled_maxes": backfilled_maxes}, sort_keys=True, separators=(",", ":"), default=str).encode()
    return f"template-{hashlib.sha256(payload).hexdigest()}"


async def template_apply_confirm(sk, backfilled_maxes=None, start_date=None, week_start_day=None, target="new_block", actor_pk=None, block_id=None, block_name=None, expected_revision=None, idempotency_key=None, athlete_pk=None):
    from .template_apply import check_max_resolution_gate, concretize
    from .training_weeks import normalize_week_start_day

    if target not in {"new_block", "append", "replace_incomplete"}:
        raise ValueError("target must be new_block, append, or replace_incomplete")
    if isinstance(expected_revision, bool) or not isinstance(expected_revision, int) or expected_revision < 0:
        raise ValueError("expected_revision must be a nonnegative integer")
    if not isinstance(idempotency_key, str) or not idempotency_key.strip():
        raise ValueError("idempotency_key must be a nonempty string")
    template = await _get_template_store().get_template(sk, actor_pk=actor_pk)
    if not template:
        raise ValueError(f"Template not found: {sk}")
    store = _get_store(athlete_pk or actor_pk)
    program = copy.deepcopy(await store.get_program())
    current_maxes = dict(program.get("current_maxes") or {})
    if isinstance(backfilled_maxes, dict):
        current_maxes.update(backfilled_maxes)
    start_maxes = {
        key: value for key, value in current_maxes.items()
        if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool) and value > 0
    }
    resolved_week_start = normalize_week_start_day(week_start_day, "Monday")
    start = date.fromisoformat(start_date) if start_date else date.today()
    key = idempotency_key
    payload_hash = hashlib.sha256(json.dumps({"sk": sk, "backfilled_maxes": backfilled_maxes, "start_date": start.isoformat(), "week_start_day": resolved_week_start, "target": target, "block_id": block_id, "block_name": block_name}, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
    if target == "new_block" and hasattr(store, "get_block_transition_replay"):
        replay = await store.get_block_transition_replay(key, payload_hash)
        if replay:
            result = replay["result"]
            program = replay["program"]
            return {"status": "applied", "program_version": program.get("meta", {}).get("version_label"), "program_sk": program.get("sk") or program.get("meta", {}).get("version_label"), "target": target, "block_id": result.get("next_block_id"), "preserved_sessions": replay.get("template_preserved_sessions", len(program.get("sessions") or [])), "revision": result.get("revision")}
    glossary = await _get_glossary_store(athlete_pk or actor_pk).get_glossary()
    missing = check_max_resolution_gate(template, current_maxes, glossary)
    if missing:
        raise ValueError(f"missing maxes or exercise resolution: {', '.join(missing)}")
    sessions = _new_sessions(concretize(template, current_maxes, glossary, start, resolved_week_start), idempotency_key)
    phases = _template_phases(template)
    revision = expected_revision

    if target == "new_block" and hasattr(store, "block_transition"):
        blocks = [block for block in (program.get("meta", {}).get("blocks") or []) if isinstance(block, dict)]
        active = next((block for block in blocks if block.get("status", "active") == "active"), None)
        if not blocks:
            active = {"id": "current", "status": "active"}
        completed = next((block for block in reversed(blocks) if block.get("status") == "completed"), None)
        source_id = str((active or completed or {}).get("id") or (active or completed or {}).get("block_id") or block_id or "current")
        action = "complete_and_start" if active else "start_next"
        result = await store.block_transition(action, source_id, expected_revision=revision, idempotency_key=key, name=block_name, start_date=start.isoformat(), week_start_day=resolved_week_start, start_maxes_kg=start_maxes, next_program={"phases": phases, "sessions": sessions}, template_payload_hash=payload_hash, template_preserved_sessions=len(program.get("sessions") or []))
        written = result.get("program") or {}
        return {"status": "applied", "program_version": written.get("meta", {}).get("version_label"), "program_sk": written.get("sk") or written.get("meta", {}).get("version_label"), "target": target, "block_id": result.get("next_block_id"), "preserved_sessions": len(program.get("sessions") or []), "revision": result.get("revision")}

    existing = [copy.deepcopy(item) for item in (program.get("sessions") or []) if isinstance(item, dict)]
    markers = program.setdefault("meta", {}).setdefault("template_apply_idempotency", {})
    prior = markers.get(key) if isinstance(markers, dict) else None
    if isinstance(prior, dict):
        if prior.get("payload_hash") != payload_hash:
            raise ValueError("idempotency key was used with a different payload")
        return {"status": "applied", "program_version": program.get("meta", {}).get("version_label"), "program_sk": program.get("meta", {}).get("version_label"), "target": prior.get("target", target), "block_id": prior.get("block_id"), "preserved_sessions": prior.get("preserved_sessions", len(existing)), "revision": int(program.get("meta", {}).get("revision", revision))}
    blocks = [copy.deepcopy(item) for item in (program.get("meta", {}).get("blocks") or []) if isinstance(item, dict)]
    active = next((item for item in blocks if item.get("status", "active") == "active"), None)
    target_id = str(block_id or (active or {}).get("id") or (active or {}).get("block_id") or program.get("meta", {}).get("current_block_id") or "current")
    if target != "new_block":
        target_block = next((item for item in blocks if str(item.get("id") or item.get("block_id")) == target_id), None)
        if target_block is None:
            if not blocks and target_id == "current":
                target_block = {"id": "current", "status": "active"}
            else:
                raise ValueError("block_id must identify an existing block")
        if target_block.get("status", "active") != "active":
            raise ValueError("Template sessions may only target the active block")
    incoming_dates = {str(item.get("date")) for item in sessions}
    if target == "append":
        merged = existing + sessions
    elif target == "replace_incomplete":
        logged_dates = {str(item.get("date")) for item in existing if _has_logged_work(item)}
        merged = [item for item in existing if str(item.get("date")) not in incoming_dates or _has_logged_work(item)]
        merged.extend(item for item in sessions if str(item.get("date")) not in logged_dates)
    else:
        merged = existing + sessions
    for item in sessions:
        item["block"] = "current"
        item["block_id"] = target_id
    new_program = copy.deepcopy(program)
    new_program["sessions"] = merged
    new_program.setdefault("meta", {})["template_lineage"] = {"applied_template_sk": sk, "applied_at": datetime.now(timezone.utc).isoformat(), "week_start_day": resolved_week_start, "start_date": start.isoformat()}
    new_program["meta"]["program_week_start_day"] = resolved_week_start
    starts = dict(new_program["meta"].get("block_week_start_days") or {})
    starts[target_id] = resolved_week_start
    new_program["meta"]["block_week_start_days"] = starts
    new_program["meta"].setdefault("template_apply_idempotency", {})[key] = {"payload_hash": payload_hash, "target": target, "block_id": target_id, "preserved_sessions": len(existing)}
    written = await store._write_new_version(new_program, minor=False, expected_revision=revision, idempotency_key=key)
    committed_revision = int((written.get("meta") or {}).get("revision", revision + 1)) if isinstance(written, dict) else revision + 1
    return {"status": "applied", "program_version": new_program["meta"].get("version_label"), "program_sk": new_program.get("sk") or new_program["meta"].get("version_label"), "target": target, "block_id": target_id, "preserved_sessions": len(existing), "revision": committed_revision}
