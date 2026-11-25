from __future__ import annotations

import copy
import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from services.runtime.aws import dynamodb_resource
from boto3.dynamodb.conditions import Key

DEFAULT_BLOCK = "current"
SESSION_SK_PREFIX = "session#"


def _to_dynamo(obj: Any) -> Any:
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: _to_dynamo(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_dynamo(v) for v in obj]
    return obj

def _int_value(value: Any, default: int = 0) -> int:
    if isinstance(value, Decimal):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default

def parse_week_number(session: dict[str, Any]) -> int:
    raw_week_number = session.get("week_number")
    parsed = _int_value(raw_week_number, default=-1)
    if parsed >= 0:
        return parsed

    week = session.get("week")
    if isinstance(week, str):
        match = re.search(r"W(\d+)", week, flags=re.IGNORECASE)
        if match:
            return int(match.group(1))
    return _int_value(week)

def _phase_block(phase: dict[str, Any]) -> str:
    return str(phase.get("block") or DEFAULT_BLOCK)

def resolve_phase(session: dict[str, Any], phases: Optional[list[dict[str, Any]]] = None) -> dict[str, Any]:
    week_number = parse_week_number(session)
    block = str(session.get("block") or DEFAULT_BLOCK)

    if phases is not None:
        for phase in phases:
            if not isinstance(phase, dict) or _phase_block(phase) != block:
                continue
            start_week = _int_value(phase.get("start_week"))
            end_week = _int_value(phase.get("end_week"))
            if start_week <= week_number <= end_week:
                return copy.deepcopy(phase)
        
        return {
            "name": "Unscheduled",
            "intent": "",
            "start_week": week_number,
            "end_week": week_number,
            "block": block,
        }

    existing_phase = session.get("phase")
    if isinstance(existing_phase, dict) and existing_phase:
        phase = copy.deepcopy(existing_phase)
        phase.setdefault("block", block)
        return phase
    if isinstance(existing_phase, str) and existing_phase:
        return {
            "name": existing_phase,
            "intent": "",
            "start_week": week_number,
            "end_week": week_number,
            "block": block,
        }

    return {
        "name": "Unscheduled",
        "intent": "",
        "start_week": week_number,
        "end_week": week_number,
        "block": block,
    }

def _phase_ref(phase: dict[str, Any]) -> str:
    block = str(phase.get("block") or DEFAULT_BLOCK)
    name = str(phase.get("name") or "Unscheduled").replace("#", "-")
    return f"phase#{block}#W{phase.get('start_week', 0)}-W{phase.get('end_week', 0)}#{name}"

def _sanitize_decimals(obj):
    if isinstance(obj, Decimal):
        return float(obj) if obj % 1 > 0 else int(obj)
    if isinstance(obj, dict):
        return {k: _sanitize_decimals(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_decimals(v) for v in obj]
    return obj


def _public_session(item: dict[str, Any], phases: Optional[list[dict[str, Any]]] = None) -> dict[str, Any]:
    session = _sanitize_decimals(copy.deepcopy(item))
    if "session_id" in session and "id" not in session:
        session["id"] = str(session["session_id"])
    for key in (
        "pk",
        "sk",
        "entity_type",
        "source_pk",
        "source_table",
        "program_sk",
        "program_version",
        "program_version_number",
        "source_index",
        "same_day_ordinal",
        "phase_ref",
        "session_id",
    ):
        session.pop(key, None)

    phase = resolve_phase(session, phases)
    session["week_number"] = parse_week_number(session)
    session["block"] = str(session.get("block") or DEFAULT_BLOCK)
    session["block_id"] = str(session.get("block_id") or session["block"])
    session["phase"] = phase
    session["phase_name"] = str(phase.get("name") or "Unscheduled")
    return session

def _sort_key(item: dict[str, Any]) -> tuple[str, int, int, str]:
    return (
        str(item.get("date") or ""),
        _int_value(item.get("same_day_ordinal"), default=0),
        _int_value(item.get("source_index"), default=0),
        str(item.get("sk") or ""),
    )

class SessionStore:
    def __init__(
        self,
        table_name: str,
        pk: str = "operator",
        region: str = "ca-central-1",
        source_table_name: str = "if-health"):
        self._table_name = table_name
        from services.runtime.storage_scope import current_athlete
        self._pk = current_athlete.get() or pk
        self._region = region
        self._source_table_name = source_table_name
        self._table = None

    @property
    def table(self):
        if self._table is None:
            self._table = dynamodb_resource("dynamodb", region_name=self._region).Table(self._table_name)
        return self._table

    def _prefix(self, program_sk: str) -> str:
        return f"{SESSION_SK_PREFIX}{program_sk}#"

    def _query_items_sync(self, program_sk: str, date_prefix: str | None = None) -> list[dict[str, Any]]:
        prefix = self._prefix(program_sk)
        if date_prefix:
            prefix = f"{prefix}{date_prefix}#"

        items: list[dict[str, Any]] = []
        kwargs: dict[str, Any] = {
            "KeyConditionExpression": Key("pk").eq(self._pk) & Key("sk").begins_with(prefix),
        }
        while True:
            response = self.table.query(**kwargs)
            items.extend(response.get("Items", []))
            last_key = response.get("LastEvaluatedKey")
            if not last_key:
                break
            kwargs["ExclusiveStartKey"] = last_key
        return sorted(items, key=_sort_key)

    def list_sessions_sync(self, program_sk: str, phases: Optional[list[dict[str, Any]]] = None) -> list[dict[str, Any]]:
        return [_public_session(item, phases) for item in self._query_items_sync(program_sk)]

    def list_sessions_on_date_sync(self, program_sk: str, date_value: str, phases: Optional[list[dict[str, Any]]] = None) -> list[dict[str, Any]]:
        if not date_value:
            return []
        return [_public_session(item, phases) for item in self._query_items_sync(program_sk, date_prefix=date_value)]

    def _same_day_ordinal_sync(self, program_sk: str, date_value: str) -> int:
        return len(self._query_items_sync(program_sk, date_prefix=date_value)) + 1

    def _build_item(
        self,
        program_sk: str,
        session: dict[str, Any],
        phases: Optional[list[dict[str, Any]]] = None,
        source_index: int = 0,
        same_day_ordinal: int | None = None,
        existing_item: dict[str, Any] | None = None,
        preserve_media: bool = True) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        session_copy = copy.deepcopy(session)
        date_value = str(session_copy.get("date") or "undated")
        session_id = str((existing_item or {}).get("session_id") or session_copy.get("id") or session_copy.get("session_id") or uuid.uuid4())
        ordinal = same_day_ordinal or _int_value((existing_item or {}).get("same_day_ordinal"), default=0)
        if ordinal <= 0:
            ordinal = self._same_day_ordinal_sync(program_sk, date_value)

        block = str(session_copy.get("block") or DEFAULT_BLOCK)
        block_id = str(session_copy.get("block_id") or block)
        status = str(session_copy.get("status") or ("completed" if session_copy.get("completed") else "planned"))
        completed = bool(session_copy.get("completed")) or status in {"logged", "completed"}
        phase = resolve_phase({**session_copy, "block": block}, phases)
        planned_exercises = session_copy.get("planned_exercises")

        session_copy.update({
            "id": session_id,
            "session_id": session_id,
            "date": date_value,
            "block": block,
            "block_id": block_id,
            "status": status,
            "completed": completed,
            "week_number": parse_week_number(session_copy),
            "phase": phase,
            "phase_name": str(phase.get("name") or "Unscheduled"),
            "planned_exercises": planned_exercises if isinstance(planned_exercises, list) else [],
        })
        if existing_item is not None and preserve_media:
            if "videos" in existing_item:
                session_copy["videos"] = copy.deepcopy(existing_item["videos"])
            else:
                session_copy.pop("videos", None)
            if "media_revision" in existing_item:
                session_copy["media_revision"] = existing_item["media_revision"]
            else:
                session_copy.pop("media_revision", None)
        for exercise in session_copy.get("exercises", []):
            if not isinstance(exercise, dict):
                continue
            count = _int_value(exercise.get("sets"), 0)
            ids = exercise.get("set_ids") if isinstance(exercise.get("set_ids"), list) else []
            exercise["set_ids"] = [str(ids[i]) if i < len(ids) and ids[i] else str(uuid.uuid4()) for i in range(count)]

        sk = (existing_item or {}).get("sk")
        preserve_sk = bool(sk and f"#{date_value}#" in str(sk))
        if not preserve_sk:
            ordinal = same_day_ordinal or self._same_day_ordinal_sync(program_sk, date_value)
            sk = f"{self._prefix(program_sk)}{date_value}#{ordinal:03d}#{session_id}"

        item = {
            **session_copy,
            "pk": self._pk,
            "sk": sk,
            "entity_type": "session",
            "source_pk": self._pk,
            "source_table": self._source_table_name,
            "program_sk": program_sk,
            "source_index": _int_value((existing_item or {}).get("source_index"), default=source_index),
            "same_day_ordinal": ordinal,
            "phase_ref": _phase_ref(phase),
            "updated_at": now,
        }
        return item

    def _find_item_sync(self, program_sk: str, date_value: str, index: int | None = None, session_id: str | None = None) -> dict[str, Any]:
        items = self._query_items_sync(program_sk)
        if session_id:
            matches = [item for item in items if str(item.get("session_id") or item.get("id") or "") == session_id]
            if len(matches) == 1:
                return matches[0]
            if len(matches) > 1:
                raise ValueError(f"Session identity {session_id} is ambiguous")
            raise ValueError(f"Session {session_id} no longer exists")
        if index is not None:
            dated_items = [item for item in items if str(item.get("date") or "") == date_value]
            if index < 0 or index >= len(dated_items):
                raise ValueError(f"Session at index {index} not found")
            return dated_items[index]
        dated_items = [item for item in items if str(item.get("date") or "") == date_value]
        if len(dated_items) == 1:
            return dated_items[0]
        if len(dated_items) > 1:
            raise ValueError(f"Several Sessions are on {date_value}; choose one by id")
        raise ValueError(f"Session not found with date={date_value}")

    def _write_sync(self, session_item: dict | None, existing_item: dict | None, delete: bool = False) -> None:
        if existing_item is not None and (delete or (session_item is not None and session_item.get("sk") != existing_item.get("sk"))):
            self.table.delete_item(Key={"pk": self._pk, "sk": existing_item["sk"]})
        if session_item is not None and not delete:
            self.table.put_item(Item=_to_dynamo(session_item))

    def patch_session_sync(
        self,
        program_sk: str,
        date_value: str,
        patch: dict[str, Any],
        phases: Optional[list[dict[str, Any]]] = None,
        index: int | None = None,
        media_update: bool = False,
        session_id: str | None = None) -> dict[str, Any]:
        existing = self._find_item_sync(program_sk, date_value, index, session_id)
        for key in ("id", "session_id"):
            if key in patch and str(patch[key]) != str(existing.get("session_id")):
                raise ValueError("Session identity cannot be changed")
        session = _public_session(existing, phases)
        session.update(copy.deepcopy(patch))
        item = self._build_item(program_sk, session, phases, existing_item=existing, preserve_media=not media_update)
        item.pop("media_revision", None)
        self._write_sync(item, existing)
        result = _public_session(item, None)
        result["phase"] = resolve_phase(result, phases)
        return result
