from __future__ import annotations

import asyncio
import os
from decimal import Decimal
from typing import Any

from boto3.dynamodb.conditions import Key
from rapidfuzz import fuzz

from services.runtime.aws import dynamodb_resource

CATALOG_PK = "CATALOG"
ATHLETE_PREFIX = "ATHLETE#"
SORT_PREFIX = "EXERCISE#"

_TEXT_FIELDS = ("description", "how_to_perform", "why_do_it")
_MUSCLE_FIELDS = ("primary_muscles", "secondary_muscles", "tertiary_muscles")
_DEFINITION_FIELDS = ("name", "category", "fatigue_category", "equipment", "video_url", "lift_transfer")
_PERSONAL_FIELDS = ("fatigue_profile", "fatigue_profile_source", "fatigue_profile_reasoning", "e1rm_estimate", "archived")


def _name_key(name: Any) -> str:
    return " ".join(str(name or "").casefold().split())


def _sanitize_decimals(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value % 1 == 0 else float(value)
    if isinstance(value, dict):
        return {key: _sanitize_decimals(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_decimals(item) for item in value]
    return value


def merge_exercise(catalog: dict | None, overlay: dict | None) -> dict:
    catalog = catalog or {}
    overlay = overlay or {}
    effective: dict[str, Any] = {}
    for key in _DEFINITION_FIELDS + _TEXT_FIELDS + _MUSCLE_FIELDS:
        for source in (catalog, overlay):
            if key in source:
                effective[key] = source[key]
    for key in _PERSONAL_FIELDS:
        if key in overlay:
            effective[key] = overlay[key]
    exercise_id = overlay.get("id") or catalog.get("id")
    if exercise_id:
        effective["id"] = exercise_id
    if "custom" in overlay:
        effective["custom"] = overlay["custom"]
    if catalog:
        if "generic_status" in catalog:
            effective["generic_status"] = catalog["generic_status"]
        if "fatigue_profile" in catalog:
            effective["generic_fatigue_profile"] = catalog["fatigue_profile"]
            if "fatigue_profile" not in overlay:
                effective["fatigue_profile"] = catalog["fatigue_profile"]
                for key in ("fatigue_profile_source", "fatigue_profile_reasoning"):
                    if key in catalog:
                        effective[key] = catalog[key]
    effective["fatigue_profile_personalized"] = "fatigue_profile" in overlay
    return effective


class GlossaryStore:
    def __init__(self, pk: str = "operator", region: str = "ca-central-1", table_name: str | None = None):
        from services.runtime.storage_scope import current_athlete
        self._table_name = table_name or os.environ["GLOSSARY_TABLE_NAME"]
        self._pk = current_athlete.get() or pk
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
            self._table = dynamodb_resource("dynamodb", region_name=self._region).Table(self._table_name)
        return self._table

    def _query(self, pk: str) -> list[dict]:
        items: list[dict] = []
        kwargs: dict[str, Any] = {"KeyConditionExpression": Key("pk").eq(pk)}
        while True:
            page = self.table.query(**kwargs)
            items.extend(page.get("Items", []))
            last = page.get("LastEvaluatedKey")
            if not last:
                return items
            kwargs["ExclusiveStartKey"] = last

    @staticmethod
    def _by_id(items: list[dict]) -> dict[str, dict]:
        indexed = {}
        for item in items:
            sk = str(item.get("sk", ""))
            if sk.startswith(SORT_PREFIX):
                indexed[sk[len(SORT_PREFIX):]] = _sanitize_decimals(item)
        return indexed

    def get_glossary_sync(self) -> list[dict]:
        catalog = self._by_id(self._query(CATALOG_PK))
        overlays = self._by_id(self._query(ATHLETE_PREFIX + self._pk))
        exercises = []
        for exercise_id in sorted(set(catalog) | set(overlays)):
            overlay = overlays.get(exercise_id)
            if overlay and overlay.get("hidden") is True:
                continue
            effective = merge_exercise(catalog.get(exercise_id), overlay)
            effective.setdefault("id", exercise_id)
            exercises.append(effective)
        exercises.sort(key=lambda exercise: str(exercise.get("name") or "").lower())
        return exercises

    async def get_glossary(self) -> list[dict]:
        return await asyncio.get_running_loop().run_in_executor(None, self.get_glossary_sync)

    def fuzzy_resolve_sync(self, name: str, threshold: float = 0.92, exercises: list[dict] | None = None) -> str | None:
        if exercises is None:
            exercises = self.get_glossary_sync()
        best_id, best_score = None, 0.0
        for exercise in exercises:
            score = fuzz.token_sort_ratio(name.lower(), str(exercise.get("name", "")).lower()) / 100.0
            if score > best_score:
                best_id, best_score = exercise.get("id"), score
        return best_id if best_score >= threshold else None

    async def fuzzy_resolve(self, name: str, threshold: float = 0.92, exercises: list[dict] | None = None) -> str | None:
        return await asyncio.get_running_loop().run_in_executor(None, lambda: self.fuzzy_resolve_sync(name, threshold, exercises))
