"""Session directory resolution for opencode runs and history files."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

from config import SANDBOX_PATH

if False:  # pragma: no cover
    from storage.models import WebhookRecord


_SAFE_SEGMENT_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def safe_segment(value: Any, fallback: str = "default") -> str:
    text = str(value or "").strip()
    if not text:
        text = fallback
    text = _SAFE_SEGMENT_RE.sub("_", text)
    return text.strip("._") or fallback


def request_platform(request_data: dict[str, Any], webhook: Optional["WebhookRecord"] = None) -> str:
    if webhook:
        return str(webhook.platform or "http").lower()
    return str(request_data.get("platform") or "http").lower()


def request_channel_id(
    request_data: dict[str, Any],
    webhook: Optional["WebhookRecord"],
    cache_key: str,
) -> str:
    if webhook:
        config = webhook.get_config()
        return str(config.get("channel_id") or webhook.conversation_id or cache_key)
    return str(
        request_data.get("channel_id")
        or request_data.get("conversation_id")
        or request_data.get("_conversation_id")
        or request_data.get("chat_id")
        or cache_key
    )


def request_guild_id(
    request_data: dict[str, Any],
    webhook: Optional["WebhookRecord"],
) -> str:
    metadata = request_data.get("metadata") if isinstance(request_data.get("metadata"), dict) else {}
    if webhook:
        config = webhook.get_config()
        return str(config.get("guild_id") or metadata.get("guild_id") or webhook.platform or "discord")
    return str(
        request_data.get("guild_id")
        or metadata.get("guild_id")
        or request_platform(request_data, webhook)
        or "http"
    )


def resolve_session_dir(
    request_data: dict[str, Any],
    webhook: Optional["WebhookRecord"],
    cache_key: str,
) -> Path:
    """Return `{mount}/{guild_id}/{channel_id}` for a request."""
    guild_id = safe_segment(request_guild_id(request_data, webhook), "guild")
    channel_id = safe_segment(request_channel_id(request_data, webhook, cache_key), "channel")
    path = Path(SANDBOX_PATH) / guild_id / channel_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def resolve_direct_tool_dir(conversation_id: str) -> Path:
    """Direct tool invocations keep the historic `/files/sandbox/{chat_id}` path."""
    path = Path(SANDBOX_PATH) / safe_segment(conversation_id)
    path.mkdir(parents=True, exist_ok=True)
    return path

