














from __future__ import annotations
import os
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field

try:
    import chromadb
    from chromadb.config import Settings
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False

from config import MEMORY_DB_PATH

@dataclass
class MemoryEntry:









    id: str
    content: str
    category: str
    created_at: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:

        return {
            "id": self.id,
            "content": self.content,
            "category": self.category,
            "created_at": self.created_at,
            **self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> MemoryEntry:

        id_val = data.pop("id")
        content = data.pop("content")
        category = data.pop("category")
        created_at = data.pop("created_at")
        
        return cls(
            id=id_val,
            content=content,
            category=category,
            created_at=created_at,
            metadata=data
        )

class MemoryStore:












    
    def __init__(self, db_path: str = None):






        if not CHROMADB_AVAILABLE:
            raise ImportError(
                "chromadb is required for memory storage. "
                "Install with: pip install chromadb"
            )
        
        self.db_path = db_path or MEMORY_DB_PATH
        
        os.makedirs(self.db_path, exist_ok=True)
        
        self.client = chromadb.PersistentClient(
            path=self.db_path,
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )
        
        self.collection = self.client.get_or_create_collection(
            name="memories",
            metadata={"description": "Operator memory store"}
        )
    
    def add(
        self,
        content: str,
        category: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> MemoryEntry:










        memory_id = str(uuid.uuid4())
        
        created_at = datetime.utcnow().isoformat() + "Z"
        
        full_metadata = {
            "category": category,
            "created_at": created_at,
            **(metadata or {})
        }
        
        self.collection.add(
            ids=[memory_id],
            documents=[content],
            metadatas=[full_metadata]
        )
        
        return MemoryEntry(
            id=memory_id,
            content=content,
            category=category,
            created_at=created_at,
            metadata=metadata or {}
        )
    
    def search(
        self,
        query: str,
        n_results: int = 5,
        category_filter: Optional[str] = None
    ) -> List[MemoryEntry]:










        where = None
        if category_filter:
            where = {"category": category_filter}
        
        results = self.collection.query(
            query_texts=[query],
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances"]
        )
        
        entries = []
        if results["ids"] and results["ids"][0]:
            for i, memory_id in enumerate(results["ids"][0]):
                content = results["documents"][0][i]
                metadata = results["metadatas"][0][i]
                
                category = metadata.pop("category")
                created_at = metadata.pop("created_at")
                
                entries.append(MemoryEntry(
                    id=memory_id,
                    content=content,
                    category=category,
                    created_at=created_at,
                    metadata=metadata
                ))
        
        return entries
    
    def get(self, memory_id: str) -> Optional[MemoryEntry]:








        results = self.collection.get(
            ids=[memory_id],
            include=["documents", "metadatas"]
        )
        
        if not results["ids"]:
            return None
        
        content = results["documents"][0]
        metadata = results["metadatas"][0]
        
        category = metadata.pop("category")
        created_at = metadata.pop("created_at")
        
        return MemoryEntry(
            id=memory_id,
            content=content,
            category=category,
            created_at=created_at,
            metadata=metadata
        )
    
    def remove(self, memory_id: str) -> bool:












        try:
            existing = self.get(memory_id)
            if not existing:
                return False
            
            self.collection.delete(ids=[memory_id])
            return True
        except Exception:
            return False
    
    def list_all(
        self,
        category_filter: Optional[str] = None,
        limit: int = 100
    ) -> List[MemoryEntry]:









        where = None
        if category_filter:
            where = {"category": category_filter}
        
        results = self.collection.get(
            limit=limit,
            where=where,
            include=["documents", "metadatas"]
        )
        
        entries = []
        if results["ids"]:
            for i, memory_id in enumerate(results["ids"]):
                content = results["documents"][i]
                metadata = results["metadatas"][i]
                
                category = metadata.pop("category")
                created_at = metadata.pop("created_at")
                
                entries.append(MemoryEntry(
                    id=memory_id,
                    content=content,
                    category=category,
                    created_at=created_at,
                    metadata=metadata
                ))
        
        return entries
    
    def count(self) -> int:





        return self.collection.count()
    
    def clear(self) -> None:






        self.client.delete_collection("memories")
        self.collection = self.client.create_collection(
            name="memories",
            metadata={"description": "Operator memory store"}
        )

_memory_store: Optional[MemoryStore] = None

def get_memory_store() -> MemoryStore:







    global _memory_store
    if _memory_store is None:
        _memory_store = MemoryStore()
    return _memory_store

def search_memories(query: str, n_results: int = 5) -> List[MemoryEntry]:









    return get_memory_store().search(query, n_results)

def add_memory(content: str, category: str, metadata: Optional[Dict[str, Any]] = None) -> MemoryEntry:










    return get_memory_store().add(content, category, metadata)

def remove_memory(memory_id: str) -> bool:








    return get_memory_store().remove(memory_id)
