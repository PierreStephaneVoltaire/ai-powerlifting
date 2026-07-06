"""DynamoDB-backed store for the powerlifting per-user program fields.

All of these sub-tables live in the same ``if-health`` table under different
SKs (or as program-attribute fields). The store resolves the current
program version once and then performs simple field operations.

Mirrors the TypeScript controllers under
``utils/powerlifting-app/backend/src/controllers/``:
  - weightController.ts      -> weight_log#<version> SK
  - maxController.ts         -> max_history#<version> SK; program.meta.target_*_kg
  - dietNotesController.ts   -> program.diet_notes array
  - supplementController.ts  -> program.supplement_phases array
  - blockNotesController.ts  -> program.meta.block_notes array (legacy: program.block_notes)
"""
from __future__ import annotations

import asyncio
import logging
import os
from decimal import Decimal
from typing import Any, Optional

import boto3
from boto3.dynamodb.conditions import Key

logger = logging.getLogger(__name__)


def _to_dynamo(obj: Any) -> Any:
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: _to_dynamo(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_dynamo(v) for v in obj]
    return obj


def _sanitize_decimals(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return float(obj) if obj % 1 > 0 else int(obj)
    if isinstance(obj, dict):
        return {k: _sanitize_decimals(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_decimals(v) for v in obj]
    return obj


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def resolve_version_sk(pk: str, version: str, current_ref_sk: Optional[str]) -> str:
    """Return the SK for a given program version ('current' resolves via pointer)."""
    if version != "current":
        return f"program#{version}"
    return current_ref_sk or "program#v001"


class PerUserStore:
    """Async store for the per-user program fields living in ``if-health``."""

    def __init__(
        self,
    async def _resolve_version_sk(self, version: str) -> str:
        def _sync():
            return resolve_version_sk(self._pk, version, self._pointer_ref_sk_sync())
        return await asyncio.get_running_loop().run_in_executor(None, _sync)

    # ─── Weight log (SK: weight_log#<version>) ────────────────────────────

    def _weight_log_sync(self, version: str) -> dict:
        sk = f"weight_log#{version}"
        resp = self.table.get_item(Key={"pk": self._pk, "sk": sk})
        item = resp.get("Item")
        if not item:
            return {
                "pk": self._pk,
                "sk": sk,
                "version": version,
                "entries": [],
                "updated_at": _now_iso(),
            }
        return _sanitize_decimals(item)

    async def get_weight_log(self, version: str = "current") -> dict:
        return await asyncio.get_running_loop().run_in_executor(
            None, lambda: self._weight_log_sync(version)
        )

    def _weight_log_add_sync(self, version: str, entry: dict) -> dict:
        log = self._weight_log_sync(version)
        date = entry.get("date")
        if not date:
            raise ValueError("entry.date is required (YYYY-MM-DD)")
        entries = list(log.get("entries") or [])
        existing_idx = next(
            (i for i, e in enumerate(entries) if e.get("date") == date), -1
        )
        if existing_idx >= 0:
            entries[existing_idx] = dict(entry)
        else:
            entries.append(dict(entry))
        entries.sort(key=lambda e: str(e.get("date") or ""), reverse=True)
        log["entries"] = entries
        log["version"] = version
        log["updated_at"] = _now_iso()
        self.table.put_item(Item=_to_dynamo(log))
        return _sanitize_decimals(log)

    async def add_weight_entry(self, version: str, entry: dict) -> dict:
        return await asyncio.get_running_loop().run_in_executor(
            None, lambda: self._weight_log_add_sync(version, entry)
        )

    def _weight_log_remove_sync(self, version: str, date: str) -> dict:
        log = self._weight_log_sync(version)
        before = len(log.get("entries") or [])
        log["entries"] = [
            e for e in (log.get("entries") or []) if e.get("date") != date
        ]
        if len(log["entries"]) == before:
            return _sanitize_decimals(log)
        log["version"] = version
        log["updated_at"] = _now_iso()
        self.table.put_item(Item=_to_dynamo(log))
        return _sanitize_decimals(log)

    async def remove_weight_entry(self, version: str, date: str) -> dict:
        return await asyncio.get_running_loop().run_in_executor(
            None, lambda: self._weight_log_remove_sync(version, date)
        )

        table_name: Optional[str] = None,
        pk: str = "operator",
    # ─── Max history + target maxes ────────────────────────────────────────

    def _max_history_sync(self, version: str) -> dict:
        sk = f"max_history#{version}"
        resp = self.table.get_item(Key={"pk": self._pk, "sk": sk})
        item = resp.get("Item")
        if not item:
            return {
                "pk": self._pk,
                "sk": sk,
                "version": version,
                "entries": [],
                "updated_at": _now_iso(),
            }
        return _sanitize_decimals(item)

    async def get_max_history(self, version: str = "current") -> dict:
        return await asyncio.get_running_loop().run_in_executor(
            None, lambda: self._max_history_sync(version)
        )

    def _max_history_add_sync(self, version: str, entry: dict) -> dict:
        history = self._max_history_sync(version)
        entries = list(history.get("entries") or [])
        entries.append(dict(entry))
        entries.sort(key=lambda e: str(e.get("date") or ""), reverse=True)
        history["entries"] = entries
        history["version"] = version
        history["updated_at"] = _now_iso()
        self.table.put_item(Item=_to_dynamo(history))
        return _sanitize_decimals(history)

    async def add_max_entry(self, version: str, entry: dict) -> dict:
        return await asyncio.get_running_loop().run_in_executor(
            None, lambda: self._max_history_add_sync(version, entry)
        )

    def _get_target_maxes_sync(self, version: str) -> dict:
        def _do():
            sk = resolve_version_sk(self._pk, version, self._pointer_ref_sk_sync())
            resp = self.table.get_item(Key={"pk": self._pk, "sk": sk})
            item = resp.get("Item")
            if not item:
                raise ValueError(f"program version {version} not found")
            meta = (item.get("meta") or {})
            return {
                "squat_kg": meta.get("target_squat_kg"),
                "bench_kg": meta.get("target_bench_kg"),
                "deadlift_kg": meta.get("target_dl_kg"),
                "total_kg": meta.get("target_total_kg"),
            }
        return _do()

    async def get_target_maxes(self, version: str = "current") -> dict:
        return await asyncio.get_running_loop().run_in_executor(
            None, lambda: self._get_target_maxes_sync(version)
        )

    def _update_target_maxes_sync(self, version: str, maxes: dict) -> None:
        def _do():
            sk = resolve_version_sk(self._pk, version, self._pointer_ref_sk_sync())
            try:
                squat = float(maxes.get("squat_kg") or 0)
                bench = float(maxes.get("bench_kg") or 0)
                dl = float(maxes.get("deadlift_kg") or 0)
            except (TypeError, ValueError) as exc:
                raise ValueError("squat_kg, bench_kg, deadlift_kg must be numeric") from exc
            total = squat + bench + dl
            now = _now_iso()
            self.table.update_item(
                Key={"pk": self._pk, "sk": sk},
                UpdateExpression=(
                    "SET #meta.target_squat_kg = :squat, "
                    "#meta.target_bench_kg = :bench, "
                    "#meta.target_dl_kg = :dl, "
                    "#meta.target_total_kg = :total, "
                    "#meta.updated_at = :now"
                ),
                ExpressionAttributeNames={"#meta": "meta"},
                ExpressionAttributeValues={
                    ":squat": Decimal(str(squat)),
                    ":bench": Decimal(str(bench)),
    # ─── Diet notes (program field) ────────────────────────────────────────

    def _program_field_get_sync(self, version: str, projection: str, default):
        def _do():
            sk = resolve_version_sk(self._pk, version, self._pointer_ref_sk_sync())
            resp = self.table.get_item(
                Key={"pk": self._pk, "sk": sk},
                ProjectionExpression=projection,
            )
            item = resp.get("Item")
            if not item:
                raise ValueError(f"program version {version} not found")
            return item.get(projection, default) or default
        return _do()

    async def get_diet_notes(self, version: str = "current") -> list:
        def _do():
            return self._program_field_get_sync(version, "diet_notes", [])
        return await asyncio.get_running_loop().run_in_executor(None, _do)

    async def update_diet_notes(self, version: str, notes: list) -> None:
        def _do():
            sk = resolve_version_sk(self._pk, version, self._pointer_ref_sk_sync())
            now = _now_iso()
            self.table.update_item(
                Key={"pk": self._pk, "sk": sk},
                UpdateExpression=(
                    "SET diet_notes = :notes, #meta.updated_at = :now"
                ),
                ExpressionAttributeNames={"#meta": "meta"},
                ExpressionAttributeValues={":notes": _to_dynamo(notes), ":now": now},
            )
        return await asyncio.get_running_loop().run_in_executor(None, _do)

    async def get_supplement_phases(self, version: str = "current") -> list:
        def _do():
            return self._program_field_get_sync(version, "supplement_phases", [])
        return await asyncio.get_running_loop().run_in_executor(None, _do)

    async def update_supplement_phases(self, version: str, phases: list) -> None:
        def _do():
            sk = resolve_version_sk(self._pk, version, self._pointer_ref_sk_sync())
            now = _now_iso()
            self.table.update_item(
                Key={"pk": self._pk, "sk": sk},
                UpdateExpression=(
                    "SET supplement_phases = :phases, #meta.updated_at = :now"
                ),
                ExpressionAttributeNames={"#meta": "meta"},
                ExpressionAttributeValues={":phases": _to_dynamo(phases), ":now": now},
            )
        return await asyncio.get_running_loop().run_in_executor(None, _do)

    async def get_block_notes(self, version: str = "current") -> list:
        def _do():
            sk = resolve_version_sk(self._pk, version, self._pointer_ref_sk_sync())
            resp = self.table.get_item(
                Key={"pk": self._pk, "sk": sk},
                ProjectionExpression="#meta.block_notes, block_notes",
                ExpressionAttributeNames={"#meta": "meta"},
            )
            item = resp.get("Item")
            if not item:
                raise ValueError(f"program version {version} not found")
            meta_notes = (item.get("meta") or {}).get("block_notes")
            legacy = item.get("block_notes")
            if isinstance(meta_notes, list) and (
                len(meta_notes) > 0 or not isinstance(legacy, list)
            ):
                return _sanitize_decimals(meta_notes) or []
            return _sanitize_decimals(legacy) or []
        return await asyncio.get_running_loop().run_in_executor(None, _do)

    async def update_block_notes(self, version: str, notes: list) -> None:
        def _do():
            sk = resolve_version_sk(self._pk, version, self._pointer_ref_sk_sync())
            now = _now_iso()
            self.table.update_item(
                Key={"pk": self._pk, "sk": sk},
                UpdateExpression=(
                    "SET #meta.block_notes = :notes, #meta.updated_at = :now "
                    "REMOVE block_notes"
                ),
                ExpressionAttributeNames={"#meta": "meta"},
                ExpressionAttributeValues={":notes": _to_dynamo(notes), ":now": now},
            )
        return await asyncio.get_running_loop().run_in_executor(None, _do)

    # ─── Exercise E1RM (program.exercises[].e1rm_estimate) ──────────────────

    async def set_exercise_e1rm(
        self,
        version: str,
        exercise_id: str,
        e1rm_kg: float,
        method: str = "manual",
    ) -> dict:
        def _do():
            sk = resolve_version_sk(self._pk, version, self._pointer_ref_sk_sync())
            resp = self.table.get_item(Key={"pk": self._pk, "sk": sk})
            item = resp.get("Item")
            if not item:
                raise ValueError(f"program version {version} not found")
            exercises = item.get("exercises") or []
            found = False
            for ex in exercises:
                if ex.get("id") == exercise_id:
                    ex.setdefault("e1rm_estimate", {})
                    ex["e1rm_estimate"]["value_kg"] = Decimal(str(e1rm_kg))
                    ex["e1rm_estimate"]["method"] = method or "manual"
                    ex["e1rm_estimate"]["basis"] = "Manual entry"
                    ex["e1rm_estimate"]["confidence"] = "medium"
                    ex["e1rm_estimate"]["updated_at"] = _now_iso()
                    found = True
                    break
            if not found:
                raise ValueError(f"exercise {exercise_id} not found in program")
            now = _now_iso()
            self.table.update_item(
                Key={"pk": self._pk, "sk": sk},
                UpdateExpression=(
                    "SET exercises = :ex, #meta.updated_at = :now"
                ),
                ExpressionAttributeNames={"#meta": "meta"},
                ExpressionAttributeValues={":ex": _to_dynamo(exercises), ":now": now},
            )
            return {"exercise_id": exercise_id, "value_kg": float(e1rm_kg), "method": method}
        return await asyncio.get_running_loop().run_in_executor(None, _do)

                    ":dl": Decimal(str(dl)),
                    ":total": Decimal(str(total)),
                    ":now": now,
                },
            )
        _do()

    async def update_target_maxes(self, version: str, maxes: dict) -> None:
        return await asyncio.get_running_loop().run_in_executor(
            None, lambda: self._update_target_maxes_sync(version, maxes)
        )

        region: str = "ca-central-1",
    ) -> None:
        self._table_name = table_name or os.environ.get("IF_HEALTH_TABLE_NAME", "if-health")
        self._pk = pk
        self._region = region or os.environ.get("AWS_REGION", "ca-central-1")
        self._table = None

    @property
    def table(self):
        if self._table is None:
            self._table = boto3.resource("dynamodb", region_name=self._region).Table(
                self._table_name
            )
        return self._table

    def _pointer_ref_sk_sync(self) -> Optional[str]:
        resp = self.table.get_item(Key={"pk": self._pk, "sk": "program#current"})
        item = resp.get("Item")
        if not item:
            return None
        return item.get("ref_sk")

    async def _resolve_version_sk(self, version: str) -> str:
        def _sync():
            return resolve_version_sk(self._pk, version, self._pointer_ref_sk_sync())
        return await asyncio.get_running_loop().run_in_executor(None, _sync)
