import importlib.util
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

_MODULE_PATH = Path(__file__).resolve().parents[1] / "app/src/channels/history_export.py"
_SPEC = importlib.util.spec_from_file_location("history_export", _MODULE_PATH)
history_export = importlib.util.module_from_spec(_SPEC)
assert _SPEC and _SPEC.loader
_SPEC.loader.exec_module(history_export)

discord_messages_to_history_events = history_export.discord_messages_to_history_events
render_discord_history_markdown = history_export.render_discord_history_markdown

def _message(
    message_id,
    author_id,
    author_name,
    content,
    created_at,
    *,
    edited_at=None,
    attachments=None,
):
    return SimpleNamespace(
        id=message_id,
        author=SimpleNamespace(id=author_id, display_name=author_name),
        clean_content=content,
        created_at=created_at,
        edited_at=edited_at,
        attachments=attachments or [],
    )

def test_discord_history_export_roles_and_attachments():
    created = datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc)
    messages = [
        _message(2, 42, "IF", "answer", created, attachments=[]),
        _message(
            1,
            7,
            "Operator",
            "question",
            created.replace(minute=1),
            attachments=[
                SimpleNamespace(
                    filename="notes.md",
                    url="https://example.test/notes.md",
                )
            ],
        ),
    ]

    events = discord_messages_to_history_events(messages, bot_user_id=42)

    assert [event["id"] for event in events] == ["2", "1"]
    assert events[0]["role"] == "assistant"
    assert events[1]["role"] == "user"
    assert (
        "[Attachment: notes.md](https://example.test/notes.md)"
        in events[1]["content"]
    )

def test_render_discord_history_markdown_is_stable():
    events = [
        {
            "id": "2",
            "role": "assistant",
            "author": "IF",
            "content": "answer",
            "created_at": "2026-05-30T12:01:00+00:00",
            "edited_at": "",
        },
        {
            "id": "1",
            "role": "user",
            "author": "Operator",
            "content": "question",
            "created_at": "2026-05-30T12:00:00+00:00",
            "edited_at": "2026-05-30T12:00:30+00:00",
        },
    ]

    first = render_discord_history_markdown(
        events,
        channel_name="lifting",
        channel_id="123",
    )
    second = render_discord_history_markdown(
        list(reversed(events)),
        channel_name="lifting",
        channel_id="123",
    )

    assert first == second
    assert first.startswith("# Discord Chat History\n\nChannel: lifting\n")
    assert "Messages: 2" in first
    assert (
        "<!-- id=1 | created=2026-05-30T12:00:00+00:00 | "
        "edited=2026-05-30T12:00:30+00:00 -->"
        in first
    )
    assert "Updated:" not in first
