"""ChromaDB-backed RAG for health documents.

Indexes PDF documents (IPF rulebook, anti-doping list, supplement PDFs) and
provides semantic search capabilities.

Uses SHA256 hash-based incremental indexing to avoid re-processing unchanged files.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

try:
    from tika import parser as tika_parser
    TIKA_AVAILABLE = True
except ImportError:
    TIKA_AVAILABLE = False
    logger.warning("[HealthDocsRAG] Apache Tika not available. PDF extraction will fail.")

class HealthDocsRAG:
    """ChromaDB-backed RAG for health documents.
    
    Indexes PDFs from docs_dir and provides semantic search.
    Uses hash-based incremental indexing to avoid re-processing unchanged files.
    """
    
    COLLECTION_NAME = "health_docs"
    HASH_FILE = ".index_hashes.json"
    CHUNK_SIZE_TOKENS = 500
    CHUNK_OVERLAP_TOKENS = 50
    
    def __init__(self, docs_dir: str, chroma_client: Any):
        """Initialize the RAG system.
        
        Args:
            docs_dir: Directory containing health PDF documents
            chroma_client: Existing ChromaDB client instance
        """
        self._docs_dir = Path(docs_dir)
        self._client = chroma_client
        self._collection = None
        self._hash_file = self._docs_dir / self.HASH_FILE
        
        logger.debug(f"[HealthDocsRAG] Initialized with docs_dir={docs_dir}")
    
    def _get_or_create_collection(self) -> Any:
        """Get or create the ChromaDB collection."""
        if self._collection is None:
            self._collection = self._client.get_or_create_collection(
                name=self.COLLECTION_NAME,
                metadata={"description": "Health and powerlifting documents"}
            )
            logger.debug(f"[HealthDocsRAG] Got/created collection: {self.COLLECTION_NAME}")
        return self._collection
    
    async def index_docs(self) -> None:
        """Index all PDF documents in docs_dir.
        
        Uses SHA256 hash to only re-process changed or new files.
        Chunks text at 500 tokens with 50-token overlap.
        """
        if not TIKA_AVAILABLE:
            logger.error("[HealthDocsRAG] Cannot index docs: Apache Tika not available")
            return
        
        if not self._docs_dir.exists():
            logger.warning(f"[HealthDocsRAG] Docs directory does not exist: {self._docs_dir}")
            return
        
        stored_hashes = self._load_hashes()
        
        pdf_files = list(self._docs_dir.glob("*.pdf"))
        if not pdf_files:
            logger.info(f"[HealthDocsRAG] No PDF files found in {self._docs_dir}")
            return
        
        logger.info(f"[HealthDocsRAG] Found {len(pdf_files)} PDF files to process")
        
        collection = self._get_or_create_collection()
        new_hashes = {}
        indexed_count = 0
        skipped_count = 0
        
        for pdf_path in pdf_files:
            file_hash = self._compute_file_hash(pdf_path)
            file_str = str(pdf_path)
            
            if file_str in stored_hashes and stored_hashes[file_str] == file_hash:
                new_hashes[file_str] = file_hash
                skipped_count += 1
                logger.debug(f"[HealthDocsRAG] Skipping unchanged file: {pdf_path.name}")
                continue
            
            logger.info(f"[HealthDocsRAG] Indexing: {pdf_path.name}")
            
            try:
                text = await self._extract_text(pdf_path)
                if not text or not text.strip():
                    logger.warning(f"[HealthDocsRAG] No text extracted from: {pdf_path.name}")
                    continue
                
                self._delete_file_chunks(collection, file_str)
                
                chunks = self._chunk_text(text)
                for i, chunk in enumerate(chunks):
                    chunk_id = self._make_chunk_id(file_str, i)
                    collection.add(
                        ids=[chunk_id],
                        documents=[chunk],
                        metadatas=[{
                            "source_file": pdf_path.name,
                            "source_path": file_str,
                            "chunk_index": i,
                            "file_hash": file_hash,
                        }]
                    )
                
                new_hashes[file_str] = file_hash
                indexed_count += 1
                logger.debug(f"[HealthDocsRAG] Indexed {len(chunks)} chunks from {pdf_path.name}")
                
            except Exception as e:
                logger.error(f"[HealthDocsRAG] Failed to index {pdf_path.name}: {e}")
        
        self._save_hashes(new_hashes)
        
        logger.info(
            f"[HealthDocsRAG] Indexing complete: "
            f"{indexed_count} files indexed, {skipped_count} unchanged"
        )
    
    async def query(self, q: str, n_results: int = 4) -> list[dict]:
        """Search health documents using semantic search.
        
        Args:
            q: Search query
            n_results: Number of results to return (default 4)
            
        Returns:
            [{"text": str, "source": str, "score": float}, ...]
        """
        collection = self._get_or_create_collection()
        
        results = collection.query(
            query_texts=[q],
            n_results=n_results,
            include=["documents", "metadatas", "distances"]
        )
        
        formatted = []
        if results and results.get("documents"):
            documents = results["documents"][0]
            metadatas = results.get("metadatas", [[]])[0]
            distances = results.get("distances", [[]])[0]
            
            for i, doc in enumerate(documents):
                meta = metadatas[i] if i < len(metadatas) else {}
                distance = distances[i] if i < len(distances) else 0.0
                
                score = max(0.0, 1.0 - (distance / 2.0))
                
                formatted.append({
                    "text": doc,
                    "source": meta.get("source_file", "unknown"),
                    "score": round(score, 3),
                })
        
        return formatted
    
    async def rebuild(self) -> None:
        """Force full re-index of all documents.
        
        Wipes the collection and re-indexes all files from scratch.
        """
        logger.info("[HealthDocsRAG] Starting full rebuild...")
        
        try:
            self._client.delete_collection(self.COLLECTION_NAME)
            logger.debug(f"[HealthDocsRAG] Deleted collection: {self.COLLECTION_NAME}")
        except Exception:
            pass
        
        self._collection = None
        
        if self._hash_file.exists():
            self._hash_file.unlink()
        
        await self.index_docs()
        
        logger.info("[HealthDocsRAG] Full rebuild complete")
    
    def _load_hashes(self) -> dict:
        """Load stored file hashes from sidecar file."""
        if not self._hash_file.exists():
            return {}
        
        try:
            with open(self._hash_file, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"[HealthDocsRAG] Failed to load hash file: {e}")
            return {}
    
    def _save_hashes(self, hashes: dict) -> None:
        """Save file hashes to sidecar file."""
        try:
            self._docs_dir.mkdir(parents=True, exist_ok=True)
            
            with open(self._hash_file, "w") as f:
                json.dump(hashes, f, indent=2)
        except Exception as e:
            logger.error(f"[HealthDocsRAG] Failed to save hash file: {e}")
    
    def _compute_file_hash(self, file_path: Path) -> str:
        """Compute SHA256 hash of a file."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    
    async def _extract_text(self, pdf_path: Path) -> str:
        """Extract text from a PDF using Apache Tika.
        
        Runs in executor to avoid blocking.
        """
        def _extract_sync():
            try:
                parsed = tika_parser.from_file(str(pdf_path))
                return parsed.get("content", "")
            except Exception as e:
                logger.error(f"[HealthDocsRAG] Tika extraction failed for {pdf_path}: {e}")
                return ""
        
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _extract_sync)
    
    def _chunk_text(self, text: str) -> list[str]:
        """Chunk text into segments of approximately CHUNK_SIZE_TOKENS.
        
        Uses simple word-based approximation (4 chars ~= 1 token).
        Maintains CHUNK_OVERLAP_TOKENS overlap between chunks.
        """
        words = text.split()
        chars_per_chunk = self.CHUNK_SIZE_TOKENS * 4
        overlap_chars = self.CHUNK_OVERLAP_TOKENS * 4
        
        chunks = []
        current_chunk = []
        current_length = 0
        
        for word in words:
            word_len = len(word) + 1
            
            if current_length + word_len > chars_per_chunk and current_chunk:
                chunk_text = " ".join(current_chunk)
                chunks.append(chunk_text)
                
                overlap_words = []
                overlap_len = 0
                for w in reversed(current_chunk):
                    if overlap_len + len(w) + 1 > overlap_chars:
                        break
                    overlap_words.insert(0, w)
                    overlap_len += len(w) + 1
                
                current_chunk = overlap_words
                current_length = overlap_len
            
            current_chunk.append(word)
            current_length += word_len
        
        if current_chunk:
            chunks.append(" ".join(current_chunk))
        
        return chunks if chunks else [text]
    
    def _make_chunk_id(self, file_path: str, chunk_index: int) -> str:
        """Create a unique ID for a chunk."""
        hash_input = f"{file_path}:{chunk_index}"
        return hashlib.sha256(hash_input.encode()).hexdigest()[:16]
    
    def _delete_file_chunks(self, collection: Any, file_path: str) -> None:
        """Delete all chunks for a given file."""
        try:
            results = collection.get(
                where={"source_path": file_path},
                include=[]
            )
            
            if results and results.get("ids"):
                collection.delete(ids=results["ids"])
                logger.debug(f"[HealthDocsRAG] Deleted {len(results['ids'])} chunks for {file_path}")
        except Exception as e:
            logger.warning(f"[HealthDocsRAG] Failed to delete chunks for {file_path}: {e}")
