"""DynamoDB-backed store for federation data.

Owns TWO federation concepts (both used by the Express backend, now routed
here instead of federationsController doing direct DynamoDB):

1. Master federation directory — the global directory keyed pk="operator",
   sk="FED#<masterId>" in the POWERLIFTING_USER_FEDERATIONS_TABLE.
   list_master_federations() scans + normalizes; update_master_federation()
   edits one item. (federationsController.listFederations / updateFederation)

2. Per-user federation library — if-health item pk=<user>, sk="federations#v1"
   with shape {federations, qualification_standards}. get_library() reads it raw
   (returning an empty library when absent); set_user_library() replaces it.
   (federationsController.getFederationLibrary / updateFederationLibrary)

NOTE: the AI-side per-user library (sk="federation_library#v1", shape
{entries:[{federation_slug,...}]}) is a DIFFERENT feature owned by
FederationLibraryStore (pl-federation-library layer) — not touched here.
"""
from __future__ import annotations

import asyncio
import random
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

import boto3


def _to_dynamo_value(obj: Any) -> Any:
    """Recursively convert float -> Decimal for DynamoDB write compatibility."""
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: _to_dynamo_value(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_dynamo_value(v) for v in obj]
    return obj


class FederationStore:
    FEDERATIONS_SK = "federations#v1"
    FEDERATIONS_PK = "operator"
    FED_ITEM_SK_PREFIX = "FED#"
    AGE_CATEGORY_VALUES = ("open", "subjunior", "junior", "master1", "master2", "master3", "master4")
    LEVEL_VALUES = ("national", "regional")
    SEX_VALUES = ("male", "female")

    def __init__(self, table_name: str, pk: str = "operator", region: str = "ca-central-1"):
        self._table_name = table_name
        self._pk = pk
        self._region = region
        self._table = None
        self._master_table_obj = None

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

    @property
    def master_table(self):
        """Lazy-load the master federations table (separate from if-health)."""
        if self._master_table_obj is None:
            import os
            name = os.environ.get("POWERLIFTING_USER_FEDERATIONS_TABLE", "if-powerlifting-user-federations")
            self._master_table_obj = boto3.resource("dynamodb", region_name=self._region).Table(name)
        return self._master_table_obj

    def _sanitize_decimals(self, obj: Any) -> Any:
        if isinstance(obj, Decimal):
            return float(obj) if obj % 1 > 0 else int(obj)
        if isinstance(obj, dict):
            return {key: self._sanitize_decimals(value) for key, value in obj.items()}
        if isinstance(obj, list):
            return [self._sanitize_decimals(value) for value in obj]
        return obj

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @classmethod
    def _new_entry_id(cls) -> str:
        return f"std-{int(time.time() * 1000)}-{random.randint(0, 999999)}"

    @staticmethod
    def _is_plain_object(value: Any) -> bool:
        return isinstance(value, dict)

    @classmethod
    def _normalize_string_array(cls, value: Any):
        if not isinstance(value, list):
            return None
        out = [v.strip() for v in value if isinstance(v, str) and v.strip()]
        return out if out else None

    @classmethod
    def _pick_age_category(cls, value: Any):
        if not isinstance(value, str):
            return None
        normalized = value.strip().lower().replace(" ", "").replace("-", "")
        if normalized in cls.AGE_CATEGORY_VALUES:
            return normalized
        mapping = {"masters1": "master1", "masters2": "master2", "masters3": "master3", "masters4": "master4"}
        return mapping.get(normalized)

    @classmethod
    def _pick_sex(cls, value: Any):
        if not isinstance(value, str):
            return None
        normalized = value.strip().lower()
        return normalized if normalized in cls.SEX_VALUES else None

    @classmethod
    def _pick_level(cls, value: Any):
        if not isinstance(value, str):
            return None
        normalized = value.strip().lower()
        return normalized if normalized in cls.LEVEL_VALUES else None

    @staticmethod
    def _to_finite_number(value: Any) -> float:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return value
        if isinstance(value, str) and value.strip():
            try:
                num = float(value)
                if num == num:
                    return num
            except ValueError:
                pass
        return 0

    @classmethod
    def _coerce_entry(cls, raw: Any):
        if not cls._is_plain_object(raw):
            return None
        rid = raw.get("id")
        eid = rid if (isinstance(rid, str) and rid) else cls._new_entry_id()
        total = cls._to_finite_number(raw.get("qualifying_total", raw.get("total")))
        wc = raw.get("weight_class")
        cat = raw.get("category")
        return {
            "id": eid,
            "sex": cls._pick_sex(raw.get("sex")),
            "age_class": cls._pick_age_category(raw.get("age_class")),
            "weight_class": wc.strip() if (isinstance(wc, str) and wc.strip()) else None,
            "level": cls._pick_level(raw.get("level")),
            "category": cat.strip() if (isinstance(cat, str) and cat.strip()) else None,
            "qualifying_total": total,
        }

    @classmethod
    def _entries_from_brackets(cls, brackets: Any) -> list:
        out = []
        if not cls._is_plain_object(brackets):
            return out
        for sex in cls.SEX_VALUES:
            sex_map = brackets.get(sex)
            if not cls._is_plain_object(sex_map):
                continue
            for age_raw, wc_map in sex_map.items():
                if not cls._is_plain_object(wc_map):
                    continue
                age = cls._pick_age_category(age_raw)
                for weight_class, total in wc_map.items():
                    out.append({
                        "id": cls._new_entry_id(),
                        "sex": sex,
                        "age_class": age,
                        "weight_class": weight_class,
                        "qualifying_total": cls._to_finite_number(total),
                    })
        return out

    @classmethod
    def _entries_from_legacy_maps(cls, national: Any, regional: Any) -> list:
        out = []
        for level, mp in (("national", national), ("regional", regional)):
            if not cls._is_plain_object(mp):
                continue
            for weight_class, total in mp.items():
                out.append({
                    "id": cls._new_entry_id(),
                    "level": level,
                    "weight_class": weight_class,
                    "qualifying_total": cls._to_finite_number(total),
                })
        return out

    @classmethod
    def _normalize_entries(cls, raw: Any) -> list:
        if isinstance(raw, list):
            out = []
            for item in raw:
                entry = cls._coerce_entry(item)
                if entry:
                    out.append(entry)
            return out
        if cls._is_plain_object(raw):
            if cls._is_plain_object(raw.get("male")) or cls._is_plain_object(raw.get("female")):
                return cls._entries_from_brackets(raw)
            if cls._is_plain_object(raw.get("national")) or cls._is_plain_object(raw.get("regional")):
                return cls._entries_from_legacy_maps(raw.get("national"), raw.get("regional"))
        return []

    @classmethod
    def _normalize_standard(cls, standard: Any):
        if not cls._is_plain_object(standard):
            return None
        start = standard.get("start_date")
        end = standard.get("end_date")
        entries_src = standard.get("entries", standard)
        return {
            "start_date": start if (isinstance(start, str) and start) else "",
            "end_date": end if (isinstance(end, str) and end) else "",
            "entries": cls._normalize_entries(entries_src),
        }

    @classmethod
    def _normalize_display_options(cls, raw: Any):
        if not cls._is_plain_object(raw):
            return None
        return {
            "show_sex": raw["show_sex"] if isinstance(raw.get("show_sex"), bool) else True,
            "show_age_class": raw["show_age_class"] if isinstance(raw.get("show_age_class"), bool) else True,
            "show_weight_class": raw["show_weight_class"] if isinstance(raw.get("show_weight_class"), bool) else True,
            "show_category": raw["show_category"] if isinstance(raw.get("show_category"), bool) else True,
        }

    @classmethod
    def _normalize_federation(cls, raw: Any) -> dict:
        f = raw if cls._is_plain_object(raw) else {}
        standards_raw = f.get("standards") if cls._is_plain_object(f.get("standards")) else {}
        standards = {}
        if cls._is_plain_object(standards_raw):
            for year, std in standards_raw.items():
                normalized = cls._normalize_standard(std)
                if normalized:
                    standards[year] = normalized
        unit = f.get("standard_unit")
        region = f.get("region")
        created = f.get("created_at")
        updated = f.get("updated_at")
        return {
            "pk": f.get("pk") if isinstance(f.get("pk"), str) else "",
            "sk": f.get("sk") if isinstance(f.get("sk"), str) else "",
            "name": f.get("name") if isinstance(f.get("name"), str) else "",
            "abbreviation": f.get("abbreviation") if isinstance(f.get("abbreviation"), str) else None,
            "region": region.strip() if (isinstance(region, str) and region.strip()) else None,
            "website_url": f.get("website_url") if isinstance(f.get("website_url"), str) else None,
            "status": "archived" if f.get("status") == "archived" else "active",
            "source_slug": f.get("source_slug") if isinstance(f.get("source_slug"), str) else None,
            "has_standards": bool(f.get("has_standards")),
            "standard_unit": unit if unit in ("kg", "dots") else None,
            "standards": standards,
            "display_options": cls._normalize_display_options(f.get("display_options")),
            "parent_federation_abbr": f.get("parent_federation_abbr") if isinstance(f.get("parent_federation_abbr"), str) else None,
            "membership_group": cls._normalize_string_array(f.get("membership_group")),
            "created_at": created if (isinstance(created, str) and created) else cls._now_iso(),
            "updated_at": updated if (isinstance(updated, str) and updated) else cls._now_iso(),
        }

    # ─── Per-user federation#v1 library (if-health) ─────────────────────────────

    def get_library_sync(self) -> dict:
        response = self.table.get_item(Key={"pk": self._pk, "sk": self.FEDERATIONS_SK})
        item = response.get("Item")
        if not item:
            return {
                "pk": self._pk,
                "sk": self.FEDERATIONS_SK,
                "updated_at": self._now_iso(),
                "federations": [],
                "qualification_standards": [],
            }
        return self._sanitize_decimals(item)

    async def get_library(self) -> dict:
        return await asyncio.get_running_loop().run_in_executor(None, self.get_library_sync)

    def set_user_library_sync(self, federations: list, qualification_standards: list) -> dict:
        """Replace the per-user federation#v1 library item (if-health)."""
        item = {
            "pk": self._pk,
            "sk": self.FEDERATIONS_SK,
            "updated_at": self._now_iso(),
            "federations": federations if isinstance(federations, list) else [],
            "qualification_standards": qualification_standards if isinstance(qualification_standards, list) else [],
        }
        self.table.put_item(Item=_to_dynamo_value(item))
        return self._sanitize_decimals(item)

    async def set_user_library(self, federations: list, qualification_standards: list) -> dict:
        return await asyncio.get_running_loop().run_in_executor(
            None, lambda: self.set_user_library_sync(federations, qualification_standards)
        )

    # ─── Master federation directory (POWERLIFTING_USER_FEDERATIONS_TABLE) ───────

    def list_master_federations_sync(self) -> list:
        """Query the master federations table (pk=operator) and normalize each item."""
        from boto3.dynamodb.conditions import Key
        items = []
        last_key = None
        while True:
            kwargs = {"KeyConditionExpression": Key("pk").eq(self.FEDERATIONS_PK)}
            if last_key:
                kwargs["ExclusiveStartKey"] = last_key
            resp = self.master_table.query(**kwargs)
            items.extend(resp.get("Items", []))
            last_key = resp.get("LastEvaluatedKey")
            if not last_key:
                break
        return [self._normalize_federation(it) for it in items]

    async def list_master_federations(self) -> list:
        return await asyncio.get_running_loop().run_in_executor(None, self.list_master_federations_sync)

    def update_master_federation_sync(self, master_id: str, updates: dict) -> None:
        """In-place update of a single master federation item (sk=FED#<masterId>)."""
        names: dict = {}
        values: dict = {}
        sets: list = []
        for i, (k, v) in enumerate(updates.items()):
            names[f"#f{i}"] = k
            values[f":v{i}"] = _to_dynamo_value(v)
            sets.append(f"#f{i} = :v{i}")
        if not sets:
            return
        names["#u"] = "updated_at"
        values[":u"] = self._now_iso()
        sets.append("#u = :u")
        self.master_table.update_item(
            Key={"pk": self.FEDERATIONS_PK, "sk": f"{self.FED_ITEM_SK_PREFIX}{master_id}"},
            UpdateExpression="SET " + ", ".join(sets),
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
        )

    async def update_master_federation(self, master_id: str, updates: dict) -> None:
        await asyncio.get_running_loop().run_in_executor(
            None, lambda: self.update_master_federation_sync(master_id, updates)
        )
