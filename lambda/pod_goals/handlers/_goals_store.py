"""DynamoDB-backed store for the powerlifting athlete-goals feature.

Schema (POWERLIFTING_GOALS_TABLE):
    - Goal rows:  pk=<user>, sk="GOAL#<id>"  -> StoredGoal (+ pk/sk)

This mirrors backend goalsController.ts so the fission functions are thin async
wrappers and the backend becomes a pure auth/pk router. The full replace
reconciliation (query existing -> upsert incoming by id -> delete missing) lives
here, not in the backend.
"""
from __future__ import annotations

import asyncio
import logging
import time
import random
import uuid as _uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

import boto3
from boto3.dynamodb.conditions import Key

logger = logging.getLogger(__name__)

GOAL_PREFIX = "GOAL#"

GOAL_TYPE_VALUES = (
    "hit_total",
    "qualify_for_federation",
    "peak_for_meet",
    "conservative_pr",
    "competition_exposure",
    "improve_dots",
    "improve_ipf_gl",
    "custom",
)
GOAL_PRIORITY_VALUES = ("primary", "secondary", "optional")
AGE_CATEGORY_VALUES = (
    "open",
    "subjunior",
    "junior",
    "master1",
    "master2",
    "master3",
    "master4",
)


def _new_goal_id() -> str:
    return f"goal-{time.time_ns().__format__('x')}-{int(random.random() * 1e9):x}"


def _pick_enum(value, allowed, fallback):
    return value if isinstance(value, str) and value in allowed else fallback


def _normalize_goal_type(value) -> str:
    return _pick_enum(value, GOAL_TYPE_VALUES, "custom")


def _normalize_goal_priority(value) -> str:
    return _pick_enum(value, GOAL_PRIORITY_VALUES, "secondary")


def _normalize_age_class(value) -> Optional[str]:
    return value if isinstance(value, str) and value in AGE_CATEGORY_VALUES else None


def _sanitize_decimals(obj):
    if isinstance(obj, Decimal):
        return float(obj) if obj % 1 > 0 else int(obj)
    if isinstance(obj, dict):
        return {k: _sanitize_decimals(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_decimals(v) for v in obj]
    return obj


def _to_dynamo(obj):
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: _to_dynamo(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_dynamo(v) for v in obj]
    return obj


def _dedupe_strings(value) -> Optional[list]:
    if not isinstance(value, list):
        return None
    out, seen = [], set()
    for v in value:
        if isinstance(v, str) and v and v not in seen:
            seen.add(v)
            out.append(v)
    return out if out else None


def _dedupe_numbers(value) -> Optional[list]:
    if not isinstance(value, list):
        return None
    out, seen = [], set()
    for v in value:
        if isinstance(v, (int, float)) and v == v and v > 0 and v not in seen:
            seen.add(v)
            out.append(float(v))
    return out if out else None


def _opt_finite_positive(value) -> Optional[float]:
    if isinstance(value, (int, float)) and value == value and value > 0:
        return float(value)
    return None


def normalize_goal(raw) -> Optional[dict]:
    """Replicate goalsController.normalizeGoal exactly."""
    if not raw or not isinstance(raw, dict):
        return None
    r = raw
    id_ = r.get("id") if isinstance(r.get("id"), str) and r.get("id") else _new_goal_id()
    out = {
        "id": id_,
        "title": r.get("title") if isinstance(r.get("title"), str) else "",
        "goal_type": _normalize_goal_type(r.get("goal_type")),
        "priority": _normalize_goal_priority(r.get("priority")),
    }
    target_date = r.get("target_date")
    if isinstance(target_date, str) and target_date:
        out["target_date"] = target_date
    tci = _dedupe_strings(r.get("target_competition_ids"))
    if tci:
        out["target_competition_ids"] = tci
    for key, val in (("target_total_kg", r.get("target_total_kg")),
                     ("target_dots", r.get("target_dots")),
                     ("target_ipf_gl", r.get("target_ipf_gl"))):
        n = _opt_finite_positive(val)
        if n is not None:
            out[key] = n
    tfi = _dedupe_strings(r.get("target_federation_ids"))
    if tfi:
        out["target_federation_ids"] = tfi
    twc = _dedupe_numbers(r.get("target_weight_class_kg"))
    if twc:
        out["target_weight_class_kg"] = twc
    age = _normalize_age_class(r.get("age_class"))
    if age:
        out["age_class"] = age
    notes = r.get("notes")
    if isinstance(notes, str):
        out["notes"] = notes
    return out


def strip_stored_fields(g: dict) -> dict:
    """Replicate goalsController.stripStoredFields: drop id, target_competition_ids,
    created_at, updated_at and return the rest (the AthleteGoal shape)."""
    out = dict(g)
    out.pop("id", None)
    out.pop("target_competition_ids", None)
    out.pop("created_at", None)
    out.pop("updated_at", None)
    return out


def build_stored_goal(g: dict, id_: str, created_at: Optional[str] = None) -> dict:
    """Replicate goalsController.buildStoredGoal."""
    now = datetime.now(timezone.utc).isoformat()
    return {
        **g,
        "id": id_,
        "target_competition_ids": g.get("target_competition_ids", []),
        "created_at": created_at if created_at else now,
        "updated_at": now,
    }



class GoalsStore:
    def __init__(self, table_name: str = "if-powerlifting-goals", pk: str = "operator", region: str = "ca-central-1"):
        self.table_name = table_name
        self.pk = pk
        self.region = region
        self._table = boto3.resource("dynamodb", region_name=region).Table(table_name)

    @property
    def table(self):
        return self._table

    def _query_goals_sync(self, pk: str) -> list:
        items: list = []
        last_key = None
        while True:
            kwargs = {
                "KeyConditionExpression": Key("pk").eq(pk) & Key("sk").begins_with(GOAL_PREFIX),
            }
            if last_key:
                kwargs["ExclusiveStartKey"] = last_key
            resp = self.table.query(**kwargs)
            for it in (resp.get("Items") or []):
                items.append(_sanitize_decimals(dict(it)))
            last_key = resp.get("LastEvaluatedKey")
            if not last_key:
                break
        return items

    async def _query_goals(self, pk: str) -> list:
        return await asyncio.get_running_loop().run_in_executor(None, lambda: self._query_goals_sync(pk))

    def list_goals_sync(self, pk: str) -> list:
        stored = self._query_goals_sync(pk)
        out = []
        for s in stored:
            normalized = normalize_goal(strip_stored_fields(s))
            if normalized is not None:
                out.append(normalized)
        return out

    async def list_goals(self, pk: str) -> list:
        return await asyncio.get_running_loop().run_in_executor(None, lambda: self.list_goals_sync(pk))

    def replace_goals_sync(self, pk: str, goals: list) -> None:
        """Full replace: upsert incoming goals by id, delete goals not in incoming.
        Replicates goalsController.updateGoals exactly."""
        existing = self._query_goals_sync(pk)
        by_id = {s.get("id"): s for s in existing}
        incoming_ids = set()
        now = datetime.now(timezone.utc).isoformat()

        for raw in goals or []:
            normalized = normalize_goal(raw)
            if normalized is None:
                continue
            id_ = normalized["id"]
            if id_ in by_id:
                incoming_ids.add(id_)
                cur = by_id[id_]
                merged = build_stored_goal(normalized, id_, cur.get("created_at"))
                # preserve existing target_competition_ids per controller merge
                merged["target_competition_ids"] = cur.get("target_competition_ids", [])
                self.table.put_item(Item=_to_dynamo({**merged, "pk": pk, "sk": f"{GOAL_PREFIX}{id_}"}))
            else:
                new_id = id_ or str(_uuid.uuid4())
                incoming_ids.add(new_id)
                fresh = build_stored_goal(normalized, new_id)
                fresh["updated_at"] = now
                self.table.put_item(Item=_to_dynamo({**fresh, "pk": pk, "sk": f"{GOAL_PREFIX}{new_id}"}))

        for s in existing:
            if s.get("id") not in incoming_ids:
                self.table.delete_item(Key={"pk": pk, "sk": f"{GOAL_PREFIX}{s.get('id')}"})

    async def replace_goals(self, pk: str, goals: list) -> None:
        await asyncio.get_running_loop().run_in_executor(None, lambda: self.replace_goals_sync(pk, goals))
