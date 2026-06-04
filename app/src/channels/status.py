






from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

class StatusType(Enum):
    MESSAGE_RECEIVED = "message_received"
    MODEL_SELECTED = "model_selected"
    SUBAGENT_SPAWNING = "subagent_spawning"
    SUBAGENT_COMPLETED = "subagent_completed"
    SUBAGENT_FAILED = "subagent_failed"
    TOOL_STARTED = "tool_started"
    TOOL_COMPLETED = "tool_completed"
    TOOL_FAILED = "tool_failed"
    CLASSIFICATION_STARTED = "classification_started"
    CLASSIFICATION_COMPLETED = "classification_completed"
    CLASSIFICATION_FAILED = "classification_failed"
    INTENT_DECIDED = "intent_decided"
    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    TASK_TRANSITION = "task_transition"
    ENQUEUE_FAILED = "enqueue_failed"

_STATUS_COLORS = {
    StatusType.MESSAGE_RECEIVED: 0x3498DB,
    StatusType.MODEL_SELECTED: 0x2ECC71,
    StatusType.SUBAGENT_SPAWNING: 0xF39C12,
    StatusType.SUBAGENT_COMPLETED: 0x2ECC71,
    StatusType.SUBAGENT_FAILED: 0xE74C3C,
    StatusType.TOOL_STARTED: 0x9B59B6,
    StatusType.TOOL_COMPLETED: 0x2ECC71,
    StatusType.TOOL_FAILED: 0xE74C3C,
    StatusType.CLASSIFICATION_STARTED: 0x3498DB,
    StatusType.CLASSIFICATION_COMPLETED: 0x2ECC71,
    StatusType.CLASSIFICATION_FAILED: 0xE74C3C,
    StatusType.INTENT_DECIDED: 0x1ABC9C,
    StatusType.TASK_STARTED: 0xF39C12,
    StatusType.TASK_COMPLETED: 0x2ECC71,
    StatusType.TASK_FAILED: 0xE74C3C,
    StatusType.TASK_TRANSITION: 0x95A5A6,
    StatusType.ENQUEUE_FAILED: 0xE74C3C,
}


def _build_embed(
    status_type: StatusType,
    title: str,
    description: str = "",
    fields: Optional[Dict[str, str]] = None,
) -> Any:
    import discord
    color = _STATUS_COLORS.get(status_type, 0x95A5A6)
    embed = discord.Embed(
        title=title,
        description=description or None,
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    if fields:
        for name, value in fields.items():
            embed.add_field(name=name, value=str(value)[:1024], inline=True)
    embed.set_footer(text="IF Status")
    return embed


async def send_status(
    status_type: StatusType,
    title: str,
    description: str = "",
    fields: Optional[Dict[str, str]] = None,
) -> None:
    from channels.context import get_platform_context

    ctx = get_platform_context()
    if not ctx or ctx.get("platform") != "discord":
        return

    channel = ctx.get("channel_ref")
    discord_loop = ctx.get("discord_loop")

    if not channel or not discord_loop:
        return

    await _fire_embed(status_type, title, description, fields, channel, discord_loop)


async def send_status_direct(
    status_type: StatusType,
    title: str,
    channel_ref: Any,
    discord_loop: Any,
    description: str = "",
    fields: Optional[Dict[str, str]] = None,
) -> None:
    if not channel_ref or not discord_loop:
        return
    await _fire_embed(status_type, title, description, fields, channel_ref, discord_loop)


async def _fire_embed(
    status_type: StatusType,
    title: str,
    description: str,
    fields: Optional[Dict[str, str]],
    channel: Any,
    discord_loop: Any,
) -> None:
    try:
        embed = _build_embed(status_type, title, description, fields)
        coro = channel.send(embed=embed)
        if discord_loop.is_running():
            future = asyncio.run_coroutine_threadsafe(coro, discord_loop)
            future.add_done_callback(lambda f: None)
        else:
            await coro
    except Exception as e:
        logger.debug("[Status] Failed to send embed: %s", e)
