"""DynamoDB-backed store for the powerlifting budget feature.

Schema (POWERLIFTING_BUDGET_TABLE):
    - Config item:  pk=<user>, sk="CONFIG#budget" -> {config: BudgetConfig, updated_at}
    - Item rows:    pk=<user>, sk="ITEM#<id>"    -> BudgetItem (+ pk/sk)

This module mirrors backend budgetController.ts + db/transforms.ts so the
fission functions are thin async wrappers.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

import boto3
from boto3.dynamodb.conditions import Key

logger = logging.getLogger(__name__)

CONFIG_SK = "CONFIG#budget"
ITEM_PREFIX = "ITEM#"

CATEGORY_VALUES = (
    "equipment", "supplement", "gym_membership", "federation_membership",
    "coaching", "app_subscription", "competition_entry", "transport",
    "accommodation", "food_comp_day", "food_weigh_in", "food_prep",
    "recovery", "other",
)
RECURRENCE_VALUES = ("ONE_TIME", "MONTHLY", "QUARTERLY", "ANNUAL")
PRIORITY_TIER_VALUES = ("MANDATORY", "IMPORTANT", "OPTIONAL")
DATE_PRECISION_VALUES = ("exact", "month")


def _to_finite_number(value) -> float:
    if isinstance(value, (int, float)) and value == value:
        return value
    if isinstance(value, str) and value.strip():
        try:
            num = float(value)
            if num == num:
                return num
        except ValueError:
            pass
    return 0.0


def _pick_enum(value, allowed, fallback):
    return value if isinstance(value, str) and value in allowed else fallback


def _trim_to_null(v):
    if not isinstance(v, str):
        return None
    t = v.strip()
    return t if t else None


def _normalize_category(raw):
    return _pick_enum(raw, CATEGORY_VALUES, "other")


def _normalize_recurrence(raw):
    return _pick_enum(raw, RECURRENCE_VALUES, "ONE_TIME")


def _normalize_priority_tier(raw):
    return _pick_enum(raw, PRIORITY_TIER_VALUES, "OPTIONAL")


def _normalize_date_precision(raw):
    return _pick_enum(raw, DATE_PRECISION_VALUES, "month")


def _default_start_date(precision: str) -> str:
    now = datetime.now(timezone.utc).isoformat()
    return now[:10] if precision == "exact" else now[:7]


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


def _strip_stored(item: dict) -> dict:
    out = dict(item)
    out.pop("pk", None)
    out.pop("sk", None)
    return out


def normalize_budget_item_from_store(stored, pk: str) -> dict:
    r = stored if isinstance(stored, dict) else {}
    purchased_date = _trim_to_null(r.get("purchased_date"))
    recurrence = _normalize_recurrence(r.get("recurrence"))
    competition_id = r.get("competition_id") if isinstance(r.get("competition_id"), str) and r.get("competition_id") else None
    return {
        "id": r.get("id") if isinstance(r.get("id"), str) and r.get("id") else "",
        "user_pk": r.get("user_pk") if isinstance(r.get("user_pk"), str) and r.get("user_pk") else pk,
        "name": r.get("name") if isinstance(r.get("name"), str) else "",
        "category": _normalize_category(r.get("category")),
        "priority_tier": _normalize_priority_tier(r.get("priority_tier")),
        "cost": max(0.0, _to_finite_number(r.get("cost"))),
        "currency": r.get("currency").strip() if isinstance(r.get("currency"), str) and r.get("currency").strip() else "CAD",
        "recurrence": recurrence,
        "date_precision": _normalize_date_precision(r.get("date_precision")),
        "start_date": r.get("start_date") if isinstance(r.get("start_date"), str) and r.get("start_date") else _default_start_date(_normalize_date_precision(r.get("date_precision"))),
        "end_date": None if recurrence == "ONE_TIME" else _trim_to_null(r.get("end_date")),
        "comp_linked": r.get("comp_linked") if isinstance(r.get("comp_linked"), bool) else (competition_id is not None),
        "competition_id": competition_id,
        "purchased": r.get("purchased") if isinstance(r.get("purchased"), bool) else False,
        "purchased_date": purchased_date,
        "notes": _trim_to_null(r.get("notes")),
        "photo_s3_key": _trim_to_null(r.get("photo_s3_key")),
        "cut_by_ai": r.get("cut_by_ai") if isinstance(r.get("cut_by_ai"), bool) else False,
        "created_at": r.get("created_at") if isinstance(r.get("created_at"), str) and r.get("created_at") else datetime.now(timezone.utc).isoformat(),
        "updated_at": r.get("updated_at") if isinstance(r.get("updated_at"), str) and r.get("updated_at") else datetime.now(timezone.utc).isoformat(),
    }


def normalize_budget_item_input(raw, pk: str, item_id: str, existing: Optional[dict], now: str, existing_created_at: Optional[str] = None) -> dict:
    r = raw if isinstance(raw, dict) else {}
    purchased = r.get("purchased") if isinstance(r.get("purchased"), bool) else (existing.get("purchased") if existing else False)
    if isinstance(r.get("purchased_date"), str):
        purchased_date = _trim_to_null(r.get("purchased_date"))
    elif purchased:
        purchased_date = existing.get("purchased_date") if existing and existing.get("purchased_date") else now[:10]
    else:
        purchased_date = None
    precision = _normalize_date_precision(r.get("date_precision") if r.get("date_precision") is not None else (existing.get("date_precision") if existing else None))
    recurrence = _normalize_recurrence(r.get("recurrence") if r.get("recurrence") is not None else (existing.get("recurrence") if existing else None))
    competition_id = _trim_to_null(r.get("competition_id")) if isinstance(r.get("competition_id"), str) else ((existing.get("competition_id") if existing else None))
    comp_linked = r.get("comp_linked") if isinstance(r.get("comp_linked"), bool) else (competition_id is not None)
    start_date = r.get("start_date").strip() if isinstance(r.get("start_date"), str) and r.get("start_date").strip() else ((existing.get("start_date") if existing else None) or _default_start_date(precision))
    return {
        "id": item_id,
        "user_pk": pk,
        "name": r.get("name") if isinstance(r.get("name"), str) else ((existing.get("name") if existing else "") or ""),
        "category": _normalize_category(r.get("category") if r.get("category") is not None else (existing.get("category") if existing else None)),
        "priority_tier": _normalize_priority_tier(r.get("priority_tier") if r.get("priority_tier") is not None else (existing.get("priority_tier") if existing else None)),
        "cost": max(0.0, _to_finite_number(r.get("cost") if r.get("cost") is not None else (existing.get("cost") if existing else None))),
        "currency": r.get("currency").strip() if isinstance(r.get("currency"), str) and r.get("currency").strip() else ((existing.get("currency") if existing else "CAD") or "CAD"),
        "recurrence": recurrence,
        "date_precision": precision,
        "start_date": start_date,
        "end_date": None if recurrence == "ONE_TIME" else (_trim_to_null(r.get("end_date")) if isinstance(r.get("end_date"), str) else (existing.get("end_date") if existing else None)),
        "comp_linked": comp_linked,
        "competition_id": competition_id,
        "purchased": purchased,
        "purchased_date": purchased_date,
        "notes": _trim_to_null(r.get("notes")) if isinstance(r.get("notes"), str) else (existing.get("notes") if existing else None),
        "photo_s3_key": _trim_to_null(r.get("photo_s3_key")) if isinstance(r.get("photo_s3_key"), str) else (existing.get("photo_s3_key") if existing else None),
        "cut_by_ai": r.get("cut_by_ai") if isinstance(r.get("cut_by_ai"), bool) else (existing.get("cut_by_ai") if existing else False),
        "created_at": existing_created_at or (existing.get("created_at") if existing else now),
        "updated_at": now,
    }


def normalize_budget_config_from_store(raw, pk: str) -> dict:
    wrapped = raw.get("config") if isinstance(raw, dict) and isinstance(raw.get("config"), dict) else raw
    r = wrapped if isinstance(wrapped, dict) else {}
    return {
        "user_pk": r.get("user_pk") if isinstance(r.get("user_pk"), str) and r.get("user_pk") else pk,
        "monthly_cap": max(0.0, _to_finite_number(r.get("monthly_cap"))),
        "currency": r.get("currency").strip() if isinstance(r.get("currency"), str) and r.get("currency").strip() else "CAD",
        "notes": _trim_to_null(r.get("notes")),
        "updated_at": r.get("updated_at") if isinstance(r.get("updated_at"), str) and r.get("updated_at") else datetime.now(timezone.utc).isoformat(),
    }


def _month_key(date_str) -> Optional[str]:
    if not isinstance(date_str, str) or not date_str:
        return None
    return date_str[:7] if len(date_str) >= 7 else None


def _recurring_monthly_total(items: list[dict]) -> float:
    return sum(it["cost"] for it in items if it.get("recurrence") == "MONTHLY")


def _spent_this_month(items: list[dict], month: str) -> float:
    total = 0.0
    for it in items:
        if it.get("recurrence") == "MONTHLY":
            start = _month_key(it.get("start_date"))
            end = _month_key(it.get("end_date"))
            at_or_after_start = start <= month if start else True
            at_or_before_end = month <= end if end else True
            if at_or_after_start and at_or_before_end:
                total += it["cost"]
            continue
        effective_date = it.get("purchased_date") or it.get("start_date")
        if _month_key(effective_date) == month:
            total += it["cost"]
    return total


def _empty_breakdown():
    return {"count": 0, "total": 0.0}


def _build_priority_breakdown(items: list[dict], month: str) -> dict:
    by_priority = {tier: _empty_breakdown() for tier in PRIORITY_TIER_VALUES}
    for it in items:
        bucket = by_priority.get(it.get("priority_tier"))
        if not bucket:
            continue
        if it.get("recurrence") == "MONTHLY":
            start = _month_key(it.get("start_date"))
            end = _month_key(it.get("end_date"))
            active = (start <= month if start else True) and (month <= end if end else True)
            if not active:
                continue
            bucket["count"] += 1
            bucket["total"] += it["cost"]
            continue
        effective_date = it.get("purchased_date") or it.get("start_date")
        if _month_key(effective_date) != month:
            continue
        bucket["count"] += 1
        bucket["total"] += it["cost"]
    return by_priority


def _upcoming_one_time(items: list[dict]) -> list[dict]:
    return sorted(
        [it for it in items if it.get("recurrence") == "ONE_TIME" and not it.get("purchased")],
        key=lambda it: str(it.get("start_date") or ""),
    )


def _new_item_id() -> str:
    import time
    return f"item-{int(time.time())}"


class BudgetStore:
    """DynamoDB-backed store for budget config + items (mirrors budgetController)."""

    def __init__(self, table_name: str, pk: str = "operator", region: str = "ca-central-1"):
        self._table_name = table_name
        self._pk = pk
        self._region = region
        self._table = None

    @property
    def pk(self) -> str:
        return self._pk

    @pk.setter
    def pk(self, value: str) -> None:
        self._pk = value

    @property
    def table(self):
        if self._table is None:
            self._table = boto3.resource("dynamodb", region_name=self._region).Table(self._table_name)
        return self._table

    def _query_items_sync(self, pk: str) -> list[dict]:
        items: list[dict] = []
        last_key = None
        while True:
            kwargs = {"KeyConditionExpression": Key("pk").eq(pk) & Key("sk").begins_with(ITEM_PREFIX)}
            if last_key:
                kwargs["ExclusiveStartKey"] = last_key
            resp = self.table.query(**kwargs)
            items.extend(resp.get("Items") or [])
            last_key = resp.get("LastEvaluatedKey")
            if not last_key:
                break
        return [_sanitize_decimals(i) for i in items]

    def get_config_sync(self, pk: str) -> dict:
        resp = self.table.get_item(Key={"pk": pk, "sk": CONFIG_SK})
        return normalize_budget_config_from_store(_sanitize_decimals(resp.get("Item")), pk)

    async def get_config(self, pk: str) -> dict:
        return await asyncio.get_running_loop().run_in_executor(None, lambda: self.get_config_sync(pk))

    def put_config_sync(self, pk: str, raw) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        config = normalize_budget_config_from_store(raw, pk)
        config["updated_at"] = now
        self.table.put_item(Item=_to_dynamo({"pk": pk, "sk": CONFIG_SK, "config": config, "updated_at": now}))
        return config

    async def put_config(self, pk: str, raw) -> dict:
        return await asyncio.get_running_loop().run_in_executor(None, lambda: self.put_config_sync(pk, raw))

    def list_items_sync(self, pk: str, filters: Optional[dict] = None) -> list[dict]:
        stored = self._query_items_sync(pk)
        items = [normalize_budget_item_from_store(_strip_stored(s), pk) for s in stored]
        if not filters:
            return items
        comp_id = filters.get("comp_id")
        category = filters.get("category")
        priority = filters.get("priority")
        out = []
        for it in items:
            if comp_id is not None and (it.get("competition_id") or None) != comp_id:
                continue
            if category is not None and it.get("category") != category:
                continue
            if priority is not None and it.get("priority_tier") != priority:
                continue
            out.append(it)
        return out

    async def list_items(self, pk: str, filters: Optional[dict] = None) -> list[dict]:
        return await asyncio.get_running_loop().run_in_executor(None, lambda: self.list_items_sync(pk, filters))

    def create_item_sync(self, pk: str, raw) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        item = normalize_budget_item_input(raw, pk, _new_item_id(), None, now)
        self.table.put_item(Item=_to_dynamo({**item, "pk": pk, "sk": f"{ITEM_PREFIX}{item['id']}"}))
        return item

    async def create_item(self, pk: str, raw) -> dict:
        return await asyncio.get_running_loop().run_in_executor(None, lambda: self.create_item_sync(pk, raw))

    def update_item_sync(self, pk: str, item_id: str, raw) -> dict:
        stored = self._query_items_sync(pk)
        existing = next((s for s in stored if s.get("id") == item_id), None)
        if not existing:
            raise ValueError(f"Budget item {item_id} not found")
        normalized = normalize_budget_item_from_store(_strip_stored(existing), pk)
        updated = normalize_budget_item_input(raw, pk, item_id, normalized, datetime.now(timezone.utc).isoformat())
        self.table.put_item(Item=_to_dynamo({**updated, "pk": pk, "sk": f"{ITEM_PREFIX}{item_id}"}))
        return updated

    async def update_item(self, pk: str, item_id: str, raw) -> dict:
        return await asyncio.get_running_loop().run_in_executor(None, lambda: self.update_item_sync(pk, item_id, raw))

    def delete_item_sync(self, pk: str, item_id: str) -> None:
        stored = self._query_items_sync(pk)
        existing = next((s for s in stored if s.get("id") == item_id), None)
        if not existing:
            raise ValueError(f"Budget item {item_id} not found")
        self.table.delete_item(Key={"pk": pk, "sk": f"{ITEM_PREFIX}{item_id}"})

    async def delete_item(self, pk: str, item_id: str) -> None:
        await asyncio.get_running_loop().run_in_executor(None, lambda: self.delete_item_sync(pk, item_id))

    def get_summary_sync(self, pk: str, month: str) -> dict:
        config = self.get_config_sync(pk)
        stored = self._query_items_sync(pk)
        items = [normalize_budget_item_from_store(_strip_stored(s), pk) for s in stored]
        return {
            "monthly_cap": config.get("monthly_cap"),
            "currency": config.get("currency"),
            "spent_this_month": _spent_this_month(items, month),
            "recurring_monthly_total": _recurring_monthly_total(items),
            "items_by_priority": _build_priority_breakdown(items, month),
            "upcoming_one_time": _upcoming_one_time(items),
        }

    async def get_summary(self, pk: str, month: str) -> dict:
        return await asyncio.get_running_loop().run_in_executor(None, lambda: self.get_summary_sync(pk, month))