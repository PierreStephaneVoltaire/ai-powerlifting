"""Deterministic Discord channel history markdown exports."""
from __future__ import annotations

from typing import Any, Iterable


def _event_sort_key(event: dict[str, Any]) -> tuple[str, str]:
    return (str(event.get("created_at") or ""), str(event.get("id") or ""))


def _isoformat(value: Any) -> str:
    if not value:
        return ""
    if hasattr(value, "isoformat"):
        return str(value.isoformat())
    return str(value)


def _author_name(message: Any) -> str:
    author = getattr(message, "author", None)
    if author is None:
        return "unknown"
    return (
        str(getattr(author, "display_name", "") or "")
        or str(getattr(author, "name", "") or "")
        or str(author)
        or "unknown"
    )


def _attachment_lines(message: Any) -> list[str]:
    lines: list[str] = []
    for attachment in getattr(message, "attachments", []) or []:
        filename = str(getattr(attachment, "filename", "") or "attachment")
        url = str(getattr(attachment, "url", "") or "")
        if url:
            lines.append(f"[Attachment: {filename}]({url})")
        else:
            lines.append(f"[Attachment: {filename}]")
    return lines


def discord_message_to_history_event(
    message: Any,
    *,
    bot_user_id: int | None = None,
) -> dict[str, Any] | None:
    """Convert a discord.py message-like object to a stable export event."""
    content = str(
        getattr(message, "clean_content", "")
        or getattr(message, "content", "")
        or ""
    ).strip()
    attachments = _attachment_lines(message)
    if attachments:
        content = "\n".join(part for part in [content, *attachments] if part)
    if not content:
        return None

    author = getattr(message, "author", None)
    author_id = getattr(author, "id", None)
    role = (
        "assistant"
        if bot_user_id is not None and author_id == bot_user_id
        else "user"
    )

    return {
        "id": str(getattr(message, "id", "") or ""),
        "role": role,
        "author": _author_name(message),
        "content": content,
        "created_at": _isoformat(getattr(message, "created_at", "")),
        "edited_at": _isoformat(getattr(message, "edited_at", "")),
    }


def discord_messages_to_history_events(
    messages: Iterable[Any],
    *,
    bot_user_id: int | None = None,
) -> list[dict[str, Any]]:
    """Convert a Discord history iterable to stable export events."""
    events: list[dict[str, Any]] = []
    for message in messages:
        event = discord_message_to_history_event(message, bot_user_id=bot_user_id)
        if event is not None:
            events.append(event)
    return sorted(events, key=_event_sort_key)


def render_discord_history_markdown(
    events: Iterable[dict[str, Any]],
    *,
    channel_name: str = "",
    channel_id: str = "",
) -> str:
    """Render Discord history events as markdown without generated timestamps."""
    ordered = sorted(events, key=_event_sort_key)
    channel_label = channel_name or channel_id or "unknown"
    lines = [
        "# Discord Chat History",
        "",
        f"Channel: {channel_label}",
        f"Channel ID: {channel_id or 'unknown'}",
        f"Messages: {len(ordered)}",
        "",
    ]

    for index, event in enumerate(ordered, start=1):
        role = str(event.get("role", "user") or "user")
        author = str(event.get("author", "") or "")
        label = f"{role} - {author}" if author else role
        meta = [
            f"id={event.get('id', '')}",
            f"created={event.get('created_at', '')}",
        ]
        if event.get("edited_at"):
            meta.append(f"edited={event.get('edited_at')}")

        lines.extend(
            [
                f"## {index}. {label}",
                "",
                f"<!-- {' | '.join(meta)} -->",
                "",
                str(event.get("content", "")),
                "",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"
