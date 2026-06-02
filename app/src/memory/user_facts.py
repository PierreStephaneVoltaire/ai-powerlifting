




























from __future__ import annotations
import uuid
import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)

class FactCategory(str, Enum):

    PERSONAL = "personal"
    PREFERENCE = "preference"
    OPINION = "opinion"
    SKILL = "skill"
    LIFE_EVENT = "life_event"
    FUTURE_DIRECTION = "future_direction"
    PROJECT_DIRECTION = "project_direction"
    MENTAL_STATE = "mental_state"
    CONVERSATION_SUMMARY = "conversation_summary"
    TOPIC_LOG = "topic_log"
    MODEL_ASSESSMENT = "model_assessment"

    AGENT_IDENTITY = "agent_identity"
    AGENT_OPINION = "agent_opinion"
    AGENT_PRINCIPLE = "agent_principle"

    CAPABILITY_GAP = "capability_gap"
    TOOL_SUGGESTION = "tool_suggestion"

    OPINION_PAIR = "opinion_pair"

    MISCONCEPTION = "misconception"
    INTEREST_AREA = "interest_area"

    SESSION_REFLECTION = "session_reflection"

class FactSource(str, Enum):

    USER_STATED = "user_stated"
    MODEL_OBSERVED = "model_observed"
    MODEL_ASSESSED = "model_assessed"
    CONVERSATION_DERIVED = "conversation_derived"

@dataclass
class UserFact:

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    context_id: str = ""
    username: str = ""
    content: str = ""
    category: FactCategory = FactCategory.PERSONAL
    source: FactSource = FactSource.USER_STATED
    confidence: float = 0.8
    cache_key: str = ""
    created_at: str = ""
    updated_at: str = ""
    superseded_by: str | None = None
    active: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:

        return {
            "id": self.id,
            "context_id": self.context_id,
            "username": self.username,
            "content": self.content,
            "category": self.category.value,
            "source": self.source.value,
            "confidence": self.confidence,
            "cache_key": self.cache_key,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "superseded_by": self.superseded_by,
            "active": self.active,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UserFact":

        return cls(
            id=data.get("id", str(uuid.uuid4())),
            context_id=data.get("context_id", ""),
            username=data.get("username", ""),
            content=data.get("content", ""),
            category=FactCategory(data.get("category", "personal")),
            source=FactSource(data.get("source", "user_stated")),
            confidence=data.get("confidence", 0.8),
            cache_key=data.get("cache_key", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            superseded_by=data.get("superseded_by"),
            active=data.get("active", True),
            metadata=data.get("metadata", {}),
        )

@dataclass
class CapabilityGap:

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    content: str = ""
    trigger_count: int = 1
    first_seen: str = ""
    last_seen: str = ""
    trigger_contexts: list[str] = field(default_factory=list)
    workaround: str | None = None
    suggested_tool: str | None = None
    acceptance_criteria: list[str] = field(default_factory=list)
    status: str = "open"
    priority_score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "trigger_count": self.trigger_count,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "trigger_contexts": self.trigger_contexts,
            "workaround": self.workaround,
            "suggested_tool": self.suggested_tool,
            "acceptance_criteria": self.acceptance_criteria,
            "status": self.status,
            "priority_score": self.priority_score,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CapabilityGap":
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            content=data.get("content", ""),
            trigger_count=data.get("trigger_count", 1),
            first_seen=data.get("first_seen", ""),
            last_seen=data.get("last_seen", ""),
            trigger_contexts=data.get("trigger_contexts", []),
            workaround=data.get("workaround"),
            suggested_tool=data.get("suggested_tool"),
            acceptance_criteria=data.get("acceptance_criteria", []),
            status=data.get("status", "open"),
            priority_score=data.get("priority_score", 0.0),
        )

@dataclass
class OpinionPair:

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    topic: str = ""
    user_position: str = ""
    agent_position: str = ""
    agent_reasoning: str = ""
    agent_confidence: float = 0.7
    agreement_level: str = "partial"
    evolution: list[dict] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "topic": self.topic,
            "user_position": self.user_position,
            "agent_position": self.agent_position,
            "agent_reasoning": self.agent_reasoning,
            "agent_confidence": self.agent_confidence,
            "agreement_level": self.agreement_level,
            "evolution": self.evolution,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OpinionPair":
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            topic=data.get("topic", ""),
            user_position=data.get("user_position", ""),
            agent_position=data.get("agent_position", ""),
            agent_reasoning=data.get("agent_reasoning", ""),
            agent_confidence=data.get("agent_confidence", 0.7),
            agreement_level=data.get("agreement_level", "partial"),
            evolution=data.get("evolution", []),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )

@dataclass
class Misconception:

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    topic: str = ""
    what_they_said: str = ""
    what_is_correct: str = ""
    domain: str = ""
    severity: str = "minor"
    corrected_in_session: bool = True
    recurrence_count: int = 0
    suggested_resources: list[str] = field(default_factory=list)
    created_at: str = ""
    last_seen: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "topic": self.topic,
            "what_they_said": self.what_they_said,
            "what_is_correct": self.what_is_correct,
            "domain": self.domain,
            "severity": self.severity,
            "corrected_in_session": self.corrected_in_session,
            "recurrence_count": self.recurrence_count,
            "suggested_resources": self.suggested_resources,
            "created_at": self.created_at,
            "last_seen": self.last_seen,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Misconception":
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            topic=data.get("topic", ""),
            what_they_said=data.get("what_they_said", ""),
            what_is_correct=data.get("what_is_correct", ""),
            domain=data.get("domain", ""),
            severity=data.get("severity", "minor"),
            corrected_in_session=data.get("corrected_in_session", True),
            recurrence_count=data.get("recurrence_count", 0),
            suggested_resources=data.get("suggested_resources", []),
            created_at=data.get("created_at", ""),
            last_seen=data.get("last_seen", ""),
        )

@dataclass
class SessionReflection:

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    summary: str = ""
    what_worked: list[str] = field(default_factory=list)
    what_failed: list[str] = field(default_factory=list)
    operator_satisfaction: str = "neutral"
    new_facts_stored: int = 0
    capability_gaps_hit: list[str] = field(default_factory=list)
    misconceptions_found: list[str] = field(default_factory=list)
    open_threads: list[str] = field(default_factory=list)
    meta_notes: str = ""
    preset_used: str = ""
    preset_fit_score: float = 0.0
    created_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "summary": self.summary,
            "what_worked": self.what_worked,
            "what_failed": self.what_failed,
            "operator_satisfaction": self.operator_satisfaction,
            "new_facts_stored": self.new_facts_stored,
            "capability_gaps_hit": self.capability_gaps_hit,
            "misconceptions_found": self.misconceptions_found,
            "open_threads": self.open_threads,
            "meta_notes": self.meta_notes,
            "preset_used": self.preset_used,
            "preset_fit_score": self.preset_fit_score,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionReflection":
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            session_id=data.get("session_id", ""),
            summary=data.get("summary", ""),
            what_worked=data.get("what_worked", []),
            what_failed=data.get("what_failed", []),
            operator_satisfaction=data.get("operator_satisfaction", "neutral"),
            new_facts_stored=data.get("new_facts_stored", 0),
            capability_gaps_hit=data.get("capability_gaps_hit", []),
            misconceptions_found=data.get("misconceptions_found", []),
            open_threads=data.get("open_threads", []),
            meta_notes=data.get("meta_notes", ""),
            preset_used=data.get("preset_used", ""),
            preset_fit_score=data.get("preset_fit_score", 0.0),
            created_at=data.get("created_at", ""),
        )

class UserFactStore:



















    def __init__(self, base_path: str = None):







        from .lancedb_store import UserFactStore as LanceDBStore
        self._store = LanceDBStore(base_path)

    def add(
        self,
        context_id: str,
        content: str,
        category: FactCategory | str,
        source: FactSource | str = FactSource.USER_STATED,
        username: str = "",
        confidence: float = 0.8,
        cache_key: str = "",
        metadata: Dict[str, Any] | None = None,
        fact: UserFact | None = None,
    ) -> str:


















        if fact is not None:
            context_id = fact.context_id or context_id
            content = fact.content
            category = fact.category
            source = fact.source
            username = fact.username
            confidence = fact.confidence
            cache_key = fact.cache_key
            metadata = fact.metadata
            fact_id = fact.id
            created_at = fact.created_at
            updated_at = fact.updated_at
        else:
            fact_id = None
            created_at = None
            updated_at = None

        category_str = category.value if isinstance(category, FactCategory) else category
        source_str = source.value if isinstance(source, FactSource) else source

        return self._store.add(
            context_id=context_id,
            user_id=username,
            content=content,
            category=category_str,
            source=source_str,
            confidence=confidence,
            session_key=cache_key,
            metadata=metadata,
            fact_id=fact_id,
            created_at=created_at,
            updated_at=updated_at,
        )

    def search(
        self,
        context_id: str,
        query: str,
        category: FactCategory | None = None,
        username: str | None = None,
        limit: int = 5,
        active_only: bool = True
    ) -> List[UserFact]:













        category_str = category.value if category and isinstance(category, FactCategory) else None

        results = self._store.search(
            context_id=context_id,
            query=query,
            category=category_str,
            user_id=username,
            active_only=active_only,
            limit=limit,
        )

        return [UserFact.from_dict(r) for r in results]

    def get(self, context_id: str, fact_id: str) -> UserFact | None:









        result = self._store.get(context_id, fact_id)
        if result is None:
            return None
        return UserFact.from_dict(result)

    def supersede(
        self,
        context_id: str,
        old_fact_id: str,
        new_content: str,
        reason: str,
        cache_key: str = ""
    ) -> UserFact:


















        new_id = self._store.supersede(
            context_id=context_id,
            old_fact_id=old_fact_id,
            new_content=new_content,
            reason=reason,
            session_key=cache_key,
        )

        new_fact = self.get(context_id, new_id)
        return new_fact

    def list_facts(
        self,
        context_id: str,
        category: FactCategory | None = None,
        username: str | None = None,
        include_history: bool = False
    ) -> List[UserFact]:











        category_str = category.value if category and isinstance(category, FactCategory) else None

        results = self._store.list_facts(
            context_id=context_id,
            category=category_str,
            user_id=username,
            include_inactive=include_history,
        )

        return [UserFact.from_dict(r) for r in results]

    def remove(self, context_id: str, fact_id: str) -> bool:












        return self._store.remove(context_id, fact_id)

    @property
    def count(self) -> int:




        return self._store.count

    def count_context(self, context_id: str, active_only: bool = True) -> int:









        return self._store.count_context(context_id, active_only)

    def list_by_category(self, context_id: str, category: FactCategory) -> List[UserFact]:









        return self.list_facts(context_id, category=category, include_history=False)

    def get_recent_facts(self, context_id: str, days: int = 30, limit: int = 100) -> List[UserFact]:










        results = self._store.get_recent_facts(context_id, days, limit)
        return [UserFact.from_dict(r) for r in results]

    def get_all_facts(self, context_id: str) -> List[UserFact]:








        return self.list_facts(context_id, include_history=True)

    @property
    def active_count(self) -> int:




        return self.count

    def log_capability_gap(
        self,
        context_id: str,
        content: str,
        trigger_context: str,
        cache_key: str = "",
        workaround: str | None = None,
    ) -> str:












        return self._store.log_capability_gap(
            context_id=context_id,
            content=content,
            trigger_context=trigger_context,
            session_key=cache_key,
            workaround=workaround,
        )

    def list_capability_gaps(self, context_id: str, min_triggers: int = 1) -> List[CapabilityGap]:









        results = self._store.list_capability_gaps(context_id, min_triggers)

        gaps = []
        for r in results:
            gap_data = r.get("gap_data", {})
            gap = CapabilityGap.from_dict(gap_data)
            gap.id = r.get("id", gap.id)
            gaps.append(gap)

        return gaps

    def add_with_categorization_tracking(
        self,
        context_id: str,
        content: str,
        category: FactCategory,
        source: FactSource = FactSource.USER_STATED,
        confidence: float = 0.8,
        cache_key: str = "",
        metadata: dict | None = None,
        username: str = "",
    ) -> str:


















        category_str = category.value if isinstance(category, FactCategory) else category
        source_str = source.value if isinstance(source, FactSource) else source

        return self._store.add_with_categorization_tracking(
            context_id=context_id,
            user_id=username,
            content=content,
            category=category_str,
            source=source_str,
            confidence=confidence,
            session_key=cache_key,
            metadata=metadata,
        )

_user_fact_store: Optional[UserFactStore] = None

def get_user_fact_store() -> UserFactStore:










    global _user_fact_store
    if _user_fact_store is None:
        _user_fact_store = UserFactStore()
    return _user_fact_store
