










from .user_facts import (
    UserFact,
    FactCategory,
    FactSource,
    UserFactStore,
    get_user_fact_store,
    CapabilityGap,
    OpinionPair,
    Misconception,
    SessionReflection,
)

from .lancedb_store import (
    get_table,
    clear_table_cache,
    FACTS_BASE_PATH,
)

from .embeddings import (
    embed,
    embed_batch,
    get_embedding_model,
    get_embedding_dimension,
)

try:
    from .store import (
        MemoryStore,
        MemoryEntry,
        get_memory_store,
        search_memories,
        add_memory,
        remove_memory,
    )
    _legacy_available = True
except ImportError:
    _legacy_available = False
    MemoryStore = None
    MemoryEntry = None
    get_memory_store = None
    search_memories = None
    add_memory = None
    remove_memory = None

__all__ = [
    "UserFact",
    "FactCategory",
    "FactSource",
    "UserFactStore",
    "get_user_fact_store",
    "CapabilityGap",
    "OpinionPair",
    "Misconception",
    "SessionReflection",
    "get_table",
    "clear_table_cache",
    "FACTS_BASE_PATH",
    "embed",
    "embed_batch",
    "get_embedding_model",
    "get_embedding_dimension",
    "MemoryStore",
    "MemoryEntry",
    "get_memory_store",
    "search_memories",
    "add_memory",
    "remove_memory",
]
