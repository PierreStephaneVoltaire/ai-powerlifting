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
        
        # Check for collision
        if any(ex.get("id") == exercise_id for ex in exercises):
            # Try to make it unique
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
            # token_sort_ratio is robust to word reordering
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
