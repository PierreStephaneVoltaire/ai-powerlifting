









from __future__ import annotations
import json
import os
import uuid
import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field

try:
    import lancedb
    from lancedb.pydantic import LanceModel, Vector
    LANCEDB_AVAILABLE = True
except ImportError:
    LANCEDB_AVAILABLE = False
    LanceModel = object
    Vector = lambda dim: None

from .embeddings import embed, get_embedding_dimension

logger = logging.getLogger(__name__)

try:
    from config import FACTS_BASE_PATH
except ImportError:
    FACTS_BASE_PATH = os.getenv("FACTS_BASE_PATH", "./data/facts")

def _get_db_path(context_id: str) -> str:








    return f"{FACTS_BASE_PATH}/{context_id}"

class UserFactSchema(LanceModel):




    id: str
    context_id: str
    user_id: str
    content: str
    vector: Vector(get_embedding_dimension())
    category: str
    source: str
    confidence: float
    active: bool
    superseded_by: Optional[str] = None
    created_at: str
    updated_at: str
    session_key: Optional[str] = None
    metadata_json: str = "{}"

    class Config:
        extra = "ignore"

_tables: Dict[str, Any] = {}

def get_table(context_id: str) -> Any:











    if not LANCEDB_AVAILABLE:
        raise ImportError(
            "lancedb is required for user facts storage. "
            "Install with: pip install lancedb"
        )

    global _tables

    if context_id not in _tables:
        db_path = _get_db_path(context_id)

        if not db_path.startswith("s3://"):
            os.makedirs(os.path.dirname(db_path), exist_ok=True)

        db = lancedb.connect(db_path)

        table_name = "facts"
        if table_name not in db.table_names():
            _tables[context_id] = db.create_table(
                table_name,
                schema=UserFactSchema
            )
            logger.info(f"Created LanceDB table for context: {context_id}")
        else:
            _tables[context_id] = db.open_table(table_name)
            logger.debug(f"Opened existing LanceDB table for context: {context_id}")

    return _tables[context_id]

def clear_table_cache():




    global _tables
    _tables = {}

class UserFactStore:



















    def __init__(self, base_path: str = None):







        if not LANCEDB_AVAILABLE:
            raise ImportError(
                "lancedb is required for user facts storage. "
                "Install with: pip install lancedb"
            )

        self.base_path = base_path or FACTS_BASE_PATH
        logger.info(f"UserFactStore initialized with base path: {self.base_path}")

    def _row_to_dict(self, row: Dict[str, Any]) -> Dict[str, Any]:








        result = dict(row)
        result.pop("vector", None)
        if "metadata_json" in result:
            try:
                result["metadata"] = json.loads(result.get("metadata_json", "{}") or "{}")
            except json.JSONDecodeError:
                result["metadata"] = {}
            del result["metadata_json"]
        if "user_id" in result:
            result["username"] = result["user_id"]
        if "session_key" in result:
            result["cache_key"] = result["session_key"]
        return result

    def _build_filter(
        self,
        active_only: bool = True,
        category: str | None = None,
        user_id: str | None = None
    ) -> str | None:










        conditions = []
        if active_only:
            conditions.append("active = true")
        if category:
            conditions.append(f"category = '{category}'")
        if user_id:
            conditions.append(f"user_id = '{user_id}'")

        if not conditions:
            return None
        elif len(conditions) == 1:
            return conditions[0]
        else:
            return " AND ".join(conditions)

    def add(
        self,
        context_id: str,
        user_id: str,
        content: str,
        category: str,
        source: str,
        confidence: float = 0.8,
        session_key: str | None = None,
        metadata: Dict[str, Any] | None = None,
        fact_id: str | None = None,
        created_at: str | None = None,
        updated_at: str | None = None,
    ) -> str:


















        now = datetime.now(timezone.utc).isoformat()
        fact_id = fact_id or str(uuid.uuid4())
        created_at = created_at or now
        updated_at = updated_at or now

        vector = embed(content)

        row = {
            "id": fact_id,
            "context_id": context_id,
            "user_id": user_id,
            "content": content,
            "vector": vector,
            "category": category,
            "source": source,
            "confidence": confidence,
            "active": True,
            "superseded_by": None,
            "created_at": created_at,
            "updated_at": updated_at,
            "session_key": session_key,
            "metadata_json": json.dumps(metadata) if metadata else "{}",
        }

        table = get_table(context_id)
        table.add([row])

        logger.debug(f"Stored fact: [{category}] {content[:50]}... in context {context_id}")
        return fact_id

    def get(self, context_id: str, fact_id: str) -> Dict[str, Any] | None:









        table = get_table(context_id)

        results = table.search().where(f"id = '{fact_id}'").limit(1).to_list()

        if not results:
            return None

        return self._row_to_dict(results[0])

    def remove(self, context_id: str, fact_id: str) -> bool:












        try:
            table = get_table(context_id)

            existing = self.get(context_id, fact_id)
            if not existing:
                return False

            table.delete(f"id = '{fact_id}'")
            logger.info(f"Removed fact {fact_id} from context {context_id}")
            return True
        except Exception as e:
            logger.warning(f"Failed to remove fact {fact_id}: {e}")
            return False

    def search(
        self,
        context_id: str,
        query: str,
        category: str | None = None,
        user_id: str | None = None,
        active_only: bool = True,
        limit: int = 10
    ) -> List[Dict[str, Any]]:













        table = get_table(context_id)

        query_vector = embed(query)

        search = table.search(query_vector).limit(limit)

        filter_str = self._build_filter(active_only, category, user_id)
        if filter_str:
            search = search.where(filter_str)

        results = search.to_list()

        return [self._row_to_dict(row) for row in results]

    def list_facts(
        self,
        context_id: str,
        category: str | None = None,
        user_id: str | None = None,
        include_inactive: bool = False
    ) -> List[Dict[str, Any]]:











        table = get_table(context_id)

        dim = get_embedding_dimension()
        zero_vector = [0.0] * dim

        filter_str = self._build_filter(not include_inactive, category, user_id)

        search = table.search(zero_vector).limit(10000)
        if filter_str:
            search = search.where(filter_str)

        results = search.to_list()

        return [self._row_to_dict(row) for row in results]

    def supersede(
        self,
        context_id: str,
        old_fact_id: str,
        new_content: str,
        reason: str,
        session_key: str | None = None
    ) -> str:


















        old_fact = self.get(context_id, old_fact_id)
        if not old_fact:
            raise ValueError(f"Fact not found: {old_fact_id}")

        new_fact_id = self.add(
            context_id=context_id,
            user_id=old_fact.get("username", old_fact.get("user_id", "")),
            content=new_content,
            category=old_fact.get("category", "personal"),
            source=old_fact.get("source", "user_stated"),
            confidence=old_fact.get("confidence", 0.8),
            session_key=session_key or old_fact.get("cache_key", ""),
            metadata={
                **old_fact.get("metadata", {}),
                "supersession_reason": reason,
                "superseded_fact_id": old_fact_id,
            },
        )

        table = get_table(context_id)
        table.update(
            where=f"id = '{old_fact_id}'",
            updates={
                "active": False,
                "superseded_by": new_fact_id,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )

        logger.info(f"Superseded fact {old_fact_id} -> {new_fact_id}")
        return new_fact_id

    def log_capability_gap(
        self,
        context_id: str,
        content: str,
        trigger_context: str,
        session_key: str | None = None,
        workaround: str | None = None,
    ) -> str:












        now = datetime.now(timezone.utc).isoformat()

        existing = self.search(
            context_id=context_id,
            query=content,
            category="capability_gap",
            limit=1,
        )

        if existing:
            gap_fact = existing[0]
            gap_metadata = gap_fact.get("metadata", {})

            trigger_count = gap_metadata.get("trigger_count", 0) + 1
            trigger_contexts = gap_metadata.get("trigger_contexts", [])
            trigger_contexts.append(trigger_context)

            gap_metadata["trigger_count"] = trigger_count
            gap_metadata["last_seen"] = now
            gap_metadata["trigger_contexts"] = trigger_contexts
            if workaround and not gap_metadata.get("workaround"):
                gap_metadata["workaround"] = workaround

            gap_metadata["priority_score"] = self._compute_gap_priority(
                trigger_count, now
            )

            table = get_table(context_id)
            table.update(
                where=f"id = '{gap_fact['id']}'",
                updates={
                    "metadata_json": json.dumps(gap_metadata),
                    "updated_at": now,
                }
            )
            return gap_fact["id"]

        gap_metadata = {
            "trigger_count": 1,
            "first_seen": now,
            "last_seen": now,
            "trigger_contexts": [trigger_context],
            "workaround": workaround,
            "status": "open",
            "priority_score": 0.5,
        }

        return self.add(
            context_id=context_id,
            user_id="system",
            content=content,
            category="capability_gap",
            source="model_observed",
            confidence=0.7,
            session_key=session_key,
            metadata=gap_metadata,
        )

    def _compute_gap_priority(self, trigger_count: int, last_seen: str) -> float:




        days_since = 0.0
        if last_seen:
            try:
                last = datetime.fromisoformat(last_seen.replace("Z", "+00:00"))
                days_since = (datetime.now(timezone.utc) - last).days
            except (ValueError, TypeError):
                pass

        recency_weight = 2.718 ** (-0.05 * days_since)

        frequency_weight = min(trigger_count / 20.0, 1.0)

        impact = 0.5

        return (frequency_weight * 0.4) + (recency_weight * 0.3) + (impact * 0.3)

    def list_capability_gaps(
        self,
        context_id: str,
        min_triggers: int = 1
    ) -> List[Dict[str, Any]]:









        facts = self.list_facts(
            context_id=context_id,
            category="capability_gap",
            include_inactive=False,
        )

        gaps = []
        for fact in facts:
            metadata = fact.get("metadata", {})
            if metadata.get("trigger_count", 0) >= min_triggers:
                fact["gap_data"] = metadata
                gaps.append(fact)

        gaps.sort(key=lambda g: g.get("gap_data", {}).get("priority_score", 0), reverse=True)
        return gaps

    @property
    def count(self) -> int:





        return -1

    def count_context(self, context_id: str, active_only: bool = True) -> int:









        facts = self.list_facts(context_id, include_inactive=not active_only)
        return len(facts)

    def get_recent_facts(
        self,
        context_id: str,
        days: int = 30,
        limit: int = 100
    ) -> List[Dict[str, Any]]:










        from datetime import timedelta

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        all_facts = self.list_facts(context_id, include_inactive=False)

        recent = []
        for fact in all_facts:
            created_at_str = fact.get("created_at", "")
            if created_at_str:
                try:
                    created = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                    if created > cutoff:
                        recent.append(fact)
                except (ValueError, TypeError):
                    pass

        recent.sort(key=lambda f: f.get("created_at", ""), reverse=True)
        return recent[:limit]

    def add_with_categorization_tracking(
        self,
        context_id: str,
        user_id: str,
        content: str,
        category: str,
        source: str = "user_stated",
        confidence: float = 0.8,
        session_key: str | None = None,
        metadata: Dict[str, Any] | None = None,
    ) -> str:


















        fact_id = self.add(
            context_id=context_id,
            user_id=user_id,
            content=content,
            category=category,
            source=source,
            confidence=confidence,
            session_key=session_key,
            metadata=metadata,
        )

        fit_score = self._assess_category_fit(context_id, content, category)

        if fit_score < 0.6:
            try:
                content_preview = content[:80] + "..." if len(content) > 80 else content
                meta_content = (
                    f"Fact '{content_preview}' was categorized as {category} "
                    f"but fit score was {fit_score:.2f}. This fact might belong to "
                    f"a category that doesn't exist yet."
                )

                self.add(
                    context_id=context_id,
                    user_id="system",
                    content=meta_content,
                    category="model_assessment",
                    source="model_observed",
                    confidence=0.7,
                    metadata={
                        "original_fact_id": fact_id,
                        "fit_score": fit_score,
                        "categorization_tension": True,
                        "original_category": category,
                    },
                )
            except Exception as e:
                logger.warning(f"Failed to log categorization tension: {e}")

        return fact_id

    def _assess_category_fit(
        self,
        context_id: str,
        content: str,
        category: str
    ) -> float:










        similar = self.search(
            context_id=context_id,
            query=content,
            category=category,
            limit=5,
        )

        if not similar:
            existing = self.list_facts(context_id, category=category)
            if not existing:
                return 0.7
            return 0.5

        fit_score = min(0.6 + (len(similar) * 0.08), 0.95)
        return fit_score

_user_fact_store: Optional[UserFactStore] = None

def get_user_fact_store() -> UserFactStore:










    global _user_fact_store
    if _user_fact_store is None:
        _user_fact_store = UserFactStore()
    return _user_fact_store
