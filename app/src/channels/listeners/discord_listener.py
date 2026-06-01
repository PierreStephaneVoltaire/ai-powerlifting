"""Discord listener using discord.py.

Runs a bot client in its own thread with its own event loop.
Captures messages from the registered channel and pushes to the
channel coordinator for DynamoDB-backed orchestration.
Registers slash commands as guild commands on first connect (deduped).
"""
from __future__ import annotations
import asyncio
import threading
import logging
from typing import TYPE_CHECKING, Callable

import discord
from discord import app_commands

if TYPE_CHECKING:
    from storage.models import WebhookRecord

logger = logging.getLogger(__name__)

_active_clients: dict[str, discord.Client] = {}


def get_discord_client() -> discord.Client | None:
    return next(iter(_active_clients.values()), None)


def create_discord_listener(
    record: "WebhookRecord",
    stop_event: threading.Event,
) -> Callable[[], None]:

    config = record.get_config()
    bot_token = config["bot_token"]
    channel_id = int(config["channel_id"])
    conversation_id = record.conversation_id
    webhook_id = record.webhook_id

    def run() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        intents = discord.Intents.default()
        intents.message_content = True
        client = discord.Client(intents=intents)
        _active_clients[webhook_id] = client

        tree = app_commands.CommandTree(client)

        from channels.slash_commands import setup_command_tree, should_sync

        try:
            setup_command_tree(tree, channel_id, conversation_id, webhook_id)
        except Exception as e:
            logger.error(
                f"Slash command setup failed for {webhook_id} "
                f"(messages will still be received): {e}",
                exc_info=True,
            )

        @client.event
        async def on_ready():
            logger.info(
                f"Discord listener {webhook_id} connected as {client.user}"
            )

            channel = client.get_channel(channel_id)
            if channel and hasattr(channel, "guild") and channel.guild:
                guild = channel.guild
                if should_sync(client.user.id, guild.id):
                    try:
                        tree.copy_global_to(guild=guild)
                        existing_commands = await tree.fetch_commands(guild=guild)
                        existing_names = {cmd.name for cmd in existing_commands}
                        local_commands = tree.get_commands(guild=guild)
                        local_names = {cmd.name for cmd in local_commands}
                        if existing_names != local_names:
                            await tree.sync(guild=guild)
                            logger.info(
                                f"Synced slash commands to guild "
                                f"{guild.name} ({guild.id})"
                            )
                        else:
                            logger.info(
                                f"Slash commands already registered for guild "
                                f"{guild.name} ({guild.id}), skipping sync"
                            )
                    except discord.HTTPException as e:
                        logger.error(
                            f"Failed to sync slash commands to "
                            f"{guild.name}: {e}"
                        )
                else:
                    logger.debug(
                        f"Slash commands already synced for guild "
                        f"{guild.name} ({guild.id}), skipping"
                    )
            else:
                logger.warning(
                    f"Could not resolve guild for channel {channel_id} "
                    f"in {webhook_id}"
                )

        @client.event
        async def on_message(message: discord.Message):
            if message.author == client.user or message.author.bot:
                return
            if message.channel.id != channel_id:
                return

            from channels.channel_coordinator import push_discord_event

            push_discord_event(
                conversation_id=conversation_id,
                message={
                    "platform": "discord",
                    "webhook_id": webhook_id,
                    "conversation_id": conversation_id,
                    "message_id": str(message.id),
                    "guild_id": str(message.guild.id) if message.guild else "",
                    "channel_id": str(message.channel.id),
                    "author": message.author.display_name,
                    "author_id": str(message.author.id),
                    "content": message.clean_content,
                    "attachments": [
                        {
                            "filename": att.filename,
                            "url": att.url,
                            "content_type": (
                                att.content_type
                                or "application/octet-stream"
                            ),
                        }
                        for att in message.attachments
                    ],
                    "channel_ref": message.channel,
                    "discord_loop": loop,
                    "timestamp": message.created_at.isoformat(),
                    "edited_at": message.edited_at.isoformat() if message.edited_at else "",
                    "reply_to_message_id": (
                        str(message.reference.message_id)
                        if message.reference and getattr(message.reference, "message_id", None)
                        else None
                    ),
                    "event_type": "message_create",
                },
            )
            logger.debug(
                f"Discord message from {message.author.display_name} "
                f"in {webhook_id}: {message.clean_content[:50]}..."
            )

        @client.event
        async def on_message_edit(before: discord.Message, after: discord.Message):
            if after.author == client.user or after.author.bot:
                return
            if after.channel.id != channel_id:
                return

            from channels.channel_coordinator import push_discord_event

            push_discord_event(
                conversation_id=conversation_id,
                message={
                    "platform": "discord",
                    "webhook_id": webhook_id,
                    "conversation_id": conversation_id,
                    "message_id": str(after.id),
                    "guild_id": str(after.guild.id) if after.guild else "",
                    "channel_id": str(after.channel.id),
                    "author": after.author.display_name,
                    "author_id": str(after.author.id),
                    "content": after.clean_content,
                    "attachments": [
                        {
                            "filename": att.filename,
                            "url": att.url,
                            "content_type": (
                                att.content_type
                                or "application/octet-stream"
                            ),
                        }
                        for att in after.attachments
                    ],
                    "channel_ref": after.channel,
                    "discord_loop": loop,
                    "timestamp": after.created_at.isoformat(),
                    "edited_at": after.edited_at.isoformat() if after.edited_at else "",
                    "reply_to_message_id": (
                        str(after.reference.message_id)
                        if after.reference and getattr(after.reference, "message_id", None)
                        else None
                    ),
                    "is_edit": True,
                    "previous_content": before.clean_content,
                    "event_type": "message_edit",
                },
            )
            logger.debug(
                f"Discord edit from {after.author.display_name} "
                f"in {webhook_id}: {after.clean_content[:50]}..."
            )

        async def runner():
            try:
                await client.start(bot_token)
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"Discord client error for {webhook_id}: {e}")
            finally:
                await client.close()

        async def main():
            task = asyncio.create_task(runner())
            while not stop_event.is_set():
                await asyncio.sleep(1)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        try:
            loop.run_until_complete(main())
        except Exception as e:
            logger.error(f"Discord listener error for {webhook_id}: {e}")
        finally:
            _active_clients.pop(webhook_id, None)
            loop.close()
            logger.info(f"Discord listener stopped for {webhook_id}")

    return run
