import asyncio
import hashlib
import logging
import re

import discord
from discord import app_commands

from .assistant_client import AssistantClient, proposal_message
from .store import Registration
from .users import Identity, UserDirectory

logger = logging.getLogger("coach.discord.gateway")
MESSAGE_LIMIT = 2000
NOT_LINKED = "Your Discord account is not linked to a powerlifting Person yet."
DECISION = re.compile(r"^\s*(approve|reject)\s+`?([A-Za-z0-9_-]+)`?(?:\s+`?(\S+?)`?)?\s*$", re.IGNORECASE)


def chunks(text: str) -> list[str]:
    text = text.strip() or "(no reply)"
    parts = []
    while text:
        if len(text) <= MESSAGE_LIMIT:
            parts.append(text)
            break
        cut = text.rfind("\n", 0, MESSAGE_LIMIT)
        cut = cut if cut > MESSAGE_LIMIT // 2 else MESSAGE_LIMIT
        parts.append(text[:cut])
        text = text[cut:].lstrip("\n")
    return parts


def token_key(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def message_text(message) -> str:
    attachments = getattr(message, "attachments", None) or []
    if not attachments:
        return message.clean_content
    listed = "\n".join(f"- {attachment.filename}: {attachment.url}" for attachment in attachments)
    return f"{message.clean_content}\n\nAttachments:\n{listed}".strip()


def conversation_for(athlete: str, channel_id: str) -> str:
    return f"powerlifting:{athlete}:discord:{channel_id}"


class Relay:
    def __init__(self, assistant: AssistantClient, directory: UserDirectory):
        self.assistant = assistant
        self.directory = directory
        self.locks: dict[tuple[str, str], asyncio.Lock] = {}

    async def identity(self, author_id: int | str) -> Identity | None:
        return await asyncio.to_thread(self.directory.resolve, author_id)

    async def post(self, message, text: str) -> None:
        for index, part in enumerate(chunks(text)):
            if index == 0:
                await message.reply(part, mention_author=False)
            else:
                await message.channel.send(part)

    async def decide(self, message, identity: Identity, text: str) -> bool:
        match = DECISION.match(text)
        if not match:
            return False
        action, proposal_id, target = match.groups()
        approve = action.lower() == "approve"
        try:
            outcome = await self.assistant.decide(identity.person, identity.athlete, proposal_id, approve, target if approve else None)
        except Exception as exc:
            logger.exception("assistant decision failed")
            outcome = f"The assistant is unavailable right now ({type(exc).__name__})."
        if outcome is None:
            return False
        await self.post(message, outcome)
        return True

    async def answer(self, message, text: str) -> None:
        identity = await self.identity(message.author.id)
        if not identity:
            await message.reply(NOT_LINKED, mention_author=False)
            return
        if await self.decide(message, identity, text):
            return
        channel_id = str(message.channel.id)
        proposals = []
        async with self.locks.setdefault((identity.athlete, channel_id), asyncio.Lock()):
            try:
                async with message.channel.typing():
                    answer = await self.assistant.ask(identity.person, identity.athlete, conversation_for(identity.athlete, channel_id), text)
                reply, proposals = answer.content, answer.proposals
            except Exception as exc:
                logger.exception("assistant request failed")
                reply = f"The assistant is unavailable right now ({type(exc).__name__})."
        await self.post(message, reply)
        for proposal in proposals:
            await message.channel.send(proposal_message(proposal))


class Gateway:
    def __init__(self, relay: Relay):
        self.relay = relay
        self.channels: dict[str, set[str]] = {}
        self.tasks: dict[str, asyncio.Task] = {}
        self.clients: dict[str, discord.Client] = {}

    def attach(self, registration: Registration) -> None:
        key = token_key(registration.bot_token)
        self.channels.setdefault(key, set()).add(registration.channel_id)
        task = self.tasks.get(key)
        if task is None or task.done():
            self.tasks[key] = asyncio.create_task(self._run(key, registration.bot_token), name=f"discord-{key[:8]}")

    def detach(self, registration: Registration) -> None:
        key = token_key(registration.bot_token)
        channels = self.channels.get(key, set())
        channels.discard(registration.channel_id)
        if not channels:
            self.channels.pop(key, None)
            client = self.clients.pop(key, None)
            task = self.tasks.pop(key, None)
            if client:
                asyncio.create_task(client.close())
            elif task:
                task.cancel()

    def listening(self, registration: Registration) -> bool:
        key = token_key(registration.bot_token)
        task = self.tasks.get(key)
        return registration.channel_id in self.channels.get(key, set()) and task is not None and not task.done()

    def _client(self, key: str) -> discord.Client:
        intents = discord.Intents.default()
        intents.message_content = True
        client = discord.Client(intents=intents)
        tree = app_commands.CommandTree(client)
        relay = self.relay

        def watched(channel_id: int) -> bool:
            return str(channel_id) in self.channels.get(key, set())

        @client.event
        async def on_ready():
            logger.info("Discord gateway connected as %s", client.user)
            guilds = {getattr(client.get_channel(int(channel)), "guild", None) for channel in self.channels.get(key, set())}
            for guild in filter(None, guilds):
                try:
                    tree.copy_global_to(guild=guild)
                    await tree.sync(guild=guild)
                except discord.HTTPException as exc:
                    logger.error("Slash command sync failed for %s: %s", guild.id, exc)

        @client.event
        async def on_message(message):
            if message.author.bot or not watched(message.channel.id):
                return
            await relay.answer(message, message_text(message))

        @client.event
        async def on_message_edit(before, after):
            if after.author.bot or not watched(after.channel.id) or before.content == after.content:
                return
            await relay.answer(after, f"I edited my previous message. Use this corrected text instead:\n{message_text(after)}")

        return client

    async def _run(self, key: str, token: str) -> None:
        while key in self.channels:
            client = self._client(key)
            self.clients[key] = client
            try:
                await client.start(token)
            except asyncio.CancelledError:
                await client.close()
                raise
            except discord.LoginFailure:
                logger.error("Discord rejected the bot token for %s; not retrying", key[:8])
                return
            except Exception:
                logger.exception("Discord gateway crashed; reconnecting")
            finally:
                if not client.is_closed():
                    await client.close()
            if key in self.channels:
                await asyncio.sleep(5)

    async def close(self) -> None:
        for client in list(self.clients.values()):
            await client.close()
        for task in list(self.tasks.values()):
            task.cancel()
        await asyncio.gather(*self.tasks.values(), return_exceptions=True)
