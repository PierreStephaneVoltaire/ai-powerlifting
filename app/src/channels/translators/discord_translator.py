"""Discord message translator.

Converts a debounced Discord message batch into a ChatCompletionRequest
format that can be processed by the existing agent pipeline.
"""
from __future__ import annotations
import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


def translate_discord_batch(
    messages: List[Dict[str, Any]],
    conversation_id: str,
    history_messages: Optional[List[Any]] = None,
) -> Dict[str, Any]:
    """Convert Discord message batch to ChatCompletionRequest format.

    Takes channel history + current message batch and builds a full
    conversation context for the agent.

    Args:
        messages: List of message dicts from Discord listener (current)
        conversation_id: Conversation ID for this batch
        history_messages: List of discord.Message objects from channel history

    Returns:
        Dict matching ChatCompletionRequest shape with messages and metadata
    """
    pending_uploads: List[Dict[str, Any]] = []
    api_messages: List[Dict[str, Any]] = []

    # Get the bot's own user ID directly from the active Discord client.
    # This is reliable regardless of whether IF has sent any messages in
    # the fetched history window (avoids the fragile "scan for a bot message"
    # heuristic that left bot_id=None when no prior IF messages existed).
    bot_id = None
    try:
        from channels.listeners.discord_listener import get_discord_client
        _client = get_discord_client()
        if _client and _client.user:
            bot_id = _client.user.id
    except Exception:
        pass

    # Process history messages (they come newest-first, we need oldest-first for API)
    if history_messages:
        for msg in reversed(history_messages):
            content = msg.clean_content
            if not content:
                continue

            if bot_id and msg.author.id == bot_id:
                # IF's own message → assistant role
                api_messages.append({
                    "role": "assistant",
                    "content": content,
                })
            else:
                # All other messages (human or other bots) → user role
                author = msg.author.display_name if msg.author else "unknown"
                api_messages.append({
                    "role": "user",
                    "content": f"[{author}]: {content}",
                })

    # Append current messages from debounce queue
    for msg in messages:
        text = msg.get("content", "")
        author = msg.get("author", "unknown")
        if text:
            api_messages.append({
                "role": "user",
                "content": f"[{author}]: {text}",
            })

        # Extract attachments for upload
        for att in msg.get("attachments", []):
            ct = att.get("content_type", "")
            url = att.get("url", "")
            filename = att.get("filename", "attachment")

            if url:
                pending_uploads.append({
                    "filename": filename,
                    "url": url,
                    "content_type": ct,
                })

    # Add attachment references to the last user message
    if pending_uploads:
        last_user_idx = None
        for i in range(len(api_messages) - 1, -1, -1):
            if api_messages[i]["role"] == "user":
                last_user_idx = i
                break

        if last_user_idx is not None:
            attachment_text = " ".join(
                f"[Attachment: {att['filename']} — uploads/{att['filename']}]"
                for att in pending_uploads
            )
            api_messages[last_user_idx]["content"] = (
                f"{api_messages[last_user_idx]['content']}\n{attachment_text}"
            )

    logger.info(
        f"[Translator] Built {len(api_messages)} messages from "
        f"{len(history_messages) if history_messages else 0} history + {len(messages)} current"
    )

    return {
        "model": "if-prototype",
        "stream": True,
        "messages": api_messages,
        "platform": "discord",
        "guild_id": messages[-1].get("guild_id", "") if messages else "",
        "channel_id": messages[-1].get("channel_id", conversation_id) if messages else conversation_id,
        "conversation_id": conversation_id,
        "_conversation_id": conversation_id,
        "_pending_uploads": pending_uploads,
    }
