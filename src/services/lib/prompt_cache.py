import hashlib
import json
import logging
import os
import threading
from dataclasses import dataclass
from typing import Any

import httpx
import psycopg

logger = logging.getLogger(__name__)

EMBEDDING_DIMENSIONS = 512
SIMILARITY_FLOOR = 0.85
CANDIDATE_LIMIT = 3

_schema_ready = threading.Event()


@dataclass
class Candidate:
    id: str
    request: dict[str, Any]
    response: dict[str, Any]
    similarity: float


def _host() -> str:
    return os.environ.get("PROMPT_CACHE_HOST", "pl-prompt-cache")


def _connect() -> psycopg.Connection:
    return psycopg.connect(
        host=_host(),
        port=5432,
        dbname="prompt_cache",
        user="prompt_cache",
        password=os.environ.get("PROMPT_CACHE_PASSWORD", ""),
        connect_timeout=3,
        autocommit=True,
    )


def _ensure_schema(connection: psycopg.Connection) -> None:
    if _schema_ready.is_set():
        return
    connection.execute("CREATE EXTENSION IF NOT EXISTS vector")
    connection.execute(f"""
        CREATE TABLE IF NOT EXISTS prompt_cache (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            athlete text NOT NULL,
            operation text NOT NULL,
            request_hash text NOT NULL,
            request jsonb NOT NULL,
            response jsonb NOT NULL,
            embedding vector({EMBEDDING_DIMENSIONS}) NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (athlete, operation, request_hash)
        )
    """)
    connection.execute("CREATE INDEX IF NOT EXISTS prompt_cache_embedding ON prompt_cache USING hnsw (embedding vector_cosine_ops)")
    _schema_ready.set()


def cache_request(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: payload.get(key) for key in ("messages", "tools", "response_format")}


def request_hash(request: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(request, sort_keys=True, default=str).encode()).hexdigest()


def _searchable_text(request: dict[str, Any]) -> str:
    return "\n\n".join(
        message["content"] if isinstance(message.get("content"), str) else json.dumps(message.get("content"), default=str)
        for message in request.get("messages") or []
        if message.get("role") != "system"
    )


def _embed(text: str) -> str:
    response = httpx.post(f"http://{_host()}:8080/embed", json={"inputs": text, "truncate": True}, timeout=30)
    response.raise_for_status()
    return "[" + ",".join(str(value) for value in response.json()[0]) + "]"


def exact(athlete: str, operation: str, request: dict[str, Any]) -> dict[str, Any] | None:
    try:
        with _connect() as connection:
            _ensure_schema(connection)
            row = connection.execute(
                "SELECT response FROM prompt_cache WHERE athlete = %s AND operation = %s AND request_hash = %s",
                (athlete, operation, request_hash(request)),
            ).fetchone()
    except (psycopg.Error, OSError) as exc:
        logger.warning("Prompt cache exact lookup failed: %s", exc)
        return None
    return row[0] if row else None


def similar(athlete: str, operation: str, request: dict[str, Any]) -> list[Candidate]:
    try:
        embedding = _embed(_searchable_text(request))
        with _connect() as connection:
            _ensure_schema(connection)
            rows = connection.execute(
                """
                SELECT id::text, request, response, 1 - (embedding <=> %s::vector) AS similarity
                FROM prompt_cache
                WHERE athlete = %s AND operation = %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (embedding, athlete, operation, embedding, CANDIDATE_LIMIT),
            ).fetchall()
    except (psycopg.Error, httpx.HTTPError, OSError) as exc:
        logger.warning("Prompt cache semantic search failed: %s", exc)
        return []
    return [Candidate(row[0], row[1], row[2], float(row[3])) for row in rows if float(row[3]) >= SIMILARITY_FLOOR]


def remember(athlete: str, operation: str, request: dict[str, Any], response: dict[str, Any]) -> None:
    try:
        embedding = _embed(_searchable_text(request))
        with _connect() as connection:
            _ensure_schema(connection)
            connection.execute(
                """
                INSERT INTO prompt_cache (athlete, operation, request_hash, request, response, embedding)
                VALUES (%s, %s, %s, %s, %s, %s::vector)
                ON CONFLICT (athlete, operation, request_hash) DO UPDATE SET response = EXCLUDED.response, created_at = now()
                """,
                (athlete, operation, request_hash(request), json.dumps(request, default=str), json.dumps(response, default=str), embedding),
            )
    except (psycopg.Error, httpx.HTTPError, OSError) as exc:
        logger.warning("Prompt cache store failed: %s", exc)
