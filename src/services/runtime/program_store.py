"""DynamoDB-backed store for training programs.

Uses a pointer-based schema to track the current program version.
Pointer item: pk=HEALTH_PROGRAM_PK, sk="program#current" -> {version, ref_sk, updated_at}
Program item: pk=HEALTH_PROGRAM_PK, sk="program#v{version:03d}" -> full program JSON
"""
from __future__ import annotations

import asyncio
import copy
import logging
import math
import os
import re
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from services.runtime.aws import dynamodb_resource
from boto3.dynamodb.conditions import Key, Attr

from services.runtime.block_scope import BLOCK_SCOPED_RECORD_FIELDS, current_block_id, record_block, scope_program, stamp

logger = logging.getLogger(__name__)

class ProgramNotFoundError(Exception):
    """Raised when pointer item does not exist in DynamoDB."""
    pass


class ProgramStore:
    """DynamoDB-backed store for training programs with versioning support.

    Schema:
        - Pointer item: pk=HEALTH_PROGRAM_PK, sk="program#current"
          -> {version: int, ref_sk: str, updated_at: ISO8601}
        - Program item: pk=HEALTH_PROGRAM_PK, sk="program#v{version:03d}"
          -> full program JSON as DynamoDB map

    All operations are cached in memory for performance.
    """

    POINTER_SK = "program#current"
    PROGRAM_SK_PREFIX = "program#v"

    def __init__(self, table_name: str, pk: str = "operator", region: str = "ca-central-1"):
        """Initialize the program store.

        Args:
            table_name: Name of the DynamoDB table
            pk: Partition key value (default: "operator")
            region: AWS region (default: "ca-central-1")
        """
        self._table_name = table_name
        from services.runtime.storage_scope import current_athlete
        self._pk = current_athlete.get() or pk
        self._region = region
        self._sessions_table_name = os.environ.get("IF_SESSIONS_TABLE_NAME", "if-sessions")
        self._table = None
        self._cache: Optional[dict] = None
        self._cache_version: Optional[int] = None

        logger.debug(f"[ProgramStore] Initialized with table={table_name}, pk={pk}, region={region}")

    @property
    def pk(self) -> str:
        """Active DynamoDB partition key."""
        return self._pk

    @pk.setter
    def pk(self, value: str) -> None:
        """Switch active partition key and clear cached program data."""
        if value != self._pk:
            self._pk = value
            self.invalidate_cache()

    @property
    def table(self):
        """Lazy-load DynamoDB table resource."""
        if self._table is None:
            self._table = dynamodb_resource(
                "dynamodb", region_name=self._region
            ).Table(self._table_name)
        return self._table
    
    def invalidate_cache(self) -> None:
        """Clear the in-memory cache."""
        logger.debug("[ProgramStore] Cache invalidated")
        self._cache = None
        self._cache_version = None

    def _source_snapshot_sync(self) -> tuple[dict, dict, str, bool]:
        pointer = self.table.get_item(
            Key={"pk": self._pk, "sk": self.POINTER_SK}, ConsistentRead=True
        ).get("Item") or {}
        selected = getattr(self, "_selected_program_sk", None)
        if selected in {None, "", "current", self.POINTER_SK}:
            selected = pointer.get("ref_sk")
        if not selected:
            selected = self._current_program_sk_sync()
        program = self.table.get_item(
            Key={"pk": self._pk, "sk": str(selected)}, ConsistentRead=True
        ).get("Item")
        if not isinstance(program, dict):
            raise ProgramNotFoundError(f"Program not found: {selected}")
        current = bool(pointer and str(pointer.get("ref_sk")) == str(selected))
        return copy.deepcopy(program), copy.deepcopy(pointer), str(selected), current

    async def _source_snapshot(self) -> tuple[dict, dict, str, bool]:
        return await asyncio.get_running_loop().run_in_executor(None, self._source_snapshot_sync)

    def _commit_source_sync(
        self,
        snapshot: tuple[dict, dict, str, bool],
        program: dict,
        operation: str,
        payload: dict,
        result: dict) -> dict:
        program_sk = snapshot[2]
        sessions = program.get("sessions")
        if isinstance(sessions, list):
            self._validate_session_identities(sessions)
        now = datetime.now(timezone.utc).isoformat()
        updated = copy.deepcopy(program)
        meta = updated.get("meta") if isinstance(updated.get("meta"), dict) else {}
        updated["meta"] = meta
        meta["updated_at"] = now
        updated["pk"] = self._pk
        updated["sk"] = program_sk
        updated.pop("sessions", None)
        self.table.put_item(Item=self._floats_to_decimals(updated))
        self.invalidate_cache()
        return {**copy.deepcopy(result), "sk": program_sk, "updated_at": now}

    async def _commit_source(self, *args, **kwargs) -> dict:
        return await asyncio.get_running_loop().run_in_executor(None, lambda: self._commit_source_sync(*args, **kwargs))

    async def mutate_source(self, operation: str, payload: dict, mutator) -> dict:
        snapshot = await self._source_snapshot()
        program = copy.deepcopy(snapshot[0])
        result = mutator(program) or {}
        return await self._commit_source(snapshot, program, operation, payload, result)

    def _get_session_store(self):
        from services.runtime.session_store import SessionStore
        return SessionStore(
            table_name=self._sessions_table_name,
            pk=self._pk,
            region=self._region,
            source_table_name=self._table_name,
        )

    def _current_program_sk_sync(self) -> str:
        selected = getattr(self, "_selected_program_sk", None)
        if selected and selected not in {self.POINTER_SK, "current"}:
            return selected
        pointer_resp = self.table.get_item(Key={"pk": self._pk, "sk": self.POINTER_SK})
        if "Item" in pointer_resp:
            ref_sk = pointer_resp["Item"].get("ref_sk")
            if ref_sk:
                program = self.table.get_item(Key={"pk": self._pk, "sk": str(ref_sk)}).get("Item")
                if program and program.get("published", True) is not False:
                    return str(ref_sk)

        programs = self._list_programs_sync(include_archived=False)
        if not programs:
            raise ProgramNotFoundError(
                f"No program or pointer found for pk={self._pk}. "
                "Create a program using new_version() first."
            )
        programs.sort(key=lambda p: p["sk"], reverse=True)
        return str(programs[0]["sk"])
    
    async def get_program(self) -> dict:
        """Get the current training program.
        
        Returns cached program if available, otherwise loads from DynamoDB.
        
        Returns:
            Full program dict
            
        Raises:
            ProgramNotFoundError: If pointer item does not exist
            RuntimeError: If DynamoDB operation fails
        """
        if self._cache is not None:
            logger.debug("[ProgramStore] Cache hit, returning cached program")
            return self._cache
        
        logger.debug("[ProgramStore] Cache miss, loading from DynamoDB")
        
        try:
            program = await asyncio.get_running_loop().run_in_executor(
                None, self._load_program_sync
            )
            
            self._cache = program
            return program
            
        except ProgramNotFoundError:
            raise
        except Exception as e:
            import traceback
            logger.error(f"[ProgramStore] Failed to load program: {e}\n{traceback.format_exc()}")
            raise RuntimeError(f"Failed to load program from DynamoDB: {e}")
    
    def _load_program_sync(self) -> dict:
        """Synchronous program loading logic."""
        logger.info(f"[ProgramStore] Reading pointer from table='{self._table_name}' region='{self._region}': pk={self._pk}, sk={self.POINTER_SK}")
        selected = getattr(self, "_selected_program_sk", None)
        pointer_resp = {"Item": {"ref_sk": selected, "version": 0}} if selected and selected not in {self.POINTER_SK, "current"} else self.table.get_item(
            Key={"pk": self._pk, "sk": self.POINTER_SK}
        )

        if "Item" not in pointer_resp:
            logger.info(f"[ProgramStore] Pointer not found, scanning for existing program versions...")
            try:
                scan_result = self.table.scan(
                    FilterExpression=Attr("pk").eq(self._pk) & Attr("sk").begins_with(self.PROGRAM_SK_PREFIX)
                )
                items = [item for item in scan_result.get("Items", []) if item.get("published", True) is not False]

                if not items:
                    raise ProgramNotFoundError(
                        f"No program or pointer found for pk={self._pk}. "
                        "Create a program using new_version() first."
                    )

                latest_version = 0
                latest_sk = None
                for item in items:
                    sk = item.get("sk", "")
                    if sk.startswith(self.PROGRAM_SK_PREFIX):
                        try:
                            version_str = sk[len(self.PROGRAM_SK_PREFIX):].split("-", 1)[0]
                            version = int(version_str)
                            if version > latest_version:
                                latest_version = version
                                latest_sk = sk
                        except ValueError:
                            continue

                if not latest_sk:
                    raise ProgramNotFoundError(
                        f"No valid program versions found for pk={self._pk}. "
                        "Create a program using new_version() first."
                    )

                now = datetime.now(timezone.utc).isoformat()
                pointer_item = {
                    "pk": self._pk,
                    "sk": self.POINTER_SK,
                    "version": latest_version,
                    "ref_sk": latest_sk,
                    "updated_at": now,
                }
                self.table.put_item(Item=pointer_item)
                logger.info(f"[ProgramStore] Auto-created pointer to version {latest_version} ({latest_sk})")

                pointer_resp = self.table.get_item(
                    Key={"pk": self._pk, "sk": self.POINTER_SK}
                )

            except ProgramNotFoundError:
                raise
            except Exception as scan_err:
                logger.error(f"[ProgramStore] Failed to scan for programs: {scan_err}")
                raise ProgramNotFoundError(
                    f"No program pointer found for pk={self._pk}. "
                    "Create a program using new_version() first."
                )
        
        pointer = pointer_resp["Item"]
        version = int(pointer.get("version", 0))
        ref_sk = pointer.get("ref_sk", f"{self.PROGRAM_SK_PREFIX}{version:03d}")
        
        logger.debug(f"[ProgramStore] Pointer points to version={version}, ref_sk={ref_sk}")
        
        logger.debug(f"[ProgramStore] Reading program: pk={self._pk}, sk={ref_sk}")
        program_resp = self.table.get_item(
            Key={"pk": self._pk, "sk": ref_sk}
        )
        
        if "Item" not in program_resp:
            logger.error(f"[ProgramStore] Program item not found: pk={self._pk}, sk={ref_sk}")
            raise RuntimeError(
                f"Program item not found at {ref_sk}. "
                "Data inconsistency: pointer exists but program item missing."
            )
        
        program = dict(program_resp["Item"])
        if program.get("published", True) is False:
            raise ProgramNotFoundError(f"Program version is unpublished: {ref_sk}")
        meta = program.get("meta")
        if not isinstance(meta, dict):
            meta = {}
            program["meta"] = meta
        program.pop("pk", None)
        program.pop("sk", None)
        program["sessions"] = self._get_session_store().list_sessions_sync(
            str(ref_sk),
            program.get("phases", []) if isinstance(program.get("phases"), list) else [],
        )
        
        self._cache_version = version
        logger.debug(f"[ProgramStore] Loaded program version {version}")
        
        return program
    
    async def new_version(self, patches: list[dict], change_reason: str) -> dict:
        """Create a new major version of the program with patches.
        
        Args:
            patches: List of patches, each with "path" and "value" keys
                    Example: {"path": "sessions[0].exercises[1].kg", "value": 180}
            change_reason: Human-readable reason for the version change
            
        Returns:
            New program dict
            
        Raises:
            ValueError: If patch path is invalid
            RuntimeError: If DynamoDB operation fails
        """
        self.invalidate_cache()
        program = await self.get_program()
        new_program = copy.deepcopy(program)
        self._validate_version_patches(program, patches)
        
        for patch in patches:
            path = patch.get("path", "")
            value = patch.get("value")
            
            if not path:
                raise ValueError("Patch must have 'path' key")
            
            self._apply_patch(new_program, path, value)

        self._preserve_logged_sessions(program, new_program)
        
        if "meta" not in new_program:
            new_program["meta"] = {}
        if "change_log" not in new_program["meta"]:
            new_program["meta"]["change_log"] = []
        new_program["meta"]["change_log"].append({
            "reason": change_reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        updated_program = await self._write_new_version(
            new_program, minor=False)
        
        return updated_program

    @staticmethod
    def _session_is_logged(session: dict) -> bool:
        if session.get("status") in {"logged", "completed", "skipped"} or bool(session.get("completed")):
            return True
        return any(
            isinstance(exercise, dict)
            and any(status in {"completed", "failed", "skipped"} for status in (exercise.get("set_statuses") or []))
            for exercise in (session.get("exercises") or [])
        )

    @staticmethod
    def _validate_session_identities(sessions: list[dict]) -> None:
        from services.runtime.session_store import SessionIdentityConflictError

        seen: set[str] = set()
        for session in sessions:
            if not isinstance(session, dict):
                continue
            session_id = str(session.get("session_id") or session.get("id") or "").strip()
            if not session_id:
                continue
            if session_id in seen:
                raise SessionIdentityConflictError(session_id, f"Session identity {session_id} occurs more than once")
            seen.add(session_id)

    def _validate_version_patches(self, program: dict, patches: list[dict]) -> None:
        sessions = program.get("sessions") if isinstance(program.get("sessions"), list) else []
        protected_meta = {"pk", "sk", "version_label", "updated_at", "published", "blocks", "current_block_id"}
        for patch in patches:
            path = patch.get("path", "") if isinstance(patch, dict) else ""
            parts = re.split(r"[.\[]", path)
            root = parts[0]
            if root in protected_meta or (root == "meta" and (len(parts) == 1 or parts[1] not in self.ALLOWED_META_FIELDS or parts[1] in protected_meta)):
                raise ValueError(f"Protected version metadata cannot be patched: {path}")
            match = re.match(r"^sessions\[(\d+)\](?:\.(.*))?$", path)
            if not match:
                continue
            index = int(match.group(1))
            if index >= len(sessions):
                raise ValueError(f"Invalid path '{path}': index {index} out of range")
            field = match.group(2) or ""
            session = sessions[index]
            if field in {"", "id", "session_id", "date"}:
                raise ValueError(f"Session identity cannot be changed: {path}")
            if self._session_is_logged(session) and (field == "exercises" or field.startswith("exercises[") or field == "videos" or field.startswith("videos[")):
                raise ValueError(f"Logged session data cannot be changed through new_version: {path}")

    def _preserve_logged_sessions(self, original: dict, updated: dict) -> None:
        before = original.get("sessions") if isinstance(original.get("sessions"), list) else []
        after = updated.get("sessions") if isinstance(updated.get("sessions"), list) else []
        for index, old in enumerate(before):
            if not isinstance(old, dict) or not self._session_is_logged(old):
                continue
            if not old.get("id"):
                raise ValueError("Logged sessions require a stable session id")
            match = next((item for item in after if isinstance(item, dict) and item.get("id") == old.get("id")), None)
            if match is None:
                raise ValueError("Logged sessions require a stable session id")
            match["id"] = old.get("id")
            match["session_id"] = old.get("session_id", old.get("id"))
            for key in ("exercises", "videos", "media_revision"):
                if key in old:
                    match[key] = copy.deepcopy(old[key])

    async def block_transition(
        self,
        action: str,
        block_id: str,
        *,
        name: str | None = None,
        current_name: str | None = None,
        start_date: str | None = None,
        week_start_day: str | None = None,
        start_maxes_kg: dict | None = None,
        next_program: dict | None = None,
    ) -> dict:
        if action == "rename":
            if not isinstance(name, str) or not name.strip():
                raise ValueError("rename requires a block name")

            def mutate(program):
                meta = program.setdefault("meta", {})
                blocks = meta.get("blocks") or []
                block = next((item for item in blocks if str(item.get("id") or item.get("block_id")) == str(block_id)), None)
                if block is None:
                    raise ValueError("block_id must identify an existing block")
                if block.get("status") == "completed" and self._is_reserved_block_name(name):
                    raise ValueError("an archived block cannot be named current")
                block["name"] = name.strip()
                block["label"] = name.strip()
                return {"action": action, "block_id": block_id, "name": block["name"]}

            return await self.mutate_source("block_rename", {"action": action, "block_id": block_id, "name": name}, mutate)
        if action not in {"complete", "start_next", "complete_and_start"}:
            raise ValueError("action must be complete, start_next, complete_and_start, or rename")
        if not block_id:
            raise ValueError("block_id is required")
        if action in {"start_next", "complete_and_start"}:
            self._validate_transition_start(start_date, week_start_day, start_maxes_kg)
        if action in {"complete", "complete_and_start"} and self._is_reserved_block_name(current_name):
            raise ValueError("an archived block cannot be named current")
        plan = self._validate_next_program(next_program)
        self.invalidate_cache()
        program = copy.deepcopy(await self.get_program())
        meta = program.setdefault("meta", {})
        blocks = [copy.deepcopy(b) for b in (meta.get("blocks") or []) if isinstance(b, dict)]
        current_id = str(meta.get("current_block_id") or "")
        if not current_id:
            current_id = next(
                (str(block.get("id") or block.get("block_id")) for block in blocks
                 if block.get("status", "active") == "active"),
                "",
            )
        active = next((b for b in blocks if str(b.get("id") or b.get("block_id")) == current_id and b.get("status", "active") == "active"), None)
        if active is None:
            active = next((b for b in blocks if str(b.get("id") or b.get("block_id")) == "current" and b.get("status", "active") == "active"), None)
        if action in {"complete", "complete_and_start"}:
            active_id = str(active.get("id") or active.get("block_id")) if active else ""
            valid_ids = {active_id} | ({"current"} if active_id == "current" else set())
            if active is None or block_id not in valid_ids:
                raise ValueError("block_id must identify the active current block")
            source = active
        else:
            if active is not None:
                raise ValueError("start_next is only allowed after the current block is completed")
            source = next((b for b in blocks if str(b.get("id") or b.get("block_id")) == block_id and b.get("status") == "completed"), None)
            if source is None:
                raise ValueError("block_id must identify a completed block")

        phases = [copy.deepcopy(p) for p in (program.get("phases") or []) if isinstance(p, dict)]
        sessions = [copy.deepcopy(s) for s in (program.get("sessions") or []) if isinstance(s, dict)]
        source_id = str(source.get("id") or source.get("block_id"))
        archive_id = source_id if source_id != "current" else self._archive_block_id(current_name or source.get("name"), blocks, phases, sessions)
        if action in {"complete", "complete_and_start"}:
            source.setdefault("start_maxes_kg", copy.deepcopy(program.get("current_maxes", {})))
            for phase in phases:
                if str(phase.get("block") or "current") == "current" or str(phase.get("block_id") or "") == source_id:
                    phase["block"] = archive_id
                    phase["block_id"] = archive_id
            for session in sessions:
                if str(session.get("block") or "current") == "current" or str(session.get("block_id") or "") == source_id:
                    session["block"] = archive_id
                    session["block_id"] = archive_id
            self._remap_block_meta(meta, source_id, archive_id)
            self._archive_block_records(program, source_id, archive_id)
            source["id"] = archive_id
            source["block_id"] = archive_id
            if isinstance(current_name, str) and current_name.strip():
                source["name"] = current_name.strip()
            if self._is_reserved_block_name(source.get("name")):
                source["name"] = archive_id
            source["label"] = source["name"] or archive_id
            source["status"] = "completed"
            source["archived"] = True
            source["completed_at"] = datetime.now(timezone.utc).isoformat()

        next_id = None
        if action in {"start_next", "complete_and_start"}:
            next_id = f"block-{uuid.uuid4().hex[:16]}"
            next_sessions = []
            for session in plan["sessions"]:
                prepared = copy.deepcopy(session)
                prepared["block"] = "current"
                prepared["block_id"] = next_id
                prepared["status"] = "planned"
                prepared["completed"] = False
                next_sessions.append(prepared)
            next_phases = []
            for phase in plan["phases"]:
                prepared = copy.deepcopy(phase)
                prepared["block"] = "current"
                prepared["block_id"] = next_id
                next_phases.append(prepared)
            phases.extend(next_phases)
            sessions.extend(next_sessions)
            next_block = {
                "id": next_id,
                "block_id": next_id,
                "label": "current",
                "name": name or "Next block",
                "status": "active",
                "start_week": 1,
                "end_week": max(
                    [int(p.get("end_week", 0)) for p in next_phases]
                    + [int(s.get("week_number", 0) or 0) for s in next_sessions]
                    + [0]
                ),
                "start_date": start_date,
                "week_start_day": week_start_day,
                "start_maxes_kg": copy.deepcopy(start_maxes_kg),
            }
            blocks.append(next_block)
            meta["program_start"] = start_date
            program["current_maxes"] = self._canonical_maxes(start_maxes_kg)

        if action in {"complete", "complete_and_start"}:
            blocks = [source if b is active else b for b in blocks]
        meta["blocks"] = blocks
        meta["current_block_id"] = next_id
        program["phases"] = phases
        program["sessions"] = sessions
        self._validate_session_identities(sessions)
        result = {"action": action, "block_id": block_id, "next_block_id": next_id, "warning": "Unfinished sessions were preserved"}
        written = await self._write_new_version(program, minor=False)
        self.invalidate_cache()
        result["program"] = written
        return result

    @staticmethod
    def _validate_transition_start(start_date: str | None, week_start_day: str | None, start_maxes_kg: dict | None) -> None:
        if not isinstance(start_date, str) or not start_date:
            raise ValueError("start_next requires start_date, week_start_day, and confirmed start_maxes_kg")
        try:
            date.fromisoformat(start_date)
        except ValueError as exc:
            raise ValueError("start_date must be an ISO date") from exc
        if not isinstance(week_start_day, str) or week_start_day.capitalize() not in {"Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"}:
            raise ValueError("week_start_day must be a weekday")
        if not isinstance(start_maxes_kg, dict) or not start_maxes_kg or any(
            isinstance(value, bool) or not isinstance(value, (int, float, Decimal)) or value <= 0 or (isinstance(value, float) and not math.isfinite(value)) for value in start_maxes_kg.values()
        ):
            raise ValueError("start_maxes_kg must contain positive numeric maxes")

    @staticmethod
    def _validate_next_program(next_program: dict | None) -> dict:
        if next_program is None:
            return {"phases": [], "sessions": []}
        if not isinstance(next_program, dict):
            raise ValueError("next_program must be an object")
        phases = next_program.get("phases", [])
        sessions = next_program.get("sessions", [])
        if not isinstance(phases, list) or not isinstance(sessions, list):
            raise ValueError("next_program phases and sessions must be arrays")
        normalized_phases = []
        for phase in phases:
            if not isinstance(phase, dict):
                raise ValueError("next_program phases must contain objects")
            try:
                start_week = int(phase.get("start_week", 1))
                end_week = int(phase.get("end_week", start_week))
            except (TypeError, ValueError) as exc:
                raise ValueError("phase week ranges must be integers") from exc
            if start_week < 1 or end_week < start_week:
                raise ValueError("phase week ranges must be positive and ordered")
            normalized = copy.deepcopy(phase)
            normalized["start_week"] = start_week
            normalized["end_week"] = end_week
            normalized_phases.append(normalized)
        normalized_sessions = []
        seen_ids: set[str] = set()
        for session in sessions:
            if not isinstance(session, dict) or not session.get("date"):
                raise ValueError("next_program sessions must contain dates")
            try:
                date.fromisoformat(str(session["date"]))
            except ValueError as exc:
                raise ValueError("next_program session dates must be ISO dates") from exc
            if session.get("status") in {"logged", "completed", "skipped"} or session.get("completed"):
                raise ValueError("next_program cannot contain completed sessions")
            normalized = copy.deepcopy(session)
            session_id = normalized.get("id") or normalized.get("session_id")
            if session_id:
                session_id = str(session_id)
                if session_id in seen_ids:
                    raise ValueError("next_program session identities must be unique")
                seen_ids.add(session_id)
                normalized["id"] = session_id
            normalized["week_number"] = max(1, ProgramStore._session_week_number(normalized))
            normalized_sessions.append(normalized)
        week_values = [phase["start_week"] for phase in normalized_phases]
        week_values.extend(session["week_number"] for session in normalized_sessions if session["week_number"] > 0)
        offset = min(week_values, default=1) - 1
        for phase in normalized_phases:
            phase["start_week"] -= offset
            phase["end_week"] -= offset
        for session in normalized_sessions:
            if session["week_number"] > 0:
                session["week_number"] -= offset
        return {"phases": normalized_phases, "sessions": normalized_sessions}

    @staticmethod
    def _session_week_number(session: dict) -> int:
        value = session.get("week_number")
        try:
            number = int(value)
            if number >= 0:
                return number
        except (TypeError, ValueError):
            pass
        value = session.get("week")
        if isinstance(value, str):
            import re
            match = re.search(r"W(\d+)", value, flags=re.IGNORECASE)
            if match:
                return int(match.group(1))
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _canonical_maxes(maxes: dict) -> dict:
        aliases = {"squat_kg": "squat", "bench_kg": "bench", "deadlift_kg": "deadlift", "dl_kg": "deadlift"}
        return {aliases.get(str(key), str(key)): value for key, value in maxes.items()}

    @staticmethod
    def _is_reserved_block_name(name: Any) -> bool:
        return isinstance(name, str) and re.sub(r"[^a-z0-9]+", " ", name.lower()).strip() in {"current", "current block"}

    @staticmethod
    def _archive_block_id(name: Any, blocks: list[dict], phases: list[dict], sessions: list[dict]) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", str(name or "").lower()).strip("-")[:48].strip("-")
        if not slug or ProgramStore._is_reserved_block_name(slug):
            return f"block-{uuid.uuid4().hex[:16]}"
        taken = {str(item.get(key)) for item in [*blocks, *phases, *sessions] for key in ("id", "block_id", "block") if item.get(key)}
        candidate, suffix = slug, 2
        while candidate in taken:
            candidate, suffix = f"{slug}-{suffix}", suffix + 1
        return candidate

    @staticmethod
    def _replace_active_block_records(program: dict, field: str, incoming: list) -> list:
        current_block_id(program)
        kept = [copy.deepcopy(item) for item in (program.get(field) or []) if isinstance(item, dict) and not ProgramStore._record_is_active_for_mutation(item, field, program)]
        replaced = [stamp(copy.deepcopy(item), program, field=field) for item in incoming if isinstance(item, dict) and ProgramStore._record_is_active_for_mutation(item, field, program)]
        return kept + replaced

    @staticmethod
    def _record_is_active_for_mutation(record: dict, field: str, program: dict) -> bool:
        return record_block(record, field, program) == current_block_id(program)

    @staticmethod
    def _archive_block_records(program: dict, source_id: str, archive_id: str) -> None:
        for field in BLOCK_SCOPED_RECORD_FIELDS:
            for record in program.get(field) or []:
                if isinstance(record, dict) and record_block(record, field, program) in {source_id, current_block_id(program) if source_id == "current" else source_id}:
                    record["block_id"] = archive_id
                    if "block" in record:
                        record["block"] = archive_id

    @staticmethod
    def _remap_block_meta(meta: dict, source_id: str, archive_id: str) -> None:
        notes = meta.get("block_notes")
        if isinstance(notes, list):
            for note in notes:
                if isinstance(note, dict) and (str(note.get("block") or "") in {source_id, "current"} or str(note.get("block_id") or "") == source_id or (source_id == "current" and not note.get("block_id") and not note.get("block"))):
                    note["block"] = archive_id
                    note["block_id"] = archive_id
    
    def _apply_patch(self, obj: dict, path: str, value: Any) -> None:
        """Apply a JSON-path-like patch to an object.
        
        Supports paths like:
            - "sessions[0].exercises[1].kg"
            - "phases[2].end_week"
        
        Args:
            obj: Object to patch
            path: Path to the field to update
            value: New value
            
        Raises:
            ValueError: If path is invalid
        """
        import re
        
        segments = []
        for part in path.split("."):
            match = re.match(r"^(\w+)\[(\d+)\]$", part)
            if match:
                segments.append((match.group(1), int(match.group(2))))
            else:
                segments.append((part, None))
        
        current = obj
        for i, (key, idx) in enumerate(segments[:-1]):
            if idx is not None:
                if key not in current:
                    raise ValueError(f"Invalid path '{path}': '{key}' not found")
                if not isinstance(current[key], list):
                    raise ValueError(f"Invalid path '{path}': '{key}' is not a list")
                if idx >= len(current[key]):
                    raise ValueError(f"Invalid path '{path}': index {idx} out of range")
                current = current[key][idx]
            else:
                if not isinstance(current, dict):
                    raise ValueError(f"Invalid path '{path}': expected dict at '{key}'")
                if key not in current:
                    raise ValueError(f"Invalid path '{path}': '{key}' not found")
                current = current[key]
        
        final_key, final_idx = segments[-1]
        if final_idx is not None:
            if final_key not in current:
                raise ValueError(f"Invalid path '{path}': '{final_key}' not found")
            if not isinstance(current[final_key], list):
                raise ValueError(f"Invalid path '{path}': '{final_key}' is not a list")
            if final_idx >= len(current[final_key]):
                raise ValueError(f"Invalid path '{path}': index {final_idx} out of range")
            current[final_key][final_idx] = value
        else:
            if not isinstance(current, dict):
                raise ValueError(f"Invalid path '{path}': expected dict at '{final_key}'")
            current[final_key] = value
    
    async def _write_new_version(self, program: dict, minor: bool) -> dict:
        """Write a new version of the program to DynamoDB.
        
        Args:
            program: Program dict to write
            minor: If True, increment minor version (1.0 -> 1.1)
                   If False, increment major version (1.0 -> 2.0)
            
        Returns:
            The written program dict
            
        Raises:
            RuntimeError: If DynamoDB operation fails
        """
        try:
            result = await asyncio.get_running_loop().run_in_executor(
                None, lambda: self._write_new_version_sync(program, minor)
            )
            return result
        except (ValueError, LookupError):
            raise
        except Exception as e:
            from services.runtime.session_store import SessionIdentityConflictError
            if isinstance(e, SessionIdentityConflictError):
                raise
            logger.error(f"[ProgramStore] Failed to write new version: {e}")
            raise RuntimeError(f"Failed to write new version to DynamoDB: {e}")
    
    @staticmethod
    def _floats_to_decimals(obj: Any) -> Any:
        """Recursively convert float values to Decimal for DynamoDB compatibility.

        DynamoDB's boto3 client does not support Python float types.
        All floats must be converted to Decimal before writing.
        None values are left as-is (DynamoDB accepts null).
        """
        if isinstance(obj, float):
            return Decimal(str(obj))
        if isinstance(obj, dict):
            return {k: ProgramStore._floats_to_decimals(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [ProgramStore._floats_to_decimals(v) for v in obj]
        return obj

    def _write_new_version_sync(self, program: dict, minor: bool) -> dict:
        """Synchronous version writing logic."""
        now = datetime.now(timezone.utc).isoformat()
        
        logger.debug(f"[ProgramStore] Reading current pointer for version increment")
        pointer_resp = self.table.get_item(
            Key={"pk": self._pk, "sk": self.POINTER_SK}
        )
        
        pointer = pointer_resp.get("Item")
        if pointer:
            current_version = int(pointer.get("version", 0))
        else:
            current_version = 0

        new_version_int = current_version + 1

        if "meta" not in program:
            program["meta"] = {}
        
        current_label = program["meta"].get("version_label", "0.0")
        try:
            major, minor_num = map(int, current_label.split("."))
            if minor:
                new_label = f"{major}.{minor_num + 1}"
            else:
                new_label = f"{major + 1}.0"
        except (ValueError, AttributeError):
            new_label = "1.0" if current_version == 0 else f"{new_version_int}.0"
        
        program["meta"]["version_label"] = new_label
        program["meta"]["updated_at"] = now
        
        suffix = uuid.uuid4().hex
        new_sk = f"{self.PROGRAM_SK_PREFIX}{new_version_int:03d}-{suffix}"

        sessions = copy.deepcopy(program.get("sessions", []))
        self._validate_session_identities(sessions)
        program_without_sessions = copy.deepcopy(program)
        program_without_sessions.pop("sessions", None)

        program_item = {**program_without_sessions, "pk": self._pk, "sk": new_sk, "published": True}
        
        program_item = self._floats_to_decimals(program_item)
        
        logger.debug(f"[ProgramStore] Writing new program version: sk={new_sk}, label={new_label}")
        self.table.put_item(Item=program_item)

        self._get_session_store().replace_program_sessions_sync(
            new_sk,
            sessions if isinstance(sessions, list) else [],
            program.get("phases", []) if isinstance(program.get("phases"), list) else [],
        )
        
        pointer_item = {
            "pk": self._pk,
            "sk": self.POINTER_SK,
            "version": new_version_int,
            "ref_sk": new_sk,
            "updated_at": now,
            "current_block_id": current_block_id(program),
        }
        
        logger.debug(f"[ProgramStore] Updating pointer to version={new_version_int}")
        self.table.put_item(Item=self._floats_to_decimals(pointer_item))
        logger.info(f"[ProgramStore] Created new {'minor' if minor else 'major'} version: {new_label} (v{new_version_int})")

        self.invalidate_cache()
        return program

    async def archive(self, sk: str) -> dict:
        self._selected_program_sk = sk
        snapshot = await self._source_snapshot()
        program = copy.deepcopy(snapshot[0])
        meta = program.setdefault("meta", {})
        meta["archived"] = True
        meta["archived_at"] = datetime.now(timezone.utc).isoformat()
        return await self._commit_source(snapshot, program, "program_archive", {"sk": sk, "archived": True}, {"success": True, "archived": True, "sk": snapshot[2]})

    async def unarchive(self, sk: str) -> dict:
        self._selected_program_sk = sk
        snapshot = await self._source_snapshot()
        program = copy.deepcopy(snapshot[0])
        meta = program.setdefault("meta", {})
        meta["archived"] = False
        meta["archived_at"] = None
        return await self._commit_source(snapshot, program, "program_unarchive", {"sk": sk, "archived": False}, {"success": True, "archived": False, "sk": snapshot[2]})

    async def list_programs(self, include_archived: bool = False) -> list[dict]:
        """List all program versions.

        Args:
            include_archived: Whether to include archived programs in the list

        Returns:
            List of program summaries (sk, meta, etc.)
        """
        return await asyncio.get_running_loop().run_in_executor(
            None, lambda: self._list_programs_sync(include_archived)
        )

    def _list_programs_sync(self, include_archived: bool = False) -> list[dict]:
        """Synchronous program listing logic."""
        scan_result = self.table.query(
            KeyConditionExpression=Key("pk").eq(self._pk) & Key("sk").begins_with(self.PROGRAM_SK_PREFIX)
        )
        items = scan_result.get("Items", [])
        
        if not include_archived:
            items = [
                item for item in items 
                if item.get("published", True) is not False and not item.get("meta", {}).get("archived", False)
            ]
        else:
            items = [item for item in items if item.get("published", True) is not False]
        
        results = []
        for item in items:
            p = dict(item)
            results.append(p)

        return results
    # ─── In-place updates (no new version — matches the pre-refactor controller) ─

    ALLOWED_META_FIELDS = (
        "program_name", "program_start", "federation", "practicing_for",
        "version_label", "sex", "weight_class_kg", "weight_classes_kg", "weight_class_confirm_by",
        "current_body_weight_kg", "current_body_weight_lb",
        "manual_maxes", "lift_attempt_settings",
        "target_squat_kg", "target_bench_kg", "target_dl_kg", "target_total_kg",
        "attempt_pct", "height_cm", "arm_wingspan_cm", "leg_length_cm",
        "blocks",
    )

    async def update_meta_field(self, field: str, value: Any) -> dict:
        return await self.update_meta_fields({field: value})

    async def update_meta_fields(self, updates: dict[str, Any]) -> dict:
        if not isinstance(updates, dict) or not updates:
            raise ValueError("updates must be a nonempty object")
        unknown = set(updates) - set(self.ALLOWED_META_FIELDS)
        if unknown:
            raise ValueError(f"Cannot update fields: {sorted(unknown)}")
        if "weight_classes_kg" in updates:
            classes = updates["weight_classes_kg"]
            if not isinstance(classes, list) or len(classes) > 2 or any(not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0 for value in classes):
                raise ValueError("weight_classes_kg must contain at most two positive numbers")

        def mutate(program):
            meta = program.setdefault("meta", {})
            meta.update(copy.deepcopy(updates))
            return {"success": True, "meta": copy.deepcopy(meta)}

        return await self.mutate_source("meta_update", {"updates": updates}, mutate)

    async def update_phases(self, phases: list, block: Optional[str]) -> dict:
        if not isinstance(phases, list):
            raise ValueError("phases must be a list")

        def mutate(program):
            existing = program.get("phases") if isinstance(program.get("phases"), list) else []
            if block:
                other_blocks = [p for p in existing if (p.get("block") or "current") != block]
                incoming = [stamp({**p, "block": p.get("block", block)}, program, p.get("block") or block) for p in phases]
                program["phases"] = other_blocks + incoming
            else:
                program["phases"] = [stamp({**p, "block": p.get("block", "current")}, program, p.get("block")) for p in phases]
            return {"success": True, "phases": copy.deepcopy(program["phases"])}

        return await self.mutate_source("phases_update", {"phases": phases, "block": block}, mutate)

    async def update_lift_profiles(self, profiles: list) -> dict:
        if not isinstance(profiles, list):
            raise ValueError("lift_profiles must be a list")

        def mutate(program):
            program["lift_profiles"] = copy.deepcopy(profiles)
            return {"success": True, "lift_profiles": copy.deepcopy(profiles)}

        return await self.mutate_source("lift_profiles_update", {"lift_profiles": profiles}, mutate)

    async def update_diet_notes(self, notes: list) -> dict:
        if not isinstance(notes, list):
            raise ValueError("diet_notes must be a list")

        def mutate(program):
            program["diet_notes"] = self._replace_active_block_records(program, "diet_notes", notes)
            return {"success": True, "diet_notes": scope_program(program)["diet_notes"]}

        return await self.mutate_source("diet_notes_update", {"diet_notes": notes}, mutate)

    async def update_block_notes(self, notes: list) -> dict:
        if not isinstance(notes, list):
            raise ValueError("block_notes must be a list")

        def mutate(program):
            meta = program.setdefault("meta", {})
            active = current_block_id(program)
            kept = [copy.deepcopy(note) for note in meta.get("block_notes") or [] if isinstance(note, dict) and record_block(note, "meta.block_notes", program) != active]
            replaced = [stamp(copy.deepcopy(note), program, field="meta.block_notes") for note in notes if isinstance(note, dict) and record_block(note, "meta.block_notes", program) == active]
            meta["block_notes"] = kept + replaced
            return {"success": True, "block_notes": scope_program(program)["meta"]["block_notes"]}

        return await self.mutate_source("block_notes_update", {"block_notes": notes}, mutate)

    async def update_supplements(self, patch: dict) -> dict:
        if not isinstance(patch, dict) or not patch or not set(patch) <= {"supplements", "supplement_phases"}:
            raise ValueError("patch must contain supplements or supplement_phases")

        def mutate(program):
            for key, value in patch.items():
                if not isinstance(value, list):
                    raise ValueError(f"{key} must be a list")
                program[key] = self._replace_active_block_records(program, key, value)
            scoped = scope_program(program)
            return {key: copy.deepcopy(scoped.get(key, [])) for key in ("supplements", "supplement_phases")}

        return await self.mutate_source("supplements_update", {"patch": patch}, mutate)

    async def update_supplement_phases(self, phases: list) -> dict:
        return await self.update_supplements({"supplement_phases": phases})
