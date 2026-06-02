"""Tests for channels.outbound_queue - Phase 5."""
import sys
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

APP_SRC = str(Path(__file__).resolve().parent.parent / "app" / "src")
if APP_SRC not in sys.path:
    sys.path.insert(0, APP_SRC)

from channels.execution_models import DiscordOutboundMessage
from channels import outbound_queue

def _make_outbound(**overrides) -> DiscordOutboundMessage:
    defaults = dict(
        outbound_id="out-1",
        channel_id="chan-1",
        conversation_id="conv-1",
        type="social_response",
        priority=5,
        content="Hello!",
        attachments=[],
        status="queued",
        created_at="2025-01-01T00:00:00+00:00",
        updated_at="2025-01-01T00:00:00+00:00",
        idempotency_key="nb:ni:social_response:out-1",
    )
    defaults.update(overrides)
    return DiscordOutboundMessage(**defaults)

def _mock_store():
    store = MagicMock()
    store.acquire_outbound_lock = AsyncMock(return_value=True)
    store.release_outbound_lock = AsyncMock(return_value=True)
    store.query_outbox = AsyncMock(return_value=[])
    store.update_outbound_message_status = AsyncMock(return_value=True)
    return store

@pytest.mark.asyncio
async def test_drain_channel_reentrancy_guard():
    outbound_queue._draining_channels.add("chan-1")
    try:
        with patch.object(outbound_queue, "_drain_channel_inner", new_callable=AsyncMock) as mock_inner:
            await outbound_queue._drain_channel("chan-1")
            mock_inner.assert_not_called()
    finally:
        outbound_queue._draining_channels.discard("chan-1")

@pytest.mark.asyncio
async def test_drain_channel_releases_draining_on_exit():
    store = _mock_store()
    store.acquire_outbound_lock = AsyncMock(return_value=False)
    with patch("channels.outbound_queue.get_execution_store", return_value=store):
        await outbound_queue._drain_channel("chan-1")
    assert "chan-1" not in outbound_queue._draining_channels

@pytest.mark.asyncio
async def test_drain_channel_exits_if_lock_not_acquired():
    store = _mock_store()
    store.acquire_outbound_lock = AsyncMock(return_value=False)
    with patch("channels.outbound_queue.get_execution_store", return_value=store):
        await outbound_queue._drain_channel_inner("chan-1")
    store.release_outbound_lock.assert_not_called()

@pytest.mark.asyncio
async def test_send_one_marks_sending_on_success():
    store = _mock_store()
    msg = _make_outbound()
    with patch.object(outbound_queue, "_resolve_discord_handle", return_value=(MagicMock(), MagicMock())), \
         patch.object(outbound_queue, "_deliver_outbound", new_callable=AsyncMock), \
         patch.object(outbound_queue, "_get_sent_message_id", return_value="discord-msg-123"):
        result = await outbound_queue._send_one("chan-1", msg, store)
    assert result is True
    calls = store.update_outbound_message_status.call_args_list
    assert len(calls) == 2
    assert calls[0].kwargs["from_status"] == "queued"
    assert calls[0].kwargs["to_status"] == "sending"
    assert calls[1].kwargs["from_status"] == "sending"
    assert calls[1].kwargs["to_status"] == "sent"
    assert calls[1].kwargs["discord_message_id"] == "discord-msg-123"

@pytest.mark.asyncio
async def test_send_one_marks_failed_on_handle_failure():
    store = _mock_store()
    msg = _make_outbound()
    with patch.object(outbound_queue, "_resolve_discord_handle", return_value=(None, None)):
        result = await outbound_queue._send_one("chan-1", msg, store)
    assert result is False
    calls = store.update_outbound_message_status.call_args_list
    assert calls[1].kwargs["to_status"] == "failed"

@pytest.mark.asyncio
async def test_send_one_marks_failed_on_delivery_error():
    store = _mock_store()
    msg = _make_outbound()
    with patch.object(outbound_queue, "_resolve_discord_handle", return_value=(MagicMock(), MagicMock())), \
         patch.object(outbound_queue, "_deliver_outbound", new_callable=AsyncMock, side_effect=RuntimeError("Discord error")):
        result = await outbound_queue._send_one("chan-1", msg, store)
    assert result is False
    calls = store.update_outbound_message_status.call_args_list
    assert calls[1].kwargs["to_status"] == "failed"

@pytest.mark.asyncio
async def test_send_one_skips_if_not_queued():
    store = _mock_store()
    store.update_outbound_message_status = AsyncMock(return_value=False)
    msg = _make_outbound()
    result = await outbound_queue._send_one("chan-1", msg, store)
    assert result is False

@pytest.mark.asyncio
async def test_resolve_discord_handle_no_clients():
    with patch.dict("sys.modules", {"channels.listeners.discord_listener": None}):
        result = outbound_queue._resolve_discord_handle("12345")
    assert result == (None, None)

@pytest.mark.asyncio
async def test_resolve_discord_handle_finds_channel():
    mock_channel = MagicMock()
    mock_client = MagicMock()
    mock_client.get_channel = MagicMock(return_value=mock_channel)
    mock_client.loop = MagicMock()
    mock_module = MagicMock()
    mock_module._active_clients = {"wh-1": mock_client}
    with patch.dict("sys.modules", {"channels.listeners.discord_listener": mock_module}):
        result = outbound_queue._resolve_discord_handle("12345")
    assert result == (mock_channel, mock_client.loop)

@pytest.mark.asyncio
async def test_resolve_discord_handle_no_matching_channel():
    mock_client = MagicMock()
    mock_client.get_channel = MagicMock(return_value=None)
    mock_module = MagicMock()
    mock_module._active_clients = {"wh-1": mock_client}
    with patch.dict("sys.modules", {"channels.listeners.discord_listener": mock_module}):
        result = outbound_queue._resolve_discord_handle("99999")
    assert result == (None, None)

@pytest.mark.asyncio
async def test_drain_loop_stops_when_empty():
    store = _mock_store()
    store.query_outbox = AsyncMock(return_value=[])
    with patch("channels.outbound_queue.get_execution_store", return_value=store):
        await outbound_queue._drain_loop("chan-1", store, "owner-1", "2099-12-31T23:59:59+00:00")
    store.query_outbox.assert_called_once()

@pytest.mark.asyncio
async def test_drain_loop_respects_lock_expiry():
    store = _mock_store()
    msg = _make_outbound()
    store.query_outbox = AsyncMock(return_value=[msg])
    with patch("channels.outbound_queue.get_execution_store", return_value=store):
        await outbound_queue._drain_loop("chan-1", store, "owner-1", "2020-01-01T00:00:00+00:00")
    store.update_outbound_message_status.assert_not_called()

@pytest.mark.asyncio
async def test_drain_reschedules_when_items_remain():
    store = _mock_store()
    call_count = {"n": 0}
    item1 = _make_outbound(outbound_id="out-1")
    item2 = _make_outbound(outbound_id="out-2")

    async def query_side(*a, **kw):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return [item1]
        if call_count["n"] == 2:
            return []
        return [item2]

    store.query_outbox = AsyncMock(side_effect=query_side)
    with patch("channels.outbound_queue.get_execution_store", return_value=store), \
         patch("channels.outbound_queue.schedule_drain") as mock_schedule, \
         patch.object(outbound_queue, "_resolve_discord_handle", return_value=(None, None)):
        await outbound_queue._drain_channel_inner("chan-1")
    mock_schedule.assert_called_once_with("chan-1")

@pytest.mark.asyncio
async def test_drain_no_reschedule_when_empty():
    store = _mock_store()
    store.query_outbox = AsyncMock(return_value=[])
    with patch("channels.outbound_queue.get_execution_store", return_value=store), \
         patch("channels.outbound_queue.schedule_drain") as mock_schedule, \
         patch.object(outbound_queue, "_resolve_discord_handle", return_value=(None, None)):
        await outbound_queue._drain_channel_inner("chan-1")
    mock_schedule.assert_not_called()
