"""DynamoDB-backed write-side for the exercise glossary.

Schema:
    - Glossary item: pk="operator", sk="glossary#v1" -> {exercises: list[dict]}
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

import boto3
from rapidfuzz import fuzz

logger = logging.getLogger(__name__)

class GlossaryStore:
    """DynamoDB-backed store for the exercise glossary."""

    GLOSSARY_SK = "glossary#v1"

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
            self._table = boto3.resource(
                "dynamodb", region_name=self._region
            ).Table(self._table_name)
        return self._table

    def _floats_to_decimals(self, obj: Any) -> Any:
        if isinstance(obj, float):
            return Decimal(str(obj))
        if isinstance(obj, dict):
            return {k: self._floats_to_decimals(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._floats_to_decimals(v) for v in obj]
        return obj

    def _sanitize_decimals(self, obj: Any) -> Any:
        if isinstance(obj, Decimal):
            return float(obj) if obj % 1 > 0 else int(obj)
        if isinstance(obj, dict):
            return {k: self._sanitize_decimals(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._sanitize_decimals(v) for v in obj]
        return obj

    def _normalize_exercise(self, exercise: dict) -> dict:
        normalized = dict(exercise)
        normalized.pop("cues", None)
        normalized.pop("notes", None)
        normalized["description"] = str(normalized.get("description") or "")
        normalized["how_to_perform"] = str(normalized.get("how_to_perform") or "")
        normalized["why_do_it"] = str(normalized.get("why_do_it") or "")
        normalized["tertiary_muscles"] = normalized.get("tertiary_muscles") or []
        if "video_url" in normalized:
            video_url = str(normalized.get("video_url") or "").strip()
            if video_url:
                normalized["video_url"] = video_url
            else:
                normalized.pop("video_url", None)
        return normalized

    def _to_canonical(self, exercise: dict) -> dict:
        """Normalize an exercise into the canonical stored shape (mirrors backend
        normalizeExercise): arrays default to [], text trimmed, cues/notes dropped."""
        normalized = self._normalize_exercise(exercise)
        normalized["name"] = str(normalized.get("name") or "").strip()
        normalized["primary_muscles"] = (
            normalized.get("primary_muscles")
            if isinstance(normalized.get("primary_muscles"), list)
            else []
        )
        normalized["secondary_muscles"] = (
            normalized.get("secondary_muscles")
            if isinstance(normalized.get("secondary_muscles"), list)
            else []
        )
        normalized["tertiary_muscles"] = (
            normalized.get("tertiary_muscles")
            if isinstance(normalized.get("tertiary_muscles"), list)
            else []
        )
        return normalized

    def _slugify(self, text: str) -> str:
        text = text.lower()
        text = re.sub(r"[^\w\s-]", "", text)
        text = re.sub(r"[\s-]+", "_", text)
        return text.strip("_")

    def _invalidate_analysis_cache(self) -> None:
        try:
            from cache_invalidation import invalidate_analysis_caches
            invalidate_analysis_caches(self._pk, self._table_name, self._region)
        except Exception as exc:
            logger.warning("[GlossaryStore] Analysis cache invalidation failed: %s", exc)

    def get_glossary_sync(self) -> list[dict]:
        resp = self.table.get_item(Key={"pk": self._pk, "sk": self.GLOSSARY_SK})
        item = resp.get("Item")
        if not item:
            return []
        return self._sanitize_decimals(item.get("exercises", []))

    async def get_glossary(self) -> list[dict]:
        return await asyncio.get_running_loop().run_in_executor(
            None, lambda: self.get_glossary_sync()
        )

    def add_exercise_sync(self, exercise: dict) -> str:
        exercises = self.get_glossary_sync()
        
        name = exercise.get("name", "")
        if not name:
            raise ValueError("Exercise name is required")
            
        exercise_id = self._slugify(name)
        
        if any(ex.get("id") == exercise_id for ex in exercises):
            i = 1
            while any(ex.get("id") == f"{exercise_id}_{i}" for ex in exercises):
                i += 1
            exercise_id = f"{exercise_id}_{i}"
            
        new_exercise = self._normalize_exercise({
            **exercise,
            "id": exercise_id,
            "name": name,
        })
        
        exercises.append(new_exercise)
        
        self.table.put_item(Item=self._floats_to_decimals({
            "pk": self._pk,
            "sk": self.GLOSSARY_SK,
            "exercises": exercises,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }))
        self._invalidate_analysis_cache()
        
        return exercise_id

    async def add_exercise(self, exercise: dict) -> str:
        return await asyncio.get_running_loop().run_in_executor(
            None, lambda: self.add_exercise_sync(exercise)
        )

    def update_exercise_sync(self, exercise_id: str, fields: dict) -> None:
        exercises = self.get_glossary_sync()
        
        found = False
        for i, ex in enumerate(exercises):
            if ex.get("id") == exercise_id:
                next_exercise = dict(ex)
                next_exercise.update(fields)
                exercises[i] = self._normalize_exercise(next_exercise)
                found = True
                break
                
        if not found:
            raise ValueError(f"Exercise not found: {exercise_id}")
            
        self.table.put_item(Item=self._floats_to_decimals({
            "pk": self._pk,
            "sk": self.GLOSSARY_SK,
            "exercises": exercises,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }))
        self._invalidate_analysis_cache()

    async def update_exercise(self, exercise_id: str, fields: dict) -> None:
        await asyncio.get_running_loop().run_in_executor(
            None, lambda: self.update_exercise_sync(exercise_id, fields)
        )

    def set_e1rm_sync(
        self, 
        exercise_id: str, 
        value_kg: float, 
        method: str = "manual", 
        basis: str = "", 
        confidence: str = "high", 
        manually_overridden: bool = True
    ) -> None:
        estimate = {
            "value_kg": value_kg,
            "method": method,
            "basis": basis,
            "confidence": confidence,
            "set_at": datetime.now(timezone.utc).isoformat(),
            "manually_overridden": manually_overridden
        }
        self.update_exercise_sync(exercise_id, {"e1rm_estimate": estimate})

    async def set_e1rm(self, *args, **kwargs) -> None:
        await asyncio.get_running_loop().run_in_executor(
            None, lambda: self.set_e1rm_sync(*args, **kwargs)
        )

    def fuzzy_resolve_sync(self, name: str, threshold: float = 0.92) -> str | None:
        exercises = self.get_glossary_sync()
        if not exercises:
            return None
            
        best_id = None
        best_score = 0
        
        for ex in exercises:
            ex_name = ex.get("name", "")
            score = fuzz.token_sort_ratio(name.lower(), ex_name.lower()) / 100.0
            if score > best_score:
                best_score = score
                best_id = ex.get("id")
                
        if best_score >= threshold:
            return best_id
        return None

    async def fuzzy_resolve(self, name: str, threshold: float = 0.92) -> str | None:
        return await asyncio.get_running_loop().run_in_executor(
            None, lambda: self.fuzzy_resolve_sync(name, threshold)
        )

    # ─── Full glossary store read/write (mirrors backend exerciseController) ──

    def get_full_store_sync(self) -> dict:
        """Return the full glossary record including pk/sk/updated_at/exercises."""
        resp = self.table.get_item(Key={"pk": self._pk, "sk": self.GLOSSARY_SK})
        item = resp.get("Item")
        if not item:
            now = datetime.now(timezone.utc).isoformat()
            return {
                "pk": self._pk,
                "sk": self.GLOSSARY_SK,
                "exercises": [],
                "updated_at": now,
            }
        return self._sanitize_decimals(item)

    async def get_full_store(self) -> dict:
        return await asyncio.get_running_loop().run_in_executor(
            None, lambda: self.get_full_store_sync()
        )

    def _persist_glossary_sync(self, glossary: dict) -> None:
        glossary = dict(glossary)
        glossary["pk"] = self._pk
        glossary["sk"] = self.GLOSSARY_SK
        glossary["updated_at"] = datetime.now(timezone.utc).isoformat()
        exercises = glossary.get("exercises", []) or []
        glossary["exercises"] = [self._to_canonical(ex) for ex in exercises]
        self.table.put_item(Item=self._floats_to_decimals(glossary))
        self._invalidate_analysis_cache()

    def remove_exercise_sync(self, exercise_id: str) -> None:
        """Delete an exercise by id from the glossary."""
        glossary = self.get_full_store_sync()
        exercises = glossary.get("exercises", []) or []
        glossary["exercises"] = [ex for ex in exercises if ex.get("id") != exercise_id]
        self._persist_glossary_sync(glossary)

    async def remove_exercise(self, exercise_id: str) -> None:
        await asyncio.get_running_loop().run_in_executor(
            None, lambda: self.remove_exercise_sync(exercise_id)
        )

    def set_archived_sync(self, exercise_id: str, archived: bool) -> None:
        """Toggle the archived flag on an exercise."""
        glossary = self.get_full_store_sync()
        exercises = glossary.get("exercises", []) or []
        changed = False
        for ex in exercises:
            if ex.get("id") == exercise_id:
                ex["archived"] = archived
                changed = True
                break
        if not changed:
            return
        glossary["exercises"] = exercises
        self._persist_glossary_sync(glossary)

    async def set_archived(self, exercise_id: str, archived: bool) -> None:
        await asyncio.get_running_loop().run_in_executor(
            None, lambda: self.set_archived_sync(exercise_id, archived)
        )

    def search_exercises_sync(self, query: str) -> list[dict]:
        """Case-insensitive substring search across glossary exercises."""
        exercises = self.get_glossary_sync()
        if not query:
            return exercises
        lower = query.lower()
        results = []
        for ex in exercises:
            name = str(ex.get("name", "") or "")
            description = str(ex.get("description", "") or "")
            how_to = str(ex.get("how_to_perform", "") or "")
            why = str(ex.get("why_do_it", "") or "")
            primary = ex.get("primary_muscles", []) or []
            secondary = ex.get("secondary_muscles", []) or []
            tertiary = ex.get("tertiary_muscles", []) or []
            muscles = primary + secondary + tertiary
            if (
                lower in name.lower()
                or lower in description.lower()
                or lower in how_to.lower()
                or lower in why.lower()
                or any(lower in str(m).lower() for m in muscles)
            ):
                results.append(ex)
        return results

    async def search_exercises(self, query: str) -> list[dict]:
        return await asyncio.get_running_loop().run_in_executor(
            None, lambda: self.search_exercises_sync(query)
        )

    def upsert_exercise_sync(self, exercise: dict) -> str:
        """Insert or update an exercise by id (generates a uuid if missing)."""
        glossary = self.get_full_store_sync()
        exercises = list(glossary.get("exercises", []) or [])
        import uuid as _uuid
        exercise_id = exercise.get("id") or str(_uuid.uuid4())
        exercise = dict(exercise)
        exercise["id"] = exercise_id
        exercise = self._to_canonical(exercise)
        existing_index = None
        for i, ex in enumerate(exercises):
            if ex.get("id") == exercise_id:
                existing_index = i
                break
        if existing_index is not None:
            exercises[existing_index] = exercise
        else:
            exercises.append(exercise)
        exercises.sort(key=lambda e: str(e.get("name", "") or "").lower())
        glossary["exercises"] = exercises
        self._persist_glossary_sync(glossary)
        return exercise_id

    async def upsert_exercise(self, exercise: dict) -> str:
        return await asyncio.get_running_loop().run_in_executor(
            None, lambda: self.upsert_exercise_sync(exercise)
        )

    def get_exercise_by_id_sync(self, exercise_id: str) -> dict | None:
        for ex in self.get_glossary_sync():
            if ex.get("id") == exercise_id:
                return ex
        return None

    async def get_exercise_by_id(self, exercise_id: str) -> dict | None:
        return await asyncio.get_running_loop().run_in_executor(
            None, lambda: self.get_exercise_by_id_sync(exercise_id)
        )
