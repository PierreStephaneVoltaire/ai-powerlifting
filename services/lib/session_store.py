from __future__ import annotations

import asyncio
import copy
import hashlib
import json
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

def require_mutation_envelope(expected_revision: Any, idempotency_key: Any) -> tuple[int, str]:
    if isinstance(expected_revision, bool) or not isinstance(expected_revision, int) or expected_revision < 0:
        raise ValueError("expected_revision must be a nonnegative integer")
    if not isinstance(idempotency_key, str) or not idempotency_key.strip():
        raise ValueError("idempotency_key must be a nonempty string")
    return expected_revision, idempotency_key

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

    def _ensure_unique_session_ids(self, sessions: list[dict[str, Any]], program_sk: str, current_revision: int | None = None) -> None:
        seen: set[str] = set()
        for session in sessions:
            session_id = str(session.get("session_id") or session.get("id") or "").strip()
            if not session_id:
                continue
            if session_id in seen:
                revision = current_revision if current_revision is not None else self._current_revision_sync(program_sk)
                raise SessionIdentityConflictError(session_id, revision, f"Session identity {session_id} occurs more than once")
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

    def _current_revision_sync(self, program_sk: str) -> int:
        pointer = self.source_table.get_item(Key={"pk": self._pk, "sk": "program#current"}, ConsistentRead=True).get("Item") or {}
        if str(pointer.get("ref_sk")) == program_sk:
            return _int_value(pointer.get("revision"), 0)
        program = self.source_table.get_item(Key={"pk": self._pk, "sk": program_sk}, ConsistentRead=True).get("Item") or {}
        meta = program.get("meta") if isinstance(program.get("meta"), dict) else {}
        return _int_value(meta.get("revision"), 0)

    def _find_item_sync(self, program_sk: str, date_value: str, index: int | None = None, session_id: str | None = None) -> dict[str, Any]:
        items = self._query_items_sync(program_sk)
        if session_id:
            matches = [item for item in items if str(item.get("session_id") or item.get("id") or "") == session_id]
            if len(matches) == 1:
                return matches[0]
            revision = self._current_revision_sync(program_sk)
            if len(matches) > 1:
                raise SessionIdentityConflictError(session_id, revision, f"Session identity {session_id} is ambiguous")
            raise SessionIdentityConflictError(session_id, revision)
        if index is not None:
            dated_items = [item for item in items if str(item.get("date") or "") == date_value]
            if index < 0 or index >= len(dated_items):
                raise ValueError(f"Session at index {index} not found")
            return dated_items[index]
        dated_items = [item for item in items if str(item.get("date") or "") == date_value]
        if len(dated_items) == 1:
            return dated_items[0]
        if len(dated_items) > 1:
            revision = self._current_revision_sync(program_sk)
            raise SessionRevisionConflictError(revision, revision, None)
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

    def _revision_context_sync(self, program_sk: str, expected_revision: int | None) -> tuple[dict, dict | None, bool, int, int]:
        program_response = self.source_table.get_item(
            Key={"pk": self._pk, "sk": program_sk},
            ConsistentRead=True,
        )
        program = program_response.get("Item")
        pointer_response = self.source_table.get_item(
            Key={"pk": self._pk, "sk": "program#current"},
            ConsistentRead=True,
        )
        pointer = pointer_response.get("Item")
        current = bool(pointer and str(pointer.get("ref_sk")) == program_sk)
        if current:
            current_revision = _int_value(pointer.get("revision"), 0)
        else:
            meta = program.get("meta") if isinstance(program, dict) else {}
            current_revision = _int_value(meta.get("revision") if isinstance(meta, dict) else 0, 0)
        expected = current_revision if expected_revision is None else int(expected_revision)
        if expected != current_revision:
            raise SessionRevisionConflictError(expected, current_revision, copy.deepcopy(program))
        if not isinstance(program, dict):
            raise ValueError(f"Program not found: {program_sk}")
        return program, pointer, current, current_revision, expected + 1

    @staticmethod
    def _transaction_item(item: dict[str, Any]) -> dict[str, Any]:
        return {key: _to_dynamo(value) for key, value in item.items()}

    @staticmethod
    def _transaction_value(value: Any) -> dict[str, Any]:
        return _to_dynamo(value)

    @staticmethod
    def _transaction_key(key: dict[str, Any]) -> dict[str, Any]:
        return SessionStore._transaction_item(key)

    def _idempotency_sk(self, program_sk: str, idempotency_key: str) -> str:
        digest = hashlib.sha256(idempotency_key.encode()).hexdigest()[:32]
        return f"session-idempotency#{program_sk}#{digest}"

    def _load_idempotency_sync(self, program_sk: str, idempotency_key: str) -> dict | None:
        if not idempotency_key:
            return None
        return self.source_table.get_item(
            Key={"pk": self._pk, "sk": self._idempotency_sk(program_sk, idempotency_key)},
            ConsistentRead=True,
        ).get("Item")

    def _replay_sync(self, program_sk: str, idempotency_key: str | None, payload: dict) -> dict | None:
        if not idempotency_key:
            return None
        marker = self._load_idempotency_sync(program_sk, idempotency_key)
        if not marker:
            return None
        payload_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()
        if marker.get("payload_hash") != payload_hash:
            raise ValueError("idempotency key was used with a different payload")
        return copy.deepcopy(marker.get("result") or {})

    def _transaction_mutation_sync(
        self,
        program_sk: str,
        operation: str,
        payload: dict,
        session_item: dict | None,
        existing_item: dict | None,
        expected_revision: int | None,
        idempotency_key: str | None,
        delete: bool = False,
        session_operations: list[dict[str, Any]] | None = None,
    ) -> dict:
        marker = self._load_idempotency_sync(program_sk, idempotency_key or "")
        payload_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()
        if marker:
            if marker.get("payload_hash") != payload_hash:
                raise ValueError("idempotency key was used with a different payload")
            return copy.deepcopy(marker.get("result") or {})

        program, pointer, current, current_revision, next_revision = self._revision_context_sync(program_sk, expected_revision)
        program_record = copy.deepcopy(program)
        program_meta = program_record.get("meta")
        if not isinstance(program_meta, dict):
            program_meta = {}
            program_record["meta"] = program_meta
        program_meta["revision"] = next_revision
        program_meta["updated_at"] = datetime.now(timezone.utc).isoformat()
        transactions: list[dict[str, Any]] = []
        if session_operations is not None:
            transactions.extend(session_operations)
        elif delete:
            media_revision = _int_value(existing_item.get("media_revision"), 0)
            transactions.append({
                "Delete": {
                    "TableName": self._table_name,
                    "Key": self._transaction_key({"pk": self._pk, "sk": existing_item["sk"]}),
                    "ConditionExpression": "attribute_exists(#pk) AND ((attribute_not_exists(#revision) AND :existing_revision = :zero) OR #revision = :existing_revision) AND ((attribute_not_exists(#media_revision) AND :existing_media_revision = :zero) OR #media_revision = :existing_media_revision)",
                    "ExpressionAttributeNames": {"#pk": "pk", "#revision": "revision", "#media_revision": "media_revision"},
                    "ExpressionAttributeValues": {":existing_revision": self._transaction_value(_int_value(existing_item.get("revision"), 0)), ":existing_media_revision": self._transaction_value(media_revision), ":zero": self._transaction_value(0)},
                }
            })
        elif session_item is not None and existing_item is not None and session_item.get("sk") != existing_item.get("sk"):
            session_item = copy.deepcopy(session_item)
            session_item["revision"] = next_revision
            transactions.append({
                "Put": {
                    "TableName": self._table_name,
                    "Item": self._transaction_item(session_item),
                    "ConditionExpression": "attribute_not_exists(#pk)",
                    "ExpressionAttributeNames": {"#pk": "pk"},
                }
            })
            transactions.append({
                "Delete": {
                    "TableName": self._table_name,
                    "Key": self._transaction_key({"pk": self._pk, "sk": existing_item["sk"]}),
                    "ConditionExpression": "((attribute_not_exists(#revision) AND :existing_revision = :zero) OR #revision = :existing_revision) AND ((attribute_not_exists(#media_revision) AND :existing_media_revision = :zero) OR #media_revision = :existing_media_revision)",
                    "ExpressionAttributeNames": {"#revision": "revision", "#media_revision": "media_revision"},
                    "ExpressionAttributeValues": {":existing_revision": self._transaction_value(_int_value(existing_item.get("revision"), 0)), ":existing_media_revision": self._transaction_value(_int_value(existing_item.get("media_revision"), 0)), ":zero": self._transaction_value(0)},
                }
            })
        elif session_item is not None:
            session_item = copy.deepcopy(session_item)
            session_item["revision"] = next_revision
            condition = "attribute_not_exists(#pk)" if existing_item is None else "((attribute_not_exists(#revision) AND :existing_revision = :zero) OR #revision = :existing_revision) AND ((attribute_not_exists(#media_revision) AND :existing_media_revision = :zero) OR #media_revision = :existing_media_revision)"
            values = {} if existing_item is None else {":existing_revision": self._transaction_value(_int_value(existing_item.get("revision"), 0)), ":existing_media_revision": self._transaction_value(_int_value(existing_item.get("media_revision"), 0)), ":zero": self._transaction_value(0)}
            transactions.append({
                "Put": {
                    "TableName": self._table_name,
                    "Item": self._transaction_item(session_item or {}),
                    "ConditionExpression": condition,
                    "ExpressionAttributeNames": ({"#pk": "pk"} if existing_item is None else {"#revision": "revision", "#media_revision": "media_revision"}),
                    **({"ExpressionAttributeValues": values} if values else {}),
                }
            })
        if current:
            transactions.append({
                "Update": {
                    "TableName": self._source_table_name,
                    "Key": self._transaction_key({"pk": self._pk, "sk": "program#current"}),
                    "UpdateExpression": "SET #revision = :next_revision, #updated_at = :updated_at",
                    "ConditionExpression": "#ref_sk = :program_sk AND ((attribute_not_exists(#revision) AND :expected_revision = :zero) OR #revision = :expected_revision)",
                    "ExpressionAttributeNames": {"#ref_sk": "ref_sk", "#revision": "revision", "#updated_at": "updated_at"},
                    "ExpressionAttributeValues": {
                        ":program_sk": self._transaction_value(program_sk),
                        ":expected_revision": self._transaction_value(current_revision),
                        ":zero": self._transaction_value(0),
                        ":next_revision": self._transaction_value(next_revision),
                        ":updated_at": self._transaction_value(program_meta["updated_at"]),
                    },
                }
            })
        program_record["pk"] = self._pk
        program_record["sk"] = program_sk
        transactions.append({
            "Put": {
                "TableName": self._source_table_name,
                "Item": self._transaction_item(program_record),
                "ConditionExpression": "attribute_exists(#pk) AND (attribute_not_exists(#meta.#revision) OR #meta.#revision = :expected_revision)",
                "ExpressionAttributeNames": {"#pk": "pk", "#meta": "meta", "#revision": "revision"},
                "ExpressionAttributeValues": {":expected_revision": self._transaction_value(current_revision)},
            }
        })
        if operation == "replace_all":
            result = {"success": True, "revision": next_revision}
        elif session_item is not None:
            result = _public_session(session_item, None)
        else:
            result = {"deleted": str(payload.get("date") or ""), "revision": next_revision}
        if idempotency_key:
            marker_item = {
                "pk": self._pk,
                "sk": self._idempotency_sk(program_sk, idempotency_key),
                "entity_type": "session_idempotency",
                "operation": operation,
                "payload_hash": payload_hash,
                "result": result,
                "revision": next_revision,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            transactions.append({
                "Put": {
                    "TableName": self._source_table_name,
                    "Item": self._transaction_item(marker_item),
                    "ConditionExpression": "attribute_not_exists(#pk)",
                    "ExpressionAttributeNames": {"#pk": "pk"},
                }
            })
        try:
            self.source_table.meta.client.transact_write_items(TransactItems=transactions)
        except Exception as exc:
            marker = self._load_idempotency_sync(program_sk, idempotency_key or "")
            if marker and marker.get("payload_hash") == payload_hash:
                return copy.deepcopy(marker.get("result") or {})
            if exc.__class__.__name__ == "TransactionCanceledException":
                if current:
                    pointer_now = self.source_table.get_item(Key={"pk": self._pk, "sk": "program#current"}, ConsistentRead=True).get("Item") or {}
                    now_revision = _int_value(pointer_now.get("revision"), current_revision)
                else:
                    program_now = self.source_table.get_item(Key={"pk": self._pk, "sk": program_sk}, ConsistentRead=True).get("Item") or {}
                    meta_now = program_now.get("meta") if isinstance(program_now.get("meta"), dict) else {}
                    now_revision = _int_value(meta_now.get("revision"), current_revision)
                raise SessionRevisionConflictError(current_revision, now_revision, copy.deepcopy(program)) from exc
            raise
        self._invalidate_caches()
        return result

    async def create_session(self, program_sk: str, session: dict[str, Any], phases: Optional[list[dict[str, Any]]] = None, expected_revision: int | None = None, idempotency_key: str | None = None) -> dict[str, Any]:
        return await asyncio.get_running_loop().run_in_executor(
            None, lambda: self.create_session_sync(program_sk, session, phases, expected_revision, idempotency_key)
        )

    def create_session_sync(self, program_sk: str, session: dict[str, Any], phases: Optional[list[dict[str, Any]]] = None, expected_revision: int | None = None, idempotency_key: str | None = None) -> dict[str, Any]:
        require_mutation_envelope(expected_revision, idempotency_key)
        date_value = str(session.get("date") or "")
        if not date_value:
            raise ValueError("Session date is required")
        replay = self._replay_sync(program_sk, idempotency_key, {"session": session})
        if replay is not None:
            replay["phase"] = resolve_phase(replay, phases)
            return replay
        item = self._build_item(program_sk, session, phases, source_index=len(self._query_items_sync(program_sk)))
        existing_ids = {
            str(candidate.get("session_id") or candidate.get("id") or "").strip()
            for candidate in self._query_items_sync(program_sk)
        }
        session_id = str(item.get("session_id") or "").strip()
        if session_id and session_id in existing_ids:
            raise SessionIdentityConflictError(session_id, self._current_revision_sync(program_sk), f"Session identity {session_id} already exists")
        result = self._transaction_mutation_sync(
            program_sk, "create", {"session": session}, item, None, expected_revision, idempotency_key,
        )
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
        require_mutation_envelope(expected_revision, idempotency_key)
        payload = {"date": date_value, "index": index, "session_id": session_id, "patch": patch}
        replay = self._replay_sync(program_sk, idempotency_key, payload)
        if replay is not None:
            replay["phase"] = resolve_phase(replay, phases)
            return replay
        existing = self._find_item_sync(program_sk, date_value, index, session_id)
        for key in ("id", "session_id"):
            if key in patch and str(patch[key]) != str(existing.get("session_id")):
                raise ValueError("Session identity cannot be changed")
        session = _public_session(existing, phases)
        session.update(copy.deepcopy(patch))
        item = self._build_item(program_sk, session, phases, existing_item=existing, preserve_media=not media_update)
        if media_update:
            item["media_revision"] = _int_value(existing.get("media_revision"), 0) + 1
        item["revision"] = _int_value(existing.get("revision"), 0) + 1
        result = self._transaction_mutation_sync(
            program_sk, "patch", payload, item, existing, expected_revision, idempotency_key,
        )
        result["phase"] = resolve_phase(result, phases)
        return result

    async def delete_session(self, program_sk: str, date_value: str, index: int | None = None, expected_revision: int | None = None, idempotency_key: str | None = None, session_id: str | None = None) -> dict[str, Any]:
        return await asyncio.get_running_loop().run_in_executor(
            None, lambda: self.delete_session_sync(program_sk, date_value, index, expected_revision, idempotency_key, session_id)
        )

    def delete_session_sync(self, program_sk: str, date_value: str, index: int | None = None, expected_revision: int | None = None, idempotency_key: str | None = None, session_id: str | None = None) -> dict[str, Any]:
        require_mutation_envelope(expected_revision, idempotency_key)
        replay = self._replay_sync(program_sk, idempotency_key, {"date": date_value, "index": index, "session_id": session_id})
        if replay is not None:
            return replay
        existing = self._find_item_sync(program_sk, date_value, index, session_id)
        return self._transaction_mutation_sync(
            program_sk, "delete", {"date": date_value, "index": index, "session_id": session_id}, None, existing, expected_revision, idempotency_key, delete=True,
        )

    async def replace_program_sessions(
        self,
        program_sk: str,
        sessions: list[dict[str, Any]],
        phases: Optional[list[dict[str, Any]]] = None,
        bump_program_revision: bool = True,
        expected_revision: int | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any] | None:
        if bump_program_revision:
            require_mutation_envelope(expected_revision, idempotency_key)
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
        if bump_program_revision:
            require_mutation_envelope(expected_revision, idempotency_key)
        existing = self._query_items_sync(program_sk)
        current_revision = self._current_revision_sync(program_sk) if bump_program_revision else None
        self._ensure_unique_session_ids(existing, program_sk, current_revision)
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
        self._ensure_unique_session_ids(prepared, program_sk, current_revision)
        if not bump_program_revision:
            with self.table.batch_writer() as batch:
                for item in existing:
                    batch.delete_item(Key={"pk": self._pk, "sk": item["sk"]})
                for item in prepared:
                    batch.put_item(Item=_to_dynamo(item))
        else:
            _, _, _, current_revision, next_revision = self._revision_context_sync(program_sk, expected_revision)
            existing_by_sk = {str(item["sk"]): item for item in existing}
            prepared_keys = {str(item["sk"]) for item in prepared}
            operations: list[dict[str, Any]] = []
            for item in existing:
                if str(item["sk"]) in prepared_keys:
                    continue
                operations.append({
                    "Delete": {
                        "TableName": self._table_name,
                        "Key": self._transaction_key({"pk": self._pk, "sk": item["sk"]}),
                        "ConditionExpression": "((attribute_not_exists(#revision) AND :existing_revision = :zero) OR #revision = :existing_revision) AND ((attribute_not_exists(#media_revision) AND :existing_media_revision = :zero) OR #media_revision = :existing_media_revision)",
                        "ExpressionAttributeNames": {"#revision": "revision", "#media_revision": "media_revision"},
                        "ExpressionAttributeValues": {":existing_revision": self._transaction_value(_int_value(item.get("revision"), 0)), ":existing_media_revision": self._transaction_value(_int_value(item.get("media_revision"), 0)), ":zero": self._transaction_value(0)},
                    }
                })
            for item in prepared:
                item["revision"] = next_revision
                previous = existing_by_sk.get(str(item["sk"]))
                if previous is None:
                    condition = "attribute_not_exists(#pk)"
                    names = {"#pk": "pk"}
                    values = {}
                else:
                    condition = "((attribute_not_exists(#revision) AND :existing_revision = :zero) OR #revision = :existing_revision) AND ((attribute_not_exists(#media_revision) AND :existing_media_revision = :zero) OR #media_revision = :existing_media_revision)"
                    names = {"#revision": "revision", "#media_revision": "media_revision"}
                    values = {":existing_revision": self._transaction_value(_int_value(previous.get("revision"), 0)), ":existing_media_revision": self._transaction_value(_int_value(previous.get("media_revision"), 0)), ":zero": self._transaction_value(0)}
                operations.append({
                    "Put": {
                        "TableName": self._table_name,
                        "Item": self._transaction_item(item),
                        "ConditionExpression": condition,
                        "ExpressionAttributeNames": names,
                        **({"ExpressionAttributeValues": values} if values else {}),
                    }
                })
            if len(operations) > (97 if idempotency_key else 98):
                raise ValueError("Session replacement exceeds the atomic DynamoDB transaction limit")
            result = self._transaction_mutation_sync(
                program_sk,
                "replace_all",
                {"sessions": sessions},
                None,
                None,
                current_revision,
                idempotency_key,
                session_operations=operations,
            )
            self._invalidate_caches()
            return result
        self._invalidate_caches()
        return None
