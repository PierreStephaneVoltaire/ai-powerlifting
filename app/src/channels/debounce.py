










from __future__ import annotations
import asyncio
import threading
import logging
from typing import Dict, List, Any, Optional

from config import CHANNEL_DEBOUNCE_SECONDS

logger = logging.getLogger(__name__)

_lock = threading.Lock()

_buffers: Dict[str, List[Dict[str, Any]]] = {}

_timers: Dict[str, asyncio.TimerHandle] = {}

_main_loop: Optional[asyncio.AbstractEventLoop] = None

def init_debounce(loop: asyncio.AbstractEventLoop) -> None:







    global _main_loop
    _main_loop = loop
    logger.info(
        f"Debounce system initialized "
        f"(window={CHANNEL_DEBOUNCE_SECONDS}s)"
    )

def push_message(conversation_id: str, message: Dict[str, Any]) -> None:









    if _main_loop is None:
        logger.error("Debounce not initialized. Call init_debounce() first.")
        return

    with _lock:
        if conversation_id not in _buffers:
            _buffers[conversation_id] = []
        _buffers[conversation_id].append(message)
        buffer_size = len(_buffers[conversation_id])

    logger.debug(
        f"Message buffered for {conversation_id} "
        f"(buffer size: {buffer_size})"
    )

    _main_loop.call_soon_threadsafe(
        _schedule_flush, conversation_id
    )

def _schedule_flush(conversation_id: str) -> None:








    if _main_loop is None:
        return

    existing = _timers.get(conversation_id)
    if existing is not None:
        existing.cancel()

    handle = _main_loop.call_later(
        CHANNEL_DEBOUNCE_SECONDS,
        lambda: asyncio.ensure_future(_flush(conversation_id), loop=_main_loop),
    )
    _timers[conversation_id] = handle

async def _flush(conversation_id: str) -> None:








    with _lock:
        messages = _buffers.pop(conversation_id, [])
        _timers.pop(conversation_id, None)

    if not messages:
        return

    platform = messages[0].get("platform", "unknown")
    channel_ref = messages[-1].get("channel_ref")
    discord_loop = messages[-1].get("discord_loop")

    logger.info(
        f"Flushing {len(messages)} messages for {conversation_id} ({platform})"
    )

    from channels.dispatcher import dispatch_channel_batch

    try:
        await dispatch_channel_batch(
            messages=messages,
            conversation_id=conversation_id,
            platform=platform,
            channel_ref=channel_ref,
            discord_loop=discord_loop,
        )
    except Exception as e:
        logger.error(f"Dispatch failed for {conversation_id}: {e}")

def get_buffer_size(conversation_id: str) -> int:








    with _lock:
        return len(_buffers.get(conversation_id, []))

def clear_buffer(conversation_id: str) -> int:








    with _lock:
        messages = _buffers.pop(conversation_id, [])
        timer = _timers.pop(conversation_id, None)
        if timer is not None:
            timer.cancel()
    return len(messages)

def get_all_buffer_sizes() -> Dict[str, int]:





    with _lock:
        return {cid: len(msgs) for cid, msgs in _buffers.items()}
