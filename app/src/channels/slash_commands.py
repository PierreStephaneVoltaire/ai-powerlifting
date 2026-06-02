





from __future__ import annotations

import logging
import threading
from typing import List

import discord
from discord import app_commands

logger = logging.getLogger(__name__)

_synced_guilds: set[tuple[int, int]] = set()
_sync_lock = threading.Lock()

def should_sync(bot_user_id: int, guild_id: int) -> bool:





    with _sync_lock:
        key = (bot_user_id, guild_id)
        if key in _synced_guilds:
            return False
        _synced_guilds.add(key)
        return True

def setup_command_tree(
    tree: app_commands.CommandTree,
    channel_id: int,
    conversation_id: str,
    webhook_id: str,
) -> None:











    cache_key = str(channel_id)
    context_id = f"discord_{channel_id}"

    def _clear_opencode_session(interaction: discord.Interaction) -> None:
        from flow.session_dirs import clear_session_dir

        request_data = {
            "platform": "discord",
            "channel_id": str(interaction.channel_id or channel_id),
            "guild_id": str(interaction.guild_id or ""),
            "conversation_id": str(interaction.channel_id or channel_id),
        }
        clear_session_dir(request_data, None, cache_key)

    @tree.command(
        name="end_convo",
        description="Clear conversation state and force reclassification",
    )
    async def end_convo_cmd(interaction: discord.Interaction):
        try:
            from routing.cache import get_cache

            cache = get_cache()
            cache.evict(cache_key)

            try:
                from storage.factory import get_webhook_store

                store = get_webhook_store()
                if store:
                    await cache.persist_eviction(cache_key, store._backend)
            except Exception as e:
                logger.warning(f"[SlashCmd] Failed to persist eviction: {e}")

            _clear_opencode_session(interaction)

            await interaction.response.send_message(
                "Acknowledged. Categorisation state cleared. "
                "Next message will be re-evaluated."
            )
        except Exception as e:
            logger.error(f"[SlashCmd] /end_convo error: {e}")
            await interaction.response.send_message(
                f"Error: {e}", ephemeral=True
            )

    @tree.command(
        name="pondering",
        description="Enter reflective conversation mode (heavy tier)",
    )
    async def pondering_cmd(interaction: discord.Interaction):
        try:
            from routing.cache import get_cache

            cache = get_cache()
            cache.pin(cache_key, 2)

            try:
                from storage.factory import get_webhook_store

                store = get_webhook_store()
                if store:
                    await cache.persist_entry(cache_key, store._backend)
            except Exception as e:
                logger.warning(f"[SlashCmd] Failed to persist pin: {e}")

            await interaction.response.send_message(
                "Acknowledged. Routing pinned to preset: pondering. "
                "Send /end_convo to release."
            )
        except Exception as e:
            logger.error(f"[SlashCmd] /pondering error: {e}")
            await interaction.response.send_message(
                f"Error: {e}", ephemeral=True
            )

    @tree.command(
        name="clear",
        description="Delete recent messages from this channel",
    )
    @app_commands.describe(amount="Number of messages to delete (default 100)")
    async def clear_cmd(interaction: discord.Interaction, amount: int = 100):
        if not interaction.channel:
            await interaction.response.send_message(
                "Cannot determine channel.", ephemeral=True
            )
            return

        perms = interaction.channel.permissions_for(interaction.guild.me)
        if not perms.manage_messages:
            await interaction.response.send_message(
                "I need the **Manage Messages** permission to clear chat.",
                ephemeral=True,
            )
            return

        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message(
                "You need the **Manage Messages** permission to use this.",
                ephemeral=True,
            )
            return

        amount = max(1, min(amount, 1000))
        await interaction.response.defer(ephemeral=True)

        try:
            deleted = await interaction.channel.purge(limit=amount)
            _clear_opencode_session(interaction)
            await interaction.followup.send(
                f"Deleted {len(deleted)} message(s).", ephemeral=True
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "Missing permissions to delete messages.", ephemeral=True
            )
        except discord.HTTPException as e:
            await interaction.followup.send(
                f"Failed to delete messages: {e}", ephemeral=True
            )

    @tree.command(
        name="chat_history",
        description="Export recent channel history as a Markdown file",
    )
    @app_commands.describe(
        limit="Number of recent messages to export (default 100, max 1000)",
    )
    async def chat_history_cmd(interaction: discord.Interaction, limit: int = 100):
        if not interaction.channel:
            await interaction.response.send_message(
                "Cannot determine channel.", ephemeral=True
            )
            return

        limit = max(1, min(limit, 1000))
        await interaction.response.defer()

        try:
            from channels.history_export import (
                discord_messages_to_history_events,
                render_discord_history_markdown,
            )
            from flow.session_dirs import resolve_session_dir, safe_segment

            messages: list[discord.Message] = []
            async for message in interaction.channel.history(limit=limit):
                messages.append(message)
            messages.reverse()

            bot_user = getattr(interaction.client, "user", None)
            bot_user_id = getattr(bot_user, "id", None)
            events = discord_messages_to_history_events(
                messages,
                bot_user_id=bot_user_id,
            )

            actual_channel_id = str(interaction.channel_id or channel_id)
            request_data = {
                "platform": "discord",
                "channel_id": actual_channel_id,
                "guild_id": str(interaction.guild_id or ""),
                "conversation_id": actual_channel_id,
            }
            session_dir = resolve_session_dir(
                request_data,
                webhook=None,
                cache_key=actual_channel_id,
            )
            export_dir = session_dir / "exports"
            export_dir.mkdir(parents=True, exist_ok=True)

            channel_name = str(getattr(interaction.channel, "name", "") or "")
            filename = (
                f"chat-history-{safe_segment(actual_channel_id, 'channel')}.md"
            )
            export_path = export_dir / filename
            export_path.write_text(
                render_discord_history_markdown(
                    events,
                    channel_name=channel_name,
                    channel_id=actual_channel_id,
                ),
                encoding="utf-8",
            )

            await interaction.followup.send(
                f"Exported {len(events)} message(s).",
                file=discord.File(export_path, filename=filename),
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "Missing permissions to read history or upload files.",
                ephemeral=True,
            )
        except discord.HTTPException as e:
            logger.error(f"[SlashCmd] /chat_history Discord error: {e}")
            await interaction.followup.send(
                f"Failed to export chat history: {e}",
                ephemeral=True,
            )
        except Exception as e:
            logger.error(f"[SlashCmd] /chat_history error: {e}", exc_info=True)
            await interaction.followup.send(
                f"Error exporting chat history: {e}",
                ephemeral=True,
            )

    def _make_reflection_handler(
        command_name: str, description: str, args_hint: str = "",
    ):


        @tree.command(name=command_name, description=description)
        @app_commands.describe(
            args=args_hint or "Optional arguments for the command"
        )
        async def handler(interaction: discord.Interaction, args: str = ""):
            await interaction.response.defer()
            try:
                from memory.user_facts import get_user_fact_store
                from agent.commands import get_command_handler
                from agent.reflection import get_reflection_engine

                store = get_user_fact_store()
                reflection_engine = get_reflection_engine()
                cmd_handler = get_command_handler(
                    store, reflection_engine, context_id
                )

                result = cmd_handler.handle(f"/{command_name}", args)

                if len(result) <= 2000:
                    await interaction.followup.send(result)
                else:
                    chunks = [
                        result[i : i + 2000]
                        for i in range(0, len(result), 2000)
                    ]
                    for chunk in chunks:
                        await interaction.followup.send(chunk)
            except ImportError as e:
                await interaction.followup.send(
                    f"Command not available: {e}"
                )
            except Exception as e:
                logger.error(
                    f"[SlashCmd] /{command_name} error: {e}"
                )
                await interaction.followup.send(
                    f"Error executing /{command_name}: {e}"
                )

        return handler

    _make_reflection_handler("reflect", "Trigger a manual reflection cycle")
    _make_reflection_handler(
        "gaps",
        "List capability gaps ranked by priority",
        args_hint="Minimum trigger count (default 1)",
    )
    _make_reflection_handler("patterns", "Show detected behavioral patterns")
    _make_reflection_handler(
        "opinions", "Show opinion pairs (operator vs agent positions)"
    )
    _make_reflection_handler(
        "growth",
        "Show operator growth report",
        args_hint="Number of days to look back (default 30)",
    )
    _make_reflection_handler(
        "meta", "Show store health metrics and category suggestions"
    )
    _make_reflection_handler(
        "tools", "Show tool suggestions from capability gaps"
    )

    @tree.command(
        name="import",
        description="Import a training program spreadsheet (XLSX/CSV)",
    )
    @app_commands.describe(
        file="Spreadsheet file to import",
    )
    async def import_cmd(interaction: discord.Interaction, file: discord.Attachment):
        await interaction.response.defer()
        try:
            prompt = f"Process the uploaded file {file.filename} as a program/template import."
            result = await _invoke_via_agent(prompt, interaction)
            await _send_chunked(interaction, result)
        except Exception as e:
            logger.error(f"[SlashCmd] /import error: {e}")
            await interaction.followup.send(f"Error: {e}")

    @tree.command(
        name="template",
        description="Manage or apply training templates",
    )
    @app_commands.describe(
        action="Action to perform",
        name="Template name (autocomplete)",
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="list", value="list"),
        app_commands.Choice(name="apply", value="apply"),
        app_commands.Choice(name="evaluate", value="evaluate"),
        app_commands.Choice(name="archive", value="archive"),
    ])
    async def template_cmd(interaction: discord.Interaction, action: str, name: str = ""):
        await interaction.response.defer()
        try:
            prompt = f"Template {action} {name}".strip()
            result = await _invoke_via_agent(prompt, interaction)
            await _send_chunked(interaction, result)
        except Exception as e:
            logger.error(f"[SlashCmd] /template error: {e}")
            await interaction.followup.send(f"Error: {e}")

    @template_cmd.autocomplete("name")
    async def template_name_autocomplete(
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[str]]:
        try:
            from mcp_runtime import get_mcp_manager
            import json

            raw = await get_mcp_manager().call_tool("template_list", {"include_archived": False})
            parsed = json.loads(raw)
            templates = parsed.get("templates", parsed if isinstance(parsed, list) else [])
            
            choices = [
                app_commands.Choice(name=t["name"], value=t.get("sk", t["name"]))
                for t in templates
                if isinstance(t, dict) and "name" in t and current.lower() in t["name"].lower()
            ]
            return choices[:25]
        except Exception as e:
            logger.warning(f"[Autocomplete] Failed: {e}")
            return []

    @tree.command(
        name="program_archive",
        description="Archive a program version",
    )
    @app_commands.describe(
        version="Version to archive (default: current)",
        confirm="Confirm archiving (required if version has future sessions)",
    )
    async def program_archive_cmd(interaction: discord.Interaction, version: str = "current", confirm: bool = False):
        await interaction.response.defer()
        try:
            prompt = f"Archive program version {version} (confirm={confirm})"
            result = await _invoke_via_agent(prompt, interaction)
            await _send_chunked(interaction, result)
        except Exception as e:
            logger.error(f"[SlashCmd] /program_archive error: {e}")
            await interaction.followup.send(f"Error: {e}")

    _register_dynamic_commands(tree, channel_id, conversation_id)

STATIC_COMMAND_NAMES = {
    "end_convo", "pondering", "clear", "chat_history", "reflect", "gaps",
    "patterns", "opinions", "growth", "meta", "tools",
    "import", "template", "program_archive",
}

MAX_DISCORD_CHAT_INPUT_COMMANDS = 100

async def _invoke_via_agent(message_content: str, interaction: discord.Interaction):

    from main import app
    from api.completions import process_chat_completion_internal
    from config import API_MODEL_NAME

    http_client = app.state.http_client
    request_data = {
        "model": API_MODEL_NAME,
        "messages": [{"role": "user", "content": message_content}],
        "platform": "discord",
        "channel_id": str(interaction.channel_id) if interaction.channel_id else "",
        "guild_id": str(interaction.guild_id) if interaction.guild_id else "",
        "conversation_id": str(interaction.channel_id) if interaction.channel_id else "",
        "user": str(interaction.user.id),
    }

    response_text, _ = await process_chat_completion_internal(
        request_data=request_data,
        http_client=http_client,
    )
    return response_text

async def _send_chunked(interaction: discord.Interaction, text: str):

    if len(text) <= 2000:
        await interaction.followup.send(text)
    else:
        for i in range(0, len(text), 2000):
            await interaction.followup.send(text[i : i + 2000])

def _make_proxy_command_handler(message_command: str, log_command: str):


    async def proxy_handler(interaction: discord.Interaction, args: str = ""):
        await interaction.response.defer()
        try:
            message_content = f"/{message_command} {args}".strip()
            result = await _invoke_via_agent(message_content, interaction)
            await _send_chunked(interaction, result)
        except Exception as e:
            logger.error(f"[SlashCmd] /{log_command} error: {e}")
            await interaction.followup.send(f"Error: {e}")

    return proxy_handler

def _register_dynamic_commands(tree, channel_id, conversation_id):

    used_names = set(STATIC_COMMAND_NAMES)
    _register_tool_commands(tree, used_names)
    _register_specialist_commands(tree, used_names)

def _register_tool_commands(tree, used_names: set[str]):

    try:
        from mcp_runtime import get_mcp_manager
        manager = get_mcp_manager()
        tool_names = manager.list_tool_names()
    except Exception:
        logger.debug("[SlashCmd] MCP tools not available, skipping tool commands")
        return

    for tool_name in tool_names:
        if len(used_names) >= MAX_DISCORD_CHAT_INPUT_COMMANDS:
            logger.warning(
                "[SlashCmd] Reached Discord slash command limit while registering tools; skipping remaining tools"
            )
            return

        discord_name = tool_name[:32]
        if discord_name in used_names:
            logger.warning(f"[SlashCmd] Skipping duplicate tool command: {discord_name} -> {tool_name}")
            continue

        description = f"Invoke MCP tool {tool_name}"[:100]

        tool_handler = _make_proxy_command_handler(tool_name, discord_name)
        tool_handler = app_commands.describe(
            args="Optional JSON arguments e.g. {\"weeks\": 4}"
        )(tool_handler)
        try:
            tree.command(name=discord_name, description=description)(tool_handler)
        except app_commands.errors.CommandAlreadyRegistered:
            logger.warning(
                f"[SlashCmd] Tool command name collision, skipping: {discord_name} -> {tool_name}"
            )
            continue
        used_names.add(discord_name)

def _register_specialist_commands(tree, used_names: set[str]):

    try:
        from agent.specialists import (
            SPECIALIST_COMMAND_ALIASES,
            list_specialists,
            get_specialist_command_map,
        )
        specialists = list_specialists()
        command_map = get_specialist_command_map()
    except Exception:
        logger.debug("[SlashCmd] Specialists not available, skipping specialist commands")
        return

    spec_by_slug = {spec.slug: spec for spec in specialists}

    ordered_command_items: list[tuple[str, str]] = []
    seen: set[str] = set()

    for alias, slug in SPECIALIST_COMMAND_ALIASES.items():
        if alias in command_map and alias not in seen:
            ordered_command_items.append((alias, command_map[alias]))
            seen.add(alias)

    for spec in specialists:
        if spec.slug in command_map and spec.slug not in seen:
            ordered_command_items.append((spec.slug, command_map[spec.slug]))
            seen.add(spec.slug)

    for command_name, slug in ordered_command_items:
        if len(used_names) >= MAX_DISCORD_CHAT_INPUT_COMMANDS:
            logger.warning(
                "[SlashCmd] Reached Discord slash command limit while registering specialists; skipping remaining specialist commands"
            )
            return

        discord_name = command_name[:32]
        if discord_name in used_names:
            logger.warning(f"[SlashCmd] Skipping duplicate specialist command: {discord_name} -> {slug}")
            continue

        spec = spec_by_slug.get(slug)
        if spec is None:
            continue

        description = spec.description[:100]

        specialist_handler = _make_proxy_command_handler(command_name, discord_name)
        specialist_handler = app_commands.describe(
            args="Task or question for the specialist"
        )(specialist_handler)
        try:
            tree.command(name=discord_name, description=description)(specialist_handler)
        except app_commands.errors.CommandAlreadyRegistered:
            logger.warning(
                f"[SlashCmd] Specialist command name collision, skipping: {discord_name} -> {slug}"
            )
            continue
        used_names.add(discord_name)
