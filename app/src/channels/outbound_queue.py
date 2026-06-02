
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Optional, Set

from channels.execution_models import DiscordOutboundMessage, get_instance_identity
from channels.execution_store import get_execution_store
from config import (
    OUTBOUND_LOCK_DURATION_SECONDS,
    OUTBOUND_DRAIN_BATCH_SIZE,
)

logger = logging.getLogger(__name__)

_draining_channels: Set[str] = set()

def schedule_drain(channel_id: str, loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
    if loop is None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning("Cannot schedule outbound drain for %s: no event loop", channel_id)
            return
    asyncio.ensure_future(_drain_channel(channel_id), loop=loop)

async def _drain_channel(channel_id: str) -> None:
    if channel_id in _draining_channels:
        return
    _draining_channels.add(channel_id)
    try:
        await _drain_channel_inner(channel_id)
    finally:
        _draining_channels.discard(channel_id)

async def _drain_channel_inner(channel_id: str) -> None:
    store = get_execution_store()
    owner = get_instance_identity()
    expires_at = (
        datetime.now(timezone.utc) + timedelta(seconds=OUTBOUND_LOCK_DURATION_SECONDS)
    ).isoformat()

    acquired = await store.acquire_outbound_lock(channel_id, owner, expires_at)
    if not acquired:
        logger.info("Outbound lock not acquired for channel %s, another drainer is active", channel_id)
        return

    try:
        await _drain_loop(channel_id, store, owner, expires_at)
    finally:
        try:
            await store.release_outbound_lock(channel_id, owner)
        except Exception as e:
            logger.warning("Failed to release outbound lock for channel %s: %s", channel_id, e)

        queued = await store.query_outbox(channel_id, limit=1)
        if queued:
            schedule_drain(channel_id)

_DRAIN_SLEEP_SECONDS = 0.1
_DRAIN_MAX_ITERATIONS = 1000

async def _drain_loop(
    channel_id: str,
    store: Any,
    owner: str,
    lock_expires_at: str,
) -> None:
    sent_count = 0
    failed_count = 0
    iteration = 0

    while iteration < _DRAIN_MAX_ITERATIONS:
        iteration += 1
        try:
            lock_expiry_dt = datetime.fromisoformat(lock_expires_at)
        except (ValueError, TypeError):
            lock_expiry_dt = datetime.now(timezone.utc) + timedelta(seconds=OUTBOUND_LOCK_DURATION_SECONDS)

        if datetime.now(timezone.utc) >= lock_expiry_dt:
            logger.info("Outbound lock window ending for channel %s after %d sent, %d failed", channel_id, sent_count, failed_count)
            break

        items = await store.query_outbox(channel_id, limit=OUTBOUND_DRAIN_BATCH_SIZE)
        queued = [m for m in items if m.status == "queued"]
        if not queued:
            break

        progress = False
        for msg in queued:
            if datetime.now(timezone.utc) >= lock_expiry_dt:
                break
            success = await _send_one(channel_id, msg, store)
            if success:
                sent_count += 1
                progress = True
            else:
                failed_count += 1

        if not progress:
            await asyncio.sleep(_DRAIN_SLEEP_SECONDS)

    if sent_count or failed_count:
        logger.info(
            "Outbound drain for channel %s: %d sent, %d failed",
            channel_id,
            sent_count,
            failed_count,
        )

async def _send_one(
    channel_id: str,
    msg: DiscordOutboundMessage,
    store: Any,
) -> bool:
    marked = await store.update_outbound_message_status(
        channel_id=channel_id,
        outbound_id=msg.outbound_id,
        from_status="queued",
        to_status="sending",
    )
    if not marked:
        logger.info("Outbound %s no longer queued, skipping", msg.outbound_id)
        return False

    channel_ref, discord_loop = _resolve_discord_handle(channel_id)
    if channel_ref is None or discord_loop is None:
        logger.error("Cannot resolve Discord channel handle for outbound %s to channel %s", msg.outbound_id, channel_id)
        await store.update_outbound_message_status(
            channel_id=channel_id,
            outbound_id=msg.outbound_id,
            from_status="sending",
            to_status="failed",
        )
        return False

    try:
        await _deliver_outbound(msg, channel_ref, discord_loop)
        discord_msg_id = _get_sent_message_id(channel_ref, msg)
        await store.update_outbound_message_status(
            channel_id=channel_id,
            outbound_id=msg.outbound_id,
            from_status="sending",
            to_status="sent",
            discord_message_id=discord_msg_id or "",
        )
        return True
    except Exception as e:
        logger.error("Failed to send outbound %s to channel %s: %s", msg.outbound_id, channel_id, e)
        await store.update_outbound_message_status(
            channel_id=channel_id,
            outbound_id=msg.outbound_id,
            from_status="sending",
            to_status="failed",
        )
        return False

def _resolve_discord_handle(channel_id: str) -> tuple:
    try:
        from channels.listeners.discord_listener import _active_clients
    except Exception as e:
        logger.error("Cannot import discord listener for channel handle: %s", e)
        return None, None

    for _webhook_id, client in _active_clients.items():
        try:
            channel_ref = client.get_channel(int(channel_id))
            if channel_ref is not None:
                return channel_ref, client.loop
        except (ValueError, AttributeError, Exception) as e:
            logger.debug("Client did not resolve channel %s: %s", channel_id, e)
            continue
    return None, None

async def _deliver_outbound(
    msg: DiscordOutboundMessage,
    channel_ref: Any,
    discord_loop: Any,
) -> None:
    from channels.chunker import chunk_response
    from channels.delivery import deliver_to_channel

    chunks = chunk_response(msg.content)
    await deliver_to_channel(
        platform="discord",
        channel_ref=channel_ref,
        chunks=chunks,
        attachments=msg.attachments,
        discord_loop=discord_loop,
    )

def _get_sent_message_id(channel_ref: Any, msg: DiscordOutboundMessage) -> Optional[str]:
    return None
