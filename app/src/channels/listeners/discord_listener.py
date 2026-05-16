"""Discord listener using discord.py.

Runs a bot client in its own thread with its own event loop.
Captures messages from the registered channel and pushes to debounce queue.
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

# Registry of active Discord clients keyed by webhook_id
_active_clients: dict[str, discord.Client] = {}


def get_discord_client() -> discord.Client | None:
    """Return any active Discord client, or None if no listeners are running."""
    return next(iter(_active_clients.values()), None)


def create_discord_listener(
    record: "WebhookRecord",
    stop_event: threading.Event,
) -> Callable[[], None]:
    """Create a Discord listener function for threading.

    Returns a callable to be used as a Thread target. Runs a discord.py
    client that listens to a single channel.

    Args:
        record: WebhookRecord containing Discord configuration
        stop_event: Threading event to signal listener shutdown

    Returns:
        Callable that runs the Discord bot listener
    """
    config = record.get_config()
    bot_token = config["bot_token"]
    channel_id = int(config["channel_id"])
    conversation_id = record.conversation_id
    webhook_id = record.webhook_id

    def run() -> None:
        """Run the Discord bot in its own event loop."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        intents = discord.Intents.default()
        intents.message_content = True
        client = discord.Client(intents=intents)
        _active_clients[webhook_id] = client

        # Set up slash command tree
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

            # Sync slash commands to guild (deduped)
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
            # Ignore own messages and other bots
            if message.author == client.user or message.author.bot:
                return
            # Only listen to the registered channel
            if message.channel.id != channel_id:
                return

            # Import here to avoid circular dependency
            from channels.debounce import push_message

            push_message(
                conversation_id=conversation_id,
                message={
                    "platform": "discord",
                    "webhook_id": webhook_id,
                    "conversation_id": conversation_id,
                    "guild_id": str(message.guild.id) if message.guild else "",
                    "channel_id": str(message.channel.id),
                    "author": message.author.display_name,
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
                    "discord_loop": loop,  # Pass the Discord event loop for delivery
                    "timestamp": message.created_at.isoformat(),
                },
            )
            logger.debug(
                f"Discord message from {message.author.display_name} "
                f"in {webhook_id}: {message.clean_content[:50]}..."
            )

        async def runner():
            """Run the Discord client."""
            try:
                await client.start(bot_token)
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"Discord client error for {webhook_id}: {e}")
            finally:
                await client.close()

        async def main():
            """Main async function that watches for stop signal."""
            task = asyncio.create_task(runner())
            # Watch for stop signal from the manager
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
