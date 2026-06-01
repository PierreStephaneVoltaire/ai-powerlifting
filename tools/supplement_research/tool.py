
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from pydantic import Field

from tools.sdk_compat import (
    Action,
    Observation,
    Tool,
    ToolDefinition,
    ToolExecutor,
    register_tool,
)

logger = logging.getLogger(__name__)

SUPPLEMENT_S3_PREFIX = os.getenv("SUPPLEMENT_S3_PREFIX", "supplement-research/")
SUPPLEMENT_DATA_DIR = Path(
    os.getenv("SUPPLEMENT_DATA_DIR", "./data/supplement-research.lancedb")
)
SUPPLEMENT_PDF_DIR = Path(
    os.getenv("SUPPLEMENT_PDF_DIR", "./data/supplement-research-pdfs")
)
SUPPLEMENT_TABLE_NAME = "supplement_research"
CHUNK_SIZE_TOKENS = 500
CHUNK_OVERLAP_TOKENS = 50
HASH_FILE = ".index_hashes.json"
VALID_CONTEXTS = {
    "strength",
    "hypertrophy",
    "sleep",
    "recovery",
    "cognition",
    "longevity",
    "general",
}

_init_lock = threading.Lock()
_initialized = False

def _run_async(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, coro).result()
    return asyncio.run(coro)

def _format_result(result: Any) -> str:
    if isinstance(result, str):
        return result
    return json.dumps(result, indent=2, default=str)

def _embedding_dimension() -> int:
    try:
        from memory.embeddings import get_embedding_dimension
        return get_embedding_dimension()
    except Exception:
        return int(os.getenv("EMBEDDING_DIMENSION", "384"))

def _embed(texts: List[str]) -> List[List[float]]:
    from memory.embeddings import embed_batch
    return embed_batch(texts)

def _context_from_key(key: str) -> str:
    """Infer context tag from S3 key like 'supplement-research/sleep/ashwagandha.pdf'."""
    rest = key[len(SUPPLEMENT_S3_PREFIX):] if key.startswith(SUPPLEMENT_S3_PREFIX) else key
    parts = rest.split("/")
    if len(parts) >= 2 and parts[0]:
        tag = parts[0].lower()
        if tag in VALID_CONTEXTS:
            return tag
    return "general"

def _chunk_text(text: str) -> List[str]:
    """Chunk text into ~CHUNK_SIZE_TOKENS with CHUNK_OVERLAP_TOKENS overlap.

    Rough token approximation: 4 chars per token.
    """
    words = text.split()
    chars_per_chunk = CHUNK_SIZE_TOKENS * 4
    overlap_chars = CHUNK_OVERLAP_TOKENS * 4

    chunks: List[str] = []
    current: List[str] = []
    current_len = 0

    for word in words:
        wl = len(word) + 1
        if current_len + wl > chars_per_chunk and current:
            chunks.append(" ".join(current))
            overlap: List[str] = []
            ol = 0
            for w in reversed(current):
                if ol + len(w) + 1 > overlap_chars:
                    break
                overlap.insert(0, w)
                ol += len(w) + 1
            current = overlap
            current_len = ol
        current.append(word)
        current_len += wl
    if current:
        chunks.append(" ".join(current))
    return chunks if chunks else [text]

def _compute_file_hash(path: Path) -> str:
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(8192), b""):
            sha.update(block)
    return sha.hexdigest()

def _load_hashes() -> Dict[str, str]:
    hf = SUPPLEMENT_DATA_DIR / HASH_FILE
    if not hf.exists():
        return {}
    try:
        return json.loads(hf.read_text())
    except Exception as e:
        logger.warning(f"[supplement_research] Failed to load hash file: {e}")
        return {}

def _save_hashes(hashes: Dict[str, str]) -> None:
    SUPPLEMENT_DATA_DIR.mkdir(parents=True, exist_ok=True)
    (SUPPLEMENT_DATA_DIR / HASH_FILE).write_text(json.dumps(hashes, indent=2))

def _get_schema():
    from lancedb.pydantic import LanceModel, Vector
    dim = _embedding_dimension()

    class SupplementChunk(LanceModel):
        id: str
        source_pdf: str
        source_key: str
        context: str
        chunk_index: int
        text: str
        vector: Vector(dim)
        file_hash: str
        indexed_at: str

    return SupplementChunk

def _connect_table(create_if_missing: bool = True):
    import lancedb

    SUPPLEMENT_DATA_DIR.mkdir(parents=True, exist_ok=True)
    db = lancedb.connect(str(SUPPLEMENT_DATA_DIR))
    if SUPPLEMENT_TABLE_NAME in db.table_names():
        return db, db.open_table(SUPPLEMENT_TABLE_NAME)
    if not create_if_missing:
        return db, None
    schema = _get_schema()
    table = db.create_table(SUPPLEMENT_TABLE_NAME, schema=schema)
    logger.info(f"[supplement_research] Created LanceDB table at {SUPPLEMENT_DATA_DIR}")
    return db, table

def _sync_pdfs_from_s3() -> List[Path]:
    """Pull all supplement-research PDFs from S3 to local PDF dir.

    Returns the list of local PDF paths present after the sync.
    """
    bucket = os.getenv("POWERLIFTING_S3_BUCKET")
    if not bucket:
        logger.warning(
            "[supplement_research] POWERLIFTING_S3_BUCKET not set; skipping S3 sync"
        )
        return sorted(SUPPLEMENT_PDF_DIR.rglob("*.pdf")) if SUPPLEMENT_PDF_DIR.exists() else []

    import boto3

    SUPPLEMENT_PDF_DIR.mkdir(parents=True, exist_ok=True)
    s3 = boto3.client("s3")
    paginator = s3.get_paginator("list_objects_v2")
    downloaded = 0
    skipped = 0

    for page in paginator.paginate(Bucket=bucket, Prefix=SUPPLEMENT_S3_PREFIX):
        for obj in page.get("Contents", []) or []:
            key = obj["Key"]
            if not key.lower().endswith(".pdf"):
                continue
            rel = key[len(SUPPLEMENT_S3_PREFIX):] if key.startswith(SUPPLEMENT_S3_PREFIX) else key
            dest = SUPPLEMENT_PDF_DIR / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists() and dest.stat().st_size == obj.get("Size", 0):
                skipped += 1
                continue
            logger.info(f"[supplement_research] Downloading s3://{bucket}/{key}")
            s3.download_file(bucket, key, str(dest))
            downloaded += 1

    logger.info(
        f"[supplement_research] S3 sync complete: {downloaded} downloaded, {skipped} unchanged"
    )
    return sorted(SUPPLEMENT_PDF_DIR.rglob("*.pdf"))

def _extract_pdf_text(pdf_path: Path) -> str:
    try:
        from tika import parser as tika_parser
    except ImportError:
        logger.error("[supplement_research] Apache Tika not installed")
        return ""
    try:
        parsed = tika_parser.from_file(str(pdf_path))
        return parsed.get("content", "") or ""
    except Exception as e:
        logger.error(f"[supplement_research] Tika extraction failed for {pdf_path.name}: {e}")
        return ""

def _s3_key_for_pdf(pdf_path: Path) -> str:
    try:
        rel = pdf_path.relative_to(SUPPLEMENT_PDF_DIR).as_posix()
    except ValueError:
        rel = pdf_path.name
    return f"{SUPPLEMENT_S3_PREFIX}{rel}"

def _index_pdfs(pdf_paths: List[Path], force: bool = False) -> Dict[str, int]:
    """Chunk, embed, and upsert the given PDFs into the LanceDB table.

    Respects existing SHA256 hashes unless force=True.
    """
    _, table = _connect_table(create_if_missing=True)
    stored_hashes = {} if force else _load_hashes()
    new_hashes: Dict[str, str] = {}
    indexed = 0
    skipped = 0
    now = datetime.now(timezone.utc).isoformat()

    for pdf in pdf_paths:
        fh = _compute_file_hash(pdf)
        pdf_str = str(pdf)

        if not force and stored_hashes.get(pdf_str) == fh:
            new_hashes[pdf_str] = fh
            skipped += 1
            continue

        s3_key = _s3_key_for_pdf(pdf)
        context_tag = _context_from_key(s3_key)

        text = _extract_pdf_text(pdf)
        if not text.strip():
            logger.warning(f"[supplement_research] No text extracted from {pdf.name}")
            continue

        try:
            table.delete(f"source_key = '{s3_key}'")
        except Exception:
            pass

        chunks = _chunk_text(text)
        vectors = _embed(chunks)
        rows = []
        for i, (chunk, vec) in enumerate(zip(chunks, vectors)):
            rows.append({
                "id": hashlib.sha256(f"{s3_key}:{i}".encode()).hexdigest()[:16],
                "source_pdf": pdf.name,
                "source_key": s3_key,
                "context": context_tag,
                "chunk_index": i,
                "text": chunk,
                "vector": vec,
                "file_hash": fh,
                "indexed_at": now,
            })
        if rows:
            table.add(rows)
            indexed += 1
            new_hashes[pdf_str] = fh
            logger.info(f"[supplement_research] Indexed {len(rows)} chunks from {pdf.name} (context={context_tag})")

    _save_hashes(new_hashes)

    try:
        table.create_fts_index("text", replace=True)
    except Exception as e:
        logger.warning(f"[supplement_research] FTS index build failed: {e}")

    return {"indexed": indexed, "skipped": skipped, "total_pdfs": len(pdf_paths)}

def _initialize(rebuild: bool = False) -> Dict[str, Any]:
    """Lazy initializer: pull from S3 (once) and index.

    If rebuild=True, wipes the table + hash file and forces a full re-index.
    """
    global _initialized
    with _init_lock:
        if rebuild:
            import lancedb
            SUPPLEMENT_DATA_DIR.mkdir(parents=True, exist_ok=True)
            db = lancedb.connect(str(SUPPLEMENT_DATA_DIR))
            if SUPPLEMENT_TABLE_NAME in db.table_names():
                db.drop_table(SUPPLEMENT_TABLE_NAME)
                logger.info("[supplement_research] Dropped table for rebuild")
            hf = SUPPLEMENT_DATA_DIR / HASH_FILE
            if hf.exists():
                hf.unlink()
            _initialized = False

        if _initialized and not rebuild:
            return {"status": "already_initialized"}

        pdfs = _sync_pdfs_from_s3()
        if not pdfs:
            _initialized = True
            return {
                "status": "empty",
                "message": (
                    "No PDFs found. Upload files to "
                    f"s3://$POWERLIFTING_S3_BUCKET/{SUPPLEMENT_S3_PREFIX} and retry."
                ),
            }
        result = _index_pdfs(pdfs, force=rebuild)
        _initialized = True
        return {"status": "indexed", **result}

def _hybrid_search(
    query: str,
    top_k: int = 8,
    filter_context: Optional[str] = None,
) -> List[Dict[str, Any]]:
    from lancedb.rerankers import RRFReranker

    _, table = _connect_table(create_if_missing=False)
    if table is None:
        return []

    query_vector = _embed([query])[0]
    search = (
        table.search(query_type="hybrid")
        .vector(query_vector)
        .text(query)
        .rerank(reranker=RRFReranker())
        .limit(max(1, int(top_k)))
    )
    if filter_context:
        tag = filter_context.lower()
        if tag not in VALID_CONTEXTS:
            raise ValueError(
                f"filter_context must be one of {sorted(VALID_CONTEXTS)}; got {filter_context}"
            )
        search = search.where(f"context = '{tag}'")

    results = search.to_list()
    out: List[Dict[str, Any]] = []
    for r in results:
        out.append({
            "text": r.get("text", ""),
            "source_pdf": r.get("source_pdf", ""),
            "source_key": r.get("source_key", ""),
            "context": r.get("context", ""),
            "chunk_index": r.get("chunk_index", 0),
            "score": float(r.get("_relevance_score", 0.0)) if r.get("_relevance_score") is not None else None,
            "vector_distance": float(r["_distance"]) if r.get("_distance") is not None else None,
            "indexed_at": r.get("indexed_at", ""),
        })
    return out

class SupplementSearchAction(Action):
    query: str = Field(description="Natural-language research question.")
    top_k: int = Field(
        default=8,
        description="Number of results to return after hybrid reranking.",
    )
    filter_context: Optional[str] = Field(
        default=None,
        description=(
            "Optional topic filter. One of: strength, hypertrophy, sleep, "
            "recovery, cognition, longevity, general."
        ),
    )
    rebuild: bool = Field(
        default=False,
        description=(
            "If true, wipe the index + hash sidecar, re-pull all PDFs from S3, "
            "and re-chunk+re-embed everything before searching. Long-running."
        ),
    )

class SupplementSearchObservation(Observation):
    pass

class SupplementSearchExecutor(
    ToolExecutor[SupplementSearchAction, SupplementSearchObservation]
):
    def __call__(
        self, action: SupplementSearchAction, conversation=None
    ) -> SupplementSearchObservation:
        try:
            init_info: Dict[str, Any] = {}
            if action.rebuild or not _initialized:
                init_info = _initialize(rebuild=action.rebuild)
                if init_info.get("status") == "empty":
                    return SupplementSearchObservation.from_text(
                        _format_result({
                            "status": "empty_corpus",
                            "message": init_info.get("message", ""),
                            "results": [],
                        })
                    )

            results = _hybrid_search(
                query=action.query,
                top_k=action.top_k,
                filter_context=action.filter_context,
            )
            payload: Dict[str, Any] = {
                "query": action.query,
                "filter_context": action.filter_context,
                "top_k": action.top_k,
                "count": len(results),
                "results": results,
            }
            if init_info:
                payload["index_info"] = init_info
            return SupplementSearchObservation.from_text(_format_result(payload))
        except Exception as e:
            logger.warning(f"[supplement_research] search failed: {e}")
            return SupplementSearchObservation.from_text(
                f"ERROR: {type(e).__name__}: {e}", is_error=True
            )

class SupplementSearchTool(
    ToolDefinition[SupplementSearchAction, SupplementSearchObservation]
):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["SupplementSearchTool"]:
        return [cls(
            description=(
                "Hybrid retrieval (BM25 + vector, RRF reranker) over the local "
                "supplement research PDF corpus (Examine.com). Pulls PDFs from "
                "s3://$POWERLIFTING_S3_BUCKET/supplement-research/ on first use. "
                "Pass filter_context to narrow to a topic (strength, sleep, "
                "recovery, etc). Pass rebuild=true after uploading new PDFs to "
                "force a full re-index."
            ),
            action_type=SupplementSearchAction,
            observation_type=SupplementSearchObservation,
            executor=SupplementSearchExecutor(),
        )]

register_tool("SupplementSearchTool", SupplementSearchTool)

SUPPLEMENT_SEARCH_SCHEMA = {
    "name": "supplement_search",
    "description": (
        "Hybrid retrieval (BM25 + vector) over the local supplement research "
        "PDF corpus (Examine.com). Use for any question about supplements, "
        "ergogenic aids, sleep aids, recovery protocols, or nutrition where "
        "the corpus is likely to have coverage. Pulls PDFs from S3 on first "
        "use. Pass rebuild=true after uploading new PDFs."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Natural-language research question.",
            },
            "top_k": {
                "type": "integer",
                "description": "Number of reranked results to return.",
                "default": 8,
            },
            "filter_context": {
                "type": "string",
                "description": (
                    "Optional topic filter: strength, hypertrophy, sleep, "
                    "recovery, cognition, longevity, general."
                ),
                "enum": sorted(VALID_CONTEXTS),
            },
            "rebuild": {
                "type": "boolean",
                "description": (
                    "If true, wipe the index and re-pull+re-embed from S3 "
                    "before searching. Long-running."
                ),
                "default": False,
            },
        },
        "required": ["query"],
    },
}

def get_tools() -> List[Tool]:
    return [Tool(name="SupplementSearchTool")]

def get_schemas() -> Dict[str, dict]:
    return {"supplement_search": SUPPLEMENT_SEARCH_SCHEMA}

async def execute(name: str, args: Dict[str, Any]) -> str:
    if name != "supplement_search":
        return f"Unknown tool: {name}"
    action = SupplementSearchAction(
        query=args.get("query", ""),
        top_k=int(args.get("top_k", 8)),
        filter_context=args.get("filter_context"),
        rebuild=bool(args.get("rebuild", False)),
    )
    obs = SupplementSearchExecutor()(action)
    return "".join(c.text for c in obs.content if hasattr(c, "text"))
