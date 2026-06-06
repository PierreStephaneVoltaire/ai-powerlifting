

from __future__ import annotations
import asyncio
import logging
from typing import Dict, List, Any, TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    import discord

logger = logging.getLogger(__name__)

INTER_CHUNK_DELAY = 0.5

async def deliver_to_channel(
    platform: str,
    channel_ref: Any,
    chunks: List[str],
    attachments: List[Dict[str, Any]],
    discord_loop: Any = None,
) -> None:

    if platform == "discord":
        await _deliver_discord(channel_ref, chunks, attachments, discord_loop)
    elif platform == "openwebui":
        await _deliver_openwebui(channel_ref, chunks, attachments)
    else:
        logger.error(f"Unknown platform for delivery: {platform}")

async def _deliver_discord(
    channel: "discord.TextChannel",
    chunks: List[str],
    attachments: List[Dict[str, Any]],
    discord_loop: Any = None,
) -> None:

    import discord
    from config import DISCORD_MAX_CONTENT_CHARS, DISCORD_MAX_ATTACHMENTS_PER_MESSAGE
    from channels.chunker import chunk_response

    # --- Build discord.File objects from attachments ---
    discord_files: List[discord.File] = []
    skipped_attachments: List[str] = []

    for att in attachments:
        local_path = att.get("local_path")
        filename = att.get("filename", "attachment")

        if not local_path:
            logger.warning(
                f"Skipping attachment '{filename}': no local_path available. "
                f"File was not materialized and cannot be sent to Discord."
            )
            skipped_attachments.append(filename)
            continue

        try:
            discord_files.append(
                discord.File(local_path, filename=filename)
            )
        except Exception as e:
            logger.warning(
                f"Cannot attach '{filename}' from {local_path}: {e}. "
                f"File skipped — it will NOT be delivered."
            )
            skipped_attachments.append(filename)

    if skipped_attachments:
        logger.warning(
            f"{len(skipped_attachments)} attachment(s) could not be sent: "
            f"{skipped_attachments}"
        )

    # --- Defense-in-depth: re-chunk any chunk that exceeds Discord's hard limit ---
    safe_chunks: List[str] = []
    for chunk in chunks:
        if len(chunk) > DISCORD_MAX_CONTENT_CHARS:
            logger.warning(
                f"Chunk of {len(chunk)} chars exceeds Discord limit "
                f"({DISCORD_MAX_CONTENT_CHARS}), re-chunking as safety net"
            )
            safe_chunks.extend(
                chunk_response(chunk, max_chars=DISCORD_MAX_CONTENT_CHARS - 200)
            )
        else:
            safe_chunks.append(chunk)

    # --- Distribute discord.File attachments across chunks (max 10 per message) ---
    file_idx = 0
    for i, chunk in enumerate(safe_chunks):
        files_for_this_chunk: List[discord.File] = []
        while (
            file_idx < len(discord_files)
            and len(files_for_this_chunk) < DISCORD_MAX_ATTACHMENTS_PER_MESSAGE
        ):
            files_for_this_chunk.append(discord_files[file_idx])
            file_idx += 1

        try:
            send_coro = channel.send(
                content=chunk,
                files=files_for_this_chunk if files_for_this_chunk else None,
            )
            if discord_loop:
                future = asyncio.run_coroutine_threadsafe(send_coro, discord_loop)
                await asyncio.wrap_future(future)
            else:
                await send_coro
            logger.debug(f"Sent Discord chunk {i+1}/{len(safe_chunks)}")
        except discord.HTTPException as e:
            logger.error(f"Discord send failed: {e}")
            break
        except Exception as e:
            logger.error(f"Unexpected Discord error: {e}")
            break

        is_last = i == len(safe_chunks) - 1
        if not is_last:
            await asyncio.sleep(INTER_CHUNK_DELAY)

    # --- If there are leftover files after all chunks, send them in extra messages ---
    while file_idx < len(discord_files):
        batch: List[discord.File] = []
        while (
            file_idx < len(discord_files)
            and len(batch) < DISCORD_MAX_ATTACHMENTS_PER_MESSAGE
        ):
            batch.append(discord_files[file_idx])
            file_idx += 1
        try:
            send_coro = channel.send(
                content="📎 *(additional attachments)*",
                files=batch,
            )
            if discord_loop:
                future = asyncio.run_coroutine_threadsafe(send_coro, discord_loop)
                await asyncio.wrap_future(future)
            else:
                await send_coro
            logger.info(f"Sent {len(batch)} leftover attachment(s) in extra message")
        except discord.HTTPException as e:
            logger.error(f"Discord send failed for leftover attachments: {e}")
            break
        except Exception as e:
            logger.error(f"Unexpected Discord error for leftover attachments: {e}")
            break

async def _deliver_openwebui(
    channel_ref: Dict[str, str],
    chunks: List[str],
    attachments: List[Dict[str, Any]],
) -> None:

    base_url = channel_ref["base_url"].rstrip("/")
    channel_id = channel_ref["channel_id"]
    api_key = channel_ref["api_key"]

    full_response = "\n\n".join(chunks)

    if attachments:
        full_response += "\n\n**Attachments:**\n"
        for att in attachments:
            filename = att.get("filename", "attachment")
            url = att.get("url", "")
            full_response += f"- [{filename}]({url})\n"

    async with httpx.AsyncClient(
        base_url=base_url,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=30.0,
    ) as client:
        try:
            resp = await client.post(
                f"/api/v1/channels/{channel_id}/messages",
                json={
                    "role": "assistant",
                    "content": full_response,
                },
            )
            
            if resp.status_code in (200, 201):
                logger.info(f"OpenWebUI delivery successful")
            else:
                logger.error(
                    f"OpenWebUI delivery failed: {resp.status_code} - "
                    f"{resp.text[:200]}"
                )
        except httpx.TimeoutException:
            logger.error("OpenWebUI delivery timeout")
        except httpx.RequestError as e:
            logger.error(f"OpenWebUI connection error: {e}")
        except Exception as e:
            logger.error(f"OpenWebUI delivery error: {e}")

async def send_typing_indicator(platform: str, channel_ref: Any) -> None:

    if platform == "discord":
        pass

async def send_error_message(
    platform: str,
    channel_ref: Any,
    error_message: str,
) -> None:

    await deliver_to_channel(
        platform=platform,
        channel_ref=channel_ref,
        chunks=[f"❌ Error: {error_message}"],
        attachments=[],
    )

async def deliver_to_openwebui(
    api_url: str,
    channel_id: str,
    chunks: List[str],
    attachments: List[Dict[str, Any]],
) -> None:

    if not api_url:
        logger.error("OpenWebUI API URL not configured")
        return
    
    base_url = api_url.rstrip("/")
    
    full_response = "\n\n".join(chunks)
    
    if attachments:
        full_response += "\n\n**Attachments:**\n"
        for att in attachments:
            filename = att.get("filename", "attachment")
            url = att.get("url", "")
            full_response += f"- [{filename}]({url})\n"
    
    async with httpx.AsyncClient(
        base_url=base_url,
        timeout=30.0,
    ) as client:
        try:
            resp = await client.post(
                f"/api/v1/channels/{channel_id}/messages",
                json={
                    "role": "assistant",
                    "content": full_response,
                },
            )
            
            if resp.status_code in (200, 201):
                logger.info(f"OpenWebUI heartbeat delivery successful")
            else:
                logger.error(
                    f"OpenWebUI heartbeat delivery failed: {resp.status_code} - "
                    f"{resp.text[:200]}"
                )
        except httpx.TimeoutException:
            logger.error("OpenWebUI heartbeat delivery timeout")
        except httpx.RequestError as e:
            logger.error(f"OpenWebUI heartbeat connection error: {e}")
        except Exception as e:
            logger.error(f"OpenWebUI heartbeat delivery error: {e}")
