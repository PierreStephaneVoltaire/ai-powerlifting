








from __future__ import annotations
import re
import json
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

@dataclass
class ConversationState:




    cache_key: str
    current_tier: int = 0
    context_tokens: int = 0
    condensation_count: int = 0
    pinned: bool = False
    pinned_tier: Optional[int] = None
    pondering: bool = False
    last_updated: datetime = field(default_factory=datetime.now)

class ConversationCache:









    def __init__(self):

        self._cache: Dict[str, ConversationState] = {}

    def get(self, cache_key: str) -> Optional[ConversationState]:








        return self._cache.get(cache_key)

    def set(self, cache_key: str, state: ConversationState):






        self._cache[cache_key] = state

    def get_or_create(self, cache_key: str) -> ConversationState:








        if cache_key in self._cache:
            return self._cache[cache_key]

        state = ConversationState(cache_key=cache_key)
        self._cache[cache_key] = state
        return state

    def pin(self, cache_key: str, tier: Optional[int] = None) -> Optional[ConversationState]:









        state = self._cache.get(cache_key)
        if state:
            state.pinned = True
            state.pinned_tier = tier if tier is not None else state.current_tier
            state.last_updated = datetime.now()
        return state

    def set_pondering(self, cache_key: str, enabled: bool = True) -> Optional[ConversationState]:









        state = self._cache.get(cache_key)
        if state:
            state.pondering = enabled
            state.last_updated = datetime.now()
        return state

    def evict(self, cache_key: str) -> bool:








        if cache_key in self._cache:
            del self._cache[cache_key]
            return True
        return False

    def clear(self, cache_key: Optional[str] = None):






        if cache_key:
            self._cache.pop(cache_key, None)
        else:
            self._cache.clear()

    def size(self) -> int:

        return len(self._cache)

    async def load_from_storage(self, storage_backend) -> int:










        try:
            from storage.models import RoutingCacheEntry

            with storage_backend.get_session() as session:
                entries = session.query(RoutingCacheEntry).all()
                loaded = 0

                for entry in entries:
                    if entry.is_expired():
                        session.delete(entry)
                        continue

                    state = ConversationState(
                        cache_key=entry.cache_key,
                        current_tier=entry.current_tier or 0,
                        context_tokens=entry.context_tokens or 0,
                        condensation_count=entry.condensation_count or 1,
                        pinned=bool(entry.pinned),
                        pinned_tier=entry.pinned_tier,
                        pondering=bool(entry.pondering) if hasattr(entry, 'pondering') else False,
                        last_updated=datetime.fromisoformat(
                            entry.last_updated.replace("Z", "+00:00")
                        ) if entry.last_updated else datetime.now(),
                    )

                    self._cache[entry.cache_key] = state
                    loaded += 1

                session.commit()
                logger.info(f"[Cache] Loaded {loaded} entries from storage")
                return loaded

        except Exception as e:
            logger.warning(f"[Cache] Failed to load from storage: {e}")
            return 0

    async def persist_entry(self, cache_key: str, storage_backend) -> bool:









        state = self._cache.get(cache_key)
        if not state:
            return False

        try:
            from storage.models import RoutingCacheEntry

            with storage_backend.get_session() as session:
                entry = session.query(RoutingCacheEntry).filter(
                    RoutingCacheEntry.cache_key == cache_key
                ).first()

                if not entry:
                    entry = RoutingCacheEntry(cache_key=cache_key)
                    session.add(entry)

                entry.current_tier = state.current_tier
                entry.context_tokens = state.context_tokens
                entry.condensation_count = state.condensation_count
                entry.pinned = 1 if state.pinned else 0
                entry.pinned_tier = state.pinned_tier
                if hasattr(entry, 'pondering'):
                    entry.pondering = 1 if state.pondering else 0
                entry.touch()

                session.commit()
                return True

        except Exception as e:
            logger.warning(f"[Cache] Failed to persist entry {cache_key}: {e}")
            return False

    async def persist_eviction(self, cache_key: str, storage_backend) -> bool:









        try:
            from storage.models import RoutingCacheEntry

            with storage_backend.get_session() as session:
                entry = session.query(RoutingCacheEntry).filter(
                    RoutingCacheEntry.cache_key == cache_key
                ).first()

                if entry:
                    session.delete(entry)
                    session.commit()

                return True

        except Exception as e:
            logger.warning(f"[Cache] Failed to persist eviction {cache_key}: {e}")
            return False

SOCIAL_PATTERNS = [
    r'^thanks?$',
    r'^thank you$',
    r'^got it$',
    r'^ok$',
    r'^okay$',
    r'^sure$',
    r'^will do$',
    r'^sounds good$',
    r'^perfect$',
    r'^great$',
    r'^awesome$',
    r'^excellent$',
    r'^hi$',
    r'^hello$',
    r'^hey$',
    r'^good morning$',
    r'^good afternoon$',
    r'^good evening$',
    r'^bye$',
    r'^goodbye$',
    r'^see you$',
    r'^later$',
    r'^yes$',
    r'^no$',
    r'^yep$',
    r'^nope$',
    r'^right$',
    r'^correct$',
    r'^exactly$',
    r'^agreed$',
    r'^understood$',
    r'^gotcha$',
    r'^cool$',
    r'^nice$',
    r'^sweet$',
    r'^alright$',
    r'^all right$',
    r'^roger$',
    r'^copy$',
    r'^ack$',
]

def is_social_pattern(message: str) -> bool:











    normalized = message.strip().lower()

    if len(normalized) > 20:
        return False

    for pattern in SOCIAL_PATTERNS:
        if re.match(pattern, normalized):
            return True

    return False

_cache: Optional[ConversationCache] = None

def get_cache() -> ConversationCache:





    global _cache
    if _cache is None:
        _cache = ConversationCache()
    return _cache
