
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
                elif item.get("type"):
                    parts.append(f"[{item.get('type')}] {item}")
            elif item is not None:
                parts.append(str(item))
        return "\n".join(p for p in parts if p)
    if content is None:
        return ""
    return str(content)

def _message_key(index: int, msg: dict[str, Any]) -> str:
    for key in ("id", "message_id"):
        if msg.get(key):
            return str(msg[key])
    raw = f"{msg.get('role', 'user')}|{msg.get('created_at', '')}|{_content_to_text(msg.get('content'))}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"synthetic-{index}-{digest}"

def _normalize_event(index: int, msg: dict[str, Any]) -> dict[str, Any] | None:
    content = _content_to_text(msg.get("content")).strip()
    if not content:
        return None
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": _message_key(index, msg),
        "role": str(msg.get("role", "user")).strip() or "user",
        "author": str(msg.get("author", "") or ""),
        "content": content,
        "created_at": str(msg.get("created_at") or msg.get("timestamp") or now),
        "edited_at": str(msg.get("edited_at") or ""),
        "updated_at": now,
        "source": str(msg.get("source") or ""),
    }

def _load_events(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            return {str(item["id"]): item for item in raw if isinstance(item, dict) and item.get("id")}
    except Exception:
        return {}
    return {}

def _event_sort_key(event: dict[str, Any]) -> tuple[str, str]:
    return (str(event.get("created_at") or ""), str(event.get("id") or ""))

def render_history_markdown(events: Iterable[dict[str, Any]]) -> str:
    lines = [
        "# Conversation History",
        "",
        "This file is incremental. Message entries are updated in-place when Discord edits are observed.",
        f"Updated: {datetime.now(timezone.utc).isoformat()}",
        "",
    ]
    for index, event in enumerate(sorted(events, key=_event_sort_key), start=1):
        role = event.get("role", "user")
        author = event.get("author")
        label = f"{role} - {author}" if author else role
        meta = [f"id={event.get('id')}", f"created={event.get('created_at')}"]
        if event.get("edited_at"):
            meta.append(f"edited={event.get('edited_at')}")
        lines.extend([f"## {index}. {label}", "", f"<!-- {' | '.join(meta)} -->", "", str(event.get("content", "")), ""])
    return "\n".join(lines).rstrip() + "\n"

def write_history(
    session_dir: Path,
    messages: list[dict[str, Any]],
    history_events: list[dict[str, Any]] | None = None,
) -> Path:
    session_dir.mkdir(parents=True, exist_ok=True)
    json_path = session_dir / "history.json"
    existing = _load_events(json_path)

    source = history_events if history_events is not None else messages
    for index, msg in enumerate(source, start=1):
        event = _normalize_event(index, msg)
        if event is None:
            continue
        existing[event["id"]] = {**existing.get(event["id"], {}), **event}

    ordered = sorted(existing.values(), key=_event_sort_key)
    json_path.write_text(json.dumps(ordered, indent=2, ensure_ascii=False), encoding="utf-8")

    path = session_dir / "history.md"
    path.write_text(render_history_markdown(ordered), encoding="utf-8")
    return path
