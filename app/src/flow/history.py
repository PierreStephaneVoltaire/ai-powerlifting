"""Markdown history writer for the planning stage."""
from __future__ import annotations

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


def render_history_markdown(messages: Iterable[dict[str, Any]]) -> str:
    lines = [
        "# Conversation History",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
    ]
    for index, msg in enumerate(messages, start=1):
        role = str(msg.get("role", "user")).strip() or "user"
        content = _content_to_text(msg.get("content")).strip()
        if not content:
            continue
        lines.extend([f"## {index}. {role}", "", content, ""])
    return "\n".join(lines).rstrip() + "\n"


def write_history(session_dir: Path, messages: list[dict[str, Any]]) -> Path:
    session_dir.mkdir(parents=True, exist_ok=True)
    path = session_dir / "history.md"
    path.write_text(render_history_markdown(messages), encoding="utf-8")
    return path

