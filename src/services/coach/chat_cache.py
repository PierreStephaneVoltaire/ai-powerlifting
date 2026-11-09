import hashlib
import json
import logging
import os
import re
from difflib import SequenceMatcher
from typing import Any

from services.lib import valkey

logger = logging.getLogger("coach")
TTL_SECONDS = 30 * 24 * 3600
SIMILARITY = 0.75
STOPWORDS = frozenset("a an the is are was were be to of in on for and or it this that my me i you why what how does do did can could should would with about at by from".split())
ENTRY = re.compile(r"<entry><content>(.*?)</content><metadata>(.*?)</metadata></entry>", re.S)


def fingerprint(template: dict[str, Any]) -> str:
    meta = template.get("meta") or {}
    material = {
        "phases": template.get("phases"),
        "sessions": template.get("sessions"),
        "program_context": meta.get("program_context"),
        "evaluation": meta.get("ai_evaluation"),
    }
    return hashlib.sha256(json.dumps(material, sort_keys=True, default=str).encode()).hexdigest()


def normalize(message: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", message.lower())).strip()


def similar(first: str, second: str) -> bool:
    a, b = normalize(first), normalize(second)
    words_a, words_b = set(a.split()) - STOPWORDS, set(b.split()) - STOPWORDS
    overlap = len(words_a & words_b) / len(words_a | words_b) if words_a | words_b else 0.0
    return max(SequenceMatcher(None, a, b).ratio(), overlap) >= SIMILARITY


def _exact_key(version: str, message: str) -> str:
    return f"pl:chat-cache:template:{version}:{hashlib.sha256(normalize(message).encode()).hexdigest()}"


def collection(version: str) -> str:
    return f"chat_template_{version[:24]}"


def _mcp_url() -> str:
    return os.environ.get("PROMPT_CACHE_MCP_URL", "http://pl-prompt-cache-mcp:8000/mcp")


async def _mcp(tool: str, arguments: dict[str, Any]) -> list[str]:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async with streamable_http_client(_mcp_url()) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool, arguments)
    return [getattr(part, "text", "") for part in result.content or []]


def candidates(texts: list[str]) -> list[tuple[str, dict[str, Any]]]:
    found = []
    for text in texts:
        for content, metadata in ENTRY.findall(text):
            try:
                found.append((content.strip(), json.loads(metadata)))
            except ValueError:
                continue
    return found


async def lookup(version: str, intent: str, message: str) -> tuple[str, str] | None:
    hit = valkey.get_json(_exact_key(version, message))
    if hit and hit.get("intent") == intent:
        return "exact", hit["reply"]
    try:
        texts = await _mcp("qdrant-find", {"query": message, "collection_name": collection(version)})
    except Exception as exc:
        logger.warning("Chat cache semantic lookup failed: %s", exc)
        return None
    for question, metadata in candidates(texts):
        if metadata.get("intent") != intent or not similar(question, message):
            continue
        saved = valkey.get_json(metadata.get("reply_key", ""))
        if saved:
            return "semantic", saved["reply"]
    return None


async def remember(version: str, intent: str, message: str, reply: str) -> None:
    key = _exact_key(version, message)
    valkey.set_json(key, {"intent": intent, "question": message, "reply": reply}, ttl=TTL_SECONDS)
    try:
        await _mcp("qdrant-store", {"information": message, "collection_name": collection(version), "metadata": {"intent": intent, "reply_key": key}})
    except Exception as exc:
        logger.warning("Chat cache semantic store failed: %s", exc)
