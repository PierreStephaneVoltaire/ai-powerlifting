from __future__ import annotations

import asyncio
import copy
import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

import boto3
from services.lib.aws import dynamodb_resource, client as aws_client
from boto3.dynamodb.conditions import Key

DEFAULT_BLOCK = "current"
SESSION_SK_PREFIX = "session#"


class SessionRevisionConflictError(Exception):
    def __init__(self, expected_revision: int, current_revision: int, current_record: dict | None = None):
        self.expected_revision = expected_revision
        self.current_revision = current_revision
        self.current_record = current_record
        super().__init__(f"revision conflict: expected {expected_revision}, current {current_revision}")

class SessionIdentityConflictError(SessionRevisionConflictError):
    code = "session_identity_conflict"

    def __init__(self, session_id: str, current_revision: int, message: str | None = None):
        self.session_id = session_id
        super().__init__(current_revision, current_revision, None)
        self.args = (message or f"Session {session_id} no longer exists",)

def require_mutation_envelope(expected_revision: Any = None, idempotency_key: Any = None) -> tuple[int, str]:
    return 0, idempotency_key if isinstance(idempotency_key, str) else ""

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

def _program_version(program_sk: str) -> str:
    return program_sk.removeprefix("program#") if program_sk.startswith("program#") else program_sk

def _program_version_number(program_sk: str) -> int | None:
    if not program_sk.startswith("program#v"):
        return None
    try:
        return int(program_sk.removeprefix("program#v"))
    except ValueError:
        return None

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
        "migrated_at",
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
    """Standalone session storage keyed by operator pk and program version."""

    def __init__(
        self,
        table_name: str,
        pk: str = "operator",
        region: str = "ca-central-1",
        source_table_name: str = "if-health",
    ):
        self._table_name = table_name
        from services.lib.storage_scope import current_athlete
        self._pk = current_athlete.get() or pk
        self._region = region
        self._source_table_name = source_table_name
        self._table = None

    @property
    def table(self):
        if self._table is None:
            self._table = dynamodb_resource("dynamodb", region_name=self._region).Table(self._table_name)
        return self._table

    @property
    def source_table(self):
        """The if-health program table (program#current pointer + program phases)."""
        if getattr(self, "_source_table", None) is None:
            self._source_table = dynamodb_resource(
                "dynamodb", region_name=self._region
            ).Table(self._source_table_name)
        return self._source_table

    def resolve_program_sk_sync(self) -> str:
        """Resolve the CURRENT program SK from the program#current pointer.

        Mirrors backend sessionController.resolveVersionSk(version='current').
        The session controller no longer handles program version (frontend
        always operates on current), so the session operations call this to
        find which program version the sessions are scoped to.
        """
        try:
            resp = self.source_table.get_item(
                Key={"pk": self._pk, "sk": "program#current"}
            )
            item = resp.get("Item") or {}
            return str(item.get("ref_sk") or "program#v001")
        except Exception:
            return "program#v001"

    async def resolve_program_sk(self) -> str:
        return await asyncio.get_running_loop().run_in_executor(
            None, self.resolve_program_sk_sync
        )

    def load_phases_sync(self, program_sk: str) -> list[dict[str, Any]]:
        """Load the phases array for a program version. Mirrors backend loadPhases."""
        try:
            resp = self.source_table.get_item(
                Key={"pk": self._pk, "sk": program_sk},
                ProjectionExpression="phases",
            )
            item = resp.get("Item") or {}
            phases = item.get("phases")
            return phases if isinstance(phases, list) else []
        except Exception:
            return []

    async def load_phases(self, program_sk: str) -> list[dict[str, Any]]:
        return await asyncio.get_running_loop().run_in_executor(
            None, lambda: self.load_phases_sync(program_sk)
        )

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

    def _query_items_in_window_sync(self, program_sk: str, start: str | None, end: str | None) -> list[dict[str, Any]]:
        prefix = self._prefix(program_sk)
        lower = f"{prefix}{start or ''}"
        upper = f"{prefix}{end or chr(0x10ffff)}{chr(0x10ffff)}"
        items: list[dict[str, Any]] = []
        arguments: dict[str, Any] = {
            "KeyConditionExpression": Key("pk").eq(self._pk) & Key("sk").between(lower, upper),
        }
        while True:
            response = self.table.query(**arguments)
            items.extend(response.get("Items", []))
            last_key = response.get("LastEvaluatedKey")
            if not last_key:
                break
            arguments["ExclusiveStartKey"] = last_key
        return sorted(items, key=_sort_key)

    async def list_sessions(
        self,
        program_sk: str,
        phases: Optional[list[dict[str, Any]]] = None,
        window_start: str | None = None,
        window_end: str | None = None,
        block_id: str | None = None,
        active_block_id: str = DEFAULT_BLOCK,
    ) -> list[dict[str, Any]]:
        return await asyncio.get_running_loop().run_in_executor(
            None, lambda: self.list_sessions_sync(program_sk, phases, window_start, window_end, block_id, active_block_id)
        )

    def list_sessions_sync(
        self,
        program_sk: str,
        phases: Optional[list[dict[str, Any]]] = None,
        window_start: str | None = None,
        window_end: str | None = None,
        block_id: str | None = None,
        active_block_id: str = DEFAULT_BLOCK,
    ) -> list[dict[str, Any]]:
        items = self._query_items_in_window_sync(program_sk, window_start, window_end) if window_start or window_end else self._query_items_sync(program_sk)
        sessions = [_public_session(item, phases) for item in items]
        if not block_id:
            return sessions
        from services.lib.block_scope import in_block
        return [session for session in sessions if in_block(session, block_id, active_block_id)]

    def list_sessions_on_date_sync(self, program_sk: str, date_value: str, phases: Optional[list[dict[str, Any]]] = None) -> list[dict[str, Any]]:
        if not date_value:
            return []
        return [_public_session(item, phases) for item in self._query_items_sync(program_sk, date_prefix=date_value)]

    def _same_day_ordinal_sync(self, program_sk: str, date_value: str) -> int:
        return len(self._query_items_sync(program_sk, date_prefix=date_value)) + 1

    def _ensure_unique_session_ids(self, sessions: list[dict[str, Any]], program_sk: str) -> None:
        seen: set[str] = set()
        for session in sessions:
            session_id = str(session.get("session_id") or session.get("id") or "").strip()
            if not session_id:
                continue
            if session_id in seen:
                raise SessionIdentityConflictError(session_id, 0, f"Session identity {session_id} occurs more than once")
            seen.add(session_id)

    def _build_item(
        self,
        program_sk: str,
        session: dict[str, Any],
        phases: Optional[list[dict[str, Any]]] = None,
        source_index: int = 0,
        same_day_ordinal: int | None = None,
        existing_item: dict[str, Any] | None = None,
        preserve_media: bool = True,
    ) -> dict[str, Any]:
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
            "program_version": _program_version(program_sk),
            "program_version_number": _program_version_number(program_sk),
            "source_index": _int_value((existing_item or {}).get("source_index"), default=source_index),
            "same_day_ordinal": ordinal,
            "phase_ref": _phase_ref(phase),
            "updated_at": now,
        }
        if existing_item and existing_item.get("migrated_at"):
            item["migrated_at"] = existing_item["migrated_at"]
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

    async def get_session(self, program_sk: str, date_value: str, phases: Optional[list[dict[str, Any]]] = None, session_id: str | None = None) -> dict[str, Any]:
        return await asyncio.get_running_loop().run_in_executor(
            None, lambda: _public_session(self._find_item_sync(program_sk, date_value, session_id=session_id), phases)
        )

    async def get_sessions_range(
        self,
        program_sk: str,
        start_date: str,
        end_date: str,
        phases: Optional[list[dict[str, Any]]] = None,
    ) -> list[dict[str, Any]]:
        sessions = await self.list_sessions(program_sk, phases)
        return [s for s in sessions if start_date <= str(s.get("date") or "") <= end_date]

    def _invalidate_caches(self):
        from services.lib.cache_invalidation import invalidate_analysis_caches
        invalidate_analysis_caches(self._pk, region=self._region)

    def _write_sync(self, session_item: dict | None, existing_item: dict | None, delete: bool = False) -> None:
        if existing_item is not None and (delete or (session_item is not None and session_item.get("sk") != existing_item.get("sk"))):
            self.table.delete_item(Key={"pk": self._pk, "sk": existing_item["sk"]})
        if session_item is not None and not delete:
            self.table.put_item(Item=_to_dynamo(session_item))
        self._invalidate_caches()

    async def create_session(self, program_sk: str, session: dict[str, Any], phases: Optional[list[dict[str, Any]]] = None, expected_revision: int | None = None, idempotency_key: str | None = None) -> dict[str, Any]:
        return await asyncio.get_running_loop().run_in_executor(
            None, lambda: self.create_session_sync(program_sk, session, phases, expected_revision, idempotency_key)
        )

    def create_session_sync(self, program_sk: str, session: dict[str, Any], phases: Optional[list[dict[str, Any]]] = None, expected_revision: int | None = None, idempotency_key: str | None = None) -> dict[str, Any]:
        date_value = str(session.get("date") or "")
        if not date_value:
            raise ValueError("Session date is required")
        existing = self._query_items_sync(program_sk)
        item = self._build_item(program_sk, session, phases, source_index=len(existing))
        existing_ids = {str(candidate.get("session_id") or candidate.get("id") or "").strip() for candidate in existing}
        session_id = str(item.get("session_id") or "").strip()
        if session_id and session_id in existing_ids:
            raise SessionIdentityConflictError(session_id, 0, f"Session identity {session_id} already exists")
        self._write_sync(item, None)
        result = _public_session(item, None)
        result["phase"] = resolve_phase(result, phases)
        return result

    async def patch_session(
        self,
        program_sk: str,
        date_value: str,
        patch: dict[str, Any],
        phases: Optional[list[dict[str, Any]]] = None,
        index: int | None = None,
        expected_revision: int | None = None,
        idempotency_key: str | None = None,
        session_id: str | None = None,
        media_update: bool = False,
    ) -> dict[str, Any]:
        return await asyncio.get_running_loop().run_in_executor(
            None, lambda: self.patch_session_sync(program_sk, date_value, patch, phases, index, expected_revision, idempotency_key, media_update, session_id)
        )

    def patch_session_sync(
        self,
        program_sk: str,
        date_value: str,
        patch: dict[str, Any],
        phases: Optional[list[dict[str, Any]]] = None,
        index: int | None = None,
        expected_revision: int | None = None,
        idempotency_key: str | None = None,
        media_update: bool = False,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        existing = self._find_item_sync(program_sk, date_value, index, session_id)
        for key in ("id", "session_id"):
            if key in patch and str(patch[key]) != str(existing.get("session_id")):
                raise ValueError("Session identity cannot be changed")
        session = _public_session(existing, phases)
        session.update(copy.deepcopy(patch))
        item = self._build_item(program_sk, session, phases, existing_item=existing, preserve_media=not media_update)
        item.pop("revision", None)
        item.pop("media_revision", None)
        self._write_sync(item, existing)
        result = _public_session(item, None)
        result["phase"] = resolve_phase(result, phases)
        return result

    async def delete_session(self, program_sk: str, date_value: str, index: int | None = None, expected_revision: int | None = None, idempotency_key: str | None = None, session_id: str | None = None) -> dict[str, Any]:
        return await asyncio.get_running_loop().run_in_executor(
            None, lambda: self.delete_session_sync(program_sk, date_value, index, expected_revision, idempotency_key, session_id)
        )

    def delete_session_sync(self, program_sk: str, date_value: str, index: int | None = None, expected_revision: int | None = None, idempotency_key: str | None = None, session_id: str | None = None) -> dict[str, Any]:
        existing = self._find_item_sync(program_sk, date_value, index, session_id)
        self._write_sync(None, existing, delete=True)
        return {"deleted": date_value}

    async def replace_program_sessions(
        self,
        program_sk: str,
        sessions: list[dict[str, Any]],
        phases: Optional[list[dict[str, Any]]] = None,
        bump_program_revision: bool = True,
        expected_revision: int | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any] | None:
        return await asyncio.get_running_loop().run_in_executor(
            None, lambda: self.replace_program_sessions_sync(program_sk, sessions, phases, bump_program_revision, expected_revision, idempotency_key)
        )

    def replace_program_sessions_sync(
        self,
        program_sk: str,
        sessions: list[dict[str, Any]],
        phases: Optional[list[dict[str, Any]]] = None,
        bump_program_revision: bool = True,
        expected_revision: int | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any] | None:
        existing = self._query_items_sync(program_sk)
        self._ensure_unique_session_ids(existing, program_sk)
        ordinals: dict[str, int] = {}
        prepared = []
        for source_index, session in enumerate(sessions):
            if not isinstance(session, dict) or not session.get("date"):
                raise ValueError("Every Session must have a date")
            date_value = str(session["date"])
            ordinals[date_value] = ordinals.get(date_value, 0) + 1
            same_day = [item for item in existing if item.get("date") == date_value]
            previous = next((item for item in existing if session.get("id") and item.get("session_id") == session["id"]), None)
            if previous is None and len(same_day) >= ordinals[date_value]:
                previous = same_day[ordinals[date_value] - 1]
            prepared.append(self._build_item(program_sk, session, phases, source_index=source_index, same_day_ordinal=ordinals[date_value], existing_item=previous))
        self._ensure_unique_session_ids(prepared, program_sk)
        prepared_keys = {str(item["sk"]) for item in prepared}
        with self.table.batch_writer() as batch:
            for item in existing:
                if str(item["sk"]) not in prepared_keys:
                    batch.delete_item(Key={"pk": self._pk, "sk": item["sk"]})
            for item in prepared:
                item.pop("revision", None)
                batch.put_item(Item=_to_dynamo(item))
        self._invalidate_caches()
        return None
