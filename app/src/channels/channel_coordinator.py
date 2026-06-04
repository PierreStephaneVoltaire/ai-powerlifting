


















from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from channels.execution_models import get_instance_identity
from channels.execution_store import get_execution_store
from config import (
    CHANNEL_CLASSIFIER_DEBOUNCE_SECONDS,
    CHANNEL_CLASSIFIER_MAX_WAIT_SECONDS,
    OPENCODE_WORKSPACE_BASE,
)

logger = logging.getLogger(__name__)

_main_loop: Optional[asyncio.AbstractEventLoop] = None
_meta_lock = threading.Lock()
_channel_meta: Dict[str, Dict[str, Any]] = {}
_debounce_timers: Dict[str, asyncio.TimerHandle] = {}
_max_wait_timers: Dict[str, asyncio.TimerHandle] = {}
_active_classifier_owners: Dict[str, str] = {}

CLASSIFIER_LOCK_DURATION_SECONDS = 600
LOCK_RETRY_DEBOUNCE_SECONDS = 2.0

def init_channel_coordinator(loop: asyncio.AbstractEventLoop) -> None:
    global _main_loop
    _main_loop = loop
    logger.info(
        f"Channel coordinator initialized "
        f"(debounce={CHANNEL_CLASSIFIER_DEBOUNCE_SECONDS}s, "
        f"max_wait={CHANNEL_CLASSIFIER_MAX_WAIT_SECONDS}s)"
    )

def push_discord_event(conversation_id: str, message: Dict[str, Any]) -> None:
    if _main_loop is None:
        logger.error("Channel coordinator not initialized")
        return
    channel_id = message.get("channel_id", "")
    if not channel_id:
        logger.error("Discord event missing channel_id")
        return

    with _meta_lock:
        _channel_meta[channel_id] = {
            "webhook_id": message.get("webhook_id", ""),
            "conversation_id": conversation_id,
            "guild_id": message.get("guild_id", ""),
            "discord_loop": message.get("discord_loop"),
        }

    _main_loop.call_soon_threadsafe(
        _schedule_state_update, channel_id, message
    )

def _schedule_state_update(channel_id: str, message: Dict[str, Any]) -> None:
    asyncio.ensure_future(_update_state_and_schedule(channel_id, message))

async def _update_state_and_schedule(channel_id: str, message: Dict[str, Any]) -> None:
    store = get_execution_store()
    is_edit = (
        message.get("is_edit", False)
        or message.get("event_type") == "message_edit"
    )
    event_at = (
        message.get("edited_at")
        if is_edit and message.get("edited_at")
        else message.get("timestamp")
    ) or datetime.now(timezone.utc).isoformat()
    message_id = message.get("message_id", "")

    try:
        await store.update_channel_state_on_event(
            channel_id=channel_id,
            message_id=message_id,
            event_at=event_at,
            is_edit=is_edit,
            debounce_seconds=CHANNEL_CLASSIFIER_DEBOUNCE_SECONDS,
            max_wait_seconds=CHANNEL_CLASSIFIER_MAX_WAIT_SECONDS,
        )
    except Exception as e:
        logger.error(f"Failed to update channel state for {channel_id}: {e}")

    _schedule_timers(channel_id)

def _schedule_timers(channel_id: str) -> None:
    if _main_loop is None:
        return

    existing_debounce = _debounce_timers.get(channel_id)
    if existing_debounce is not None:
        existing_debounce.cancel()

    handle = _main_loop.call_later(
        CHANNEL_CLASSIFIER_DEBOUNCE_SECONDS,
        lambda: asyncio.ensure_future(_process_channel_batch(channel_id)),
    )
    _debounce_timers[channel_id] = handle

    if channel_id not in _max_wait_timers:
        max_wait_handle = _main_loop.call_later(
            CHANNEL_CLASSIFIER_MAX_WAIT_SECONDS,
            lambda: asyncio.ensure_future(_process_channel_batch(channel_id, force=True)),
        )
        _max_wait_timers[channel_id] = max_wait_handle

def _schedule_reschedule_timers(channel_id: str) -> None:
    if _main_loop is None:
        return

    existing_debounce = _debounce_timers.get(channel_id)
    if existing_debounce is not None:
        existing_debounce.cancel()

    handle = _main_loop.call_later(
        LOCK_RETRY_DEBOUNCE_SECONDS,
        lambda: asyncio.ensure_future(_process_channel_batch(channel_id)),
    )
    _debounce_timers[channel_id] = handle

    if channel_id not in _max_wait_timers:
        max_wait_seconds = min(
            CHANNEL_CLASSIFIER_MAX_WAIT_SECONDS,
            int(LOCK_RETRY_DEBOUNCE_SECONDS * 5),
        )
        max_wait_handle = _main_loop.call_later(
            max_wait_seconds,
            lambda: asyncio.ensure_future(_process_channel_batch(channel_id, force=True)),
        )
        _max_wait_timers[channel_id] = max_wait_handle

def _cancel_timers(channel_id: str) -> None:
    debounce = _debounce_timers.pop(channel_id, None)
    if debounce is not None:
        debounce.cancel()
    max_wait = _max_wait_timers.pop(channel_id, None)
    if max_wait is not None:
        max_wait.cancel()

async def _process_channel_batch(channel_id: str, force: bool = False) -> None:
    _cancel_timers(channel_id)

    store = get_execution_store()
    owner = get_instance_identity()
    expires_at = (
        datetime.now(timezone.utc) + timedelta(seconds=CLASSIFIER_LOCK_DURATION_SECONDS)
    ).isoformat()

    try:
        state = await store.get_channel_state(channel_id)
        if state and state.max_wait_until:
            try:
                max_wait_dt = datetime.fromisoformat(state.max_wait_until)
                if datetime.now(timezone.utc) >= max_wait_dt:
                    force = True
                elif not force and channel_id not in _max_wait_timers:
                    remaining = (max_wait_dt - datetime.now(timezone.utc)).total_seconds()
                    if remaining > 0:
                        max_wait_handle = _main_loop.call_later(
                            remaining,
                            lambda: asyncio.ensure_future(
                                _process_channel_batch(channel_id, force=True)
                            ),
                        )
                        _max_wait_timers[channel_id] = max_wait_handle
            except (ValueError, TypeError):
                pass
        if state and state.status == "classifying" and not force:
            logger.info(
                f"Channel {channel_id} is classifying, "
                f"skipping batch (dirty events will trigger re-pass)"
            )
            return
    except Exception as e:
        logger.debug(f"State check before lock acquisition failed for {channel_id}: {e}")

    try:
        acquired = await store.acquire_classifier_lock(channel_id, owner, expires_at)
    except Exception as e:
        logger.error(f"Lock acquisition error for channel {channel_id}: {e}")
        _schedule_reschedule_timers(channel_id)
        return

    if not acquired:
        logger.info(f"Classifier lock not acquired for channel {channel_id}, rescheduling")
        _schedule_reschedule_timers(channel_id)
        return

    _active_classifier_owners[channel_id] = owner
    batch_dispatch_args: Optional[Dict[str, Any]] = None
    processed_event_at: Optional[str] = None
    try:
        locked_state = await store.get_channel_state(channel_id)
        processed_event_at = locked_state.latest_observed_event_at if locked_state else None
        batch_dispatch_args = await _collect_batch_dispatch(channel_id)
    except Exception as e:
        logger.error(f"Batch collection failed for channel {channel_id}: {e}")
    finally:
        _active_classifier_owners.pop(channel_id, None)
        try:
            await store.finish_classifier_pass(
                channel_id,
                owner,
                processed_event_at=processed_event_at,
                debounce_seconds=CHANNEL_CLASSIFIER_DEBOUNCE_SECONDS,
            )
        except Exception as e:
            logger.warning(f"Failed to finish classifier pass for {channel_id}: {e}")

        try:
            state = await store.get_channel_state(channel_id)
            if state and state.status == "debouncing":
                _schedule_timers(channel_id)
            elif state and (state.dirty or state.pending):
                _schedule_timers(channel_id)
        except Exception:
            pass

    if batch_dispatch_args is not None:
        asyncio.ensure_future(_dispatch_batch_decisions(batch_dispatch_args))

async def _collect_batch_dispatch(channel_id: str) -> Optional[Dict[str, Any]]:
    from channels.listeners.discord_listener import _active_clients
    from channels.status import StatusType, send_status_direct
    store = get_execution_store()
    state = await store.get_channel_state(channel_id)
    meta = _channel_meta.get(channel_id, {})
    webhook_id = meta.get("webhook_id", "")
    conversation_id = meta.get("conversation_id", channel_id)
    guild_id = meta.get("guild_id", "")
    discord_loop = meta.get("discord_loop")
    client = _active_clients.get(webhook_id)
    if not client:
        logger.error(f"No active Discord client for webhook_id={webhook_id}, channel={channel_id}")
        return None
    channel_ref = client.get_channel(int(channel_id))
    if not channel_ref:
        logger.error(f"Could not resolve channel {channel_id} from Discord client")
        return None
    bot_id = None
    if client.user:
        bot_id = client.user.id
    from channels.dispatcher import _fetch_discord_history
    history_messages = await _fetch_discord_history(channel_ref, discord_loop)
    if history_messages:
        await _reconcile_history(channel_id, guild_id, history_messages)
    last_classified_id = state.last_classified_message_id if state else None
    last_classified_at = state.last_classified_at if state else None
    new_messages = _derive_batch(
        history_messages, last_classified_id,
        last_classified_at=last_classified_at, bot_id=bot_id,
    )
    if not new_messages:
        logger.info(f"No new messages for channel {channel_id} after cursor {last_classified_id}")
        newest_user_id = _newest_user_message_id(history_messages, bot_id=bot_id)
        if newest_user_id:
            await store.update_cursors(channel_id, newest_user_id)
        return None
    candidate_ids = [str(msg.id) for msg in new_messages]
    session_dir = _resolve_session_dir(channel_id, guild_id)
    active_tasks = await store.get_active_tasks_for_channel(channel_id)
    tasks_summary = ""
    if active_tasks:
        tasks_summary = chr(10).join(
            f"- task_id={t.task_id} status={t.status} specialist={t.selected_specialist or 'unknown'}"
            for t in active_tasks
        )
    await send_status_direct(
        StatusType.CLASSIFICATION_STARTED,
        "🧠 Classifying",
        channel_ref=channel_ref,
        discord_loop=discord_loop,
        fields={"messages": str(len(new_messages)), "active tasks": str(len(active_tasks))},
    )
    from flow.context import build_runtime_context
    runtime_context = build_runtime_context(
        messages=[{"role": "user", "content": f"Batch classification for {len(new_messages)} new messages"}],
        context_id=channel_id, cache_key=conversation_id, session_dir=session_dir,
    )
    from flow.batch_classifier import run_batch_classification, BatchClassificationError
    try:
        classification = await run_batch_classification(
            session_dir=session_dir, channel_id=channel_id,
            candidate_source_message_ids=candidate_ids,
            runtime_context=runtime_context, active_tasks_summary=tasks_summary,
            bot_id=str(bot_id) if bot_id else None,
        )
    except (BatchClassificationError, Exception) as e:
        logger.error(f"Batch classification failed for channel {channel_id}: {e}, will fallback after lock release")
        await send_status_direct(
            StatusType.CLASSIFICATION_FAILED,
            "❌ Classification failed",
            channel_ref=channel_ref,
            discord_loop=discord_loop,
            description=str(e)[:200],
        )
        return {
            "channel_id": channel_id, "conversation_id": conversation_id,
            "webhook_id": webhook_id, "channel_ref": channel_ref,
            "discord_loop": discord_loop, "new_messages": new_messages,
            "classification": None,
            "newest_user_id": _newest_user_message_id(history_messages, bot_id=bot_id),
        }
    logger.info(f"Batch classification completed for channel {channel_id}: {len(classification.decisions)} decisions")
    decision_lines = []
    for d in classification.decisions:
        line = f"{d.action}/{d.kind}"
        inline = d.social_response_text or d.response_text
        if inline:
            line += f": {str(inline)[:80]}"
        elif d.reason:
            line += f" ({d.reason[:80]})"
        decision_lines.append(line)
    decision_summary = chr(10).join(decision_lines) or "none"
    fields: dict[str, str] = {"decisions": str(len(classification.decisions))}
    if classification.batch_summary:
        fields["summary"] = classification.batch_summary[:200]
    fields["actions"] = decision_summary[:800]
    await send_status_direct(
        StatusType.CLASSIFICATION_COMPLETED,
        "✅ Classified",
        channel_ref=channel_ref,
        discord_loop=discord_loop,
        fields=fields,
    )
    return {
        "channel_id": channel_id, "conversation_id": conversation_id,
        "webhook_id": webhook_id, "channel_ref": channel_ref,
        "discord_loop": discord_loop, "new_messages": new_messages,
        "classification": classification,
        "newest_user_id": _newest_user_message_id(history_messages, bot_id=bot_id),
    }

async def _dispatch_batch_decisions(args: Dict[str, Any]) -> None:
    store = get_execution_store()
    channel_id = args["channel_id"]
    conversation_id = args["conversation_id"]
    webhook_id = args["webhook_id"]
    channel_ref = args["channel_ref"]
    discord_loop = args["discord_loop"]
    new_messages = args["new_messages"]
    classification = args["classification"]
    newest_user_id = args["newest_user_id"]

    if classification is None:
        logger.error(f"Batch classification produced no result for {channel_id}, routing through outbox fallback")
        from channels.decision_applier import _enqueue_message
        from channels.outbound_queue import schedule_drain
        message_dicts = [
            _discord_message_to_dict(msg, conversation_id, webhook_id, discord_loop)
            for msg in new_messages
        ]
        try:
            response_text = await _run_fallback_batch(
                message_dicts=message_dicts,
                conversation_id=conversation_id,
                channel_ref=channel_ref,
                discord_loop=discord_loop,
            )
            if response_text:
                await _enqueue_message(
                    store=store,
                    channel_id=channel_id,
                    conversation_id=conversation_id,
                    msg_type="social_response",
                    content=response_text,
                    priority=5,
                )
                schedule_drain(channel_id)
        except Exception as e:
            logger.error(f"Fallback routing failed for channel {channel_id}: {e}")
    else:
        from channels.context import set_platform_context, clear_platform_context
        from channels.decision_applier import apply_batch_decisions
        set_platform_context("discord", channel_ref, discord_loop)
        try:
            results = await apply_batch_decisions(
                decisions=classification.decisions,
                batch_id=classification.batch_id,
                channel_id=channel_id,
                conversation_id=conversation_id,
                channel_ref=channel_ref,
                discord_loop=discord_loop,
            )
            logger.info(
                f"Decision applier results for channel {channel_id}: "
                f"{sum(1 for r in results if r)}/{len(results)} succeeded"
            )
        except Exception as e:
            logger.error(f"Decision applier failed for channel {channel_id}: {e}")
        finally:
            clear_platform_context()

    if newest_user_id:
        try:
            await store.update_cursors(channel_id, newest_user_id)
        except Exception as e:
            logger.warning(f"Cursor update failed for channel {channel_id}: {e}")



async def _run_fallback_batch(
    message_dicts: List[Any],
    conversation_id: str,
    channel_ref: Any,
    discord_loop: Any,
) -> Optional[str]:
    from channels.translators.discord_translator import translate_discord_batch
    from channels.dispatcher import _fetch_discord_history
    history_messages = await _fetch_discord_history(channel_ref, discord_loop)
    request_data = translate_discord_batch(
        message_dicts,
        conversation_id,
        history_messages=history_messages,
    )
    request_data.pop("_pending_uploads", None)
    try:
        from main import app
        from api.completions import process_chat_completion_internal
        from storage.factory import get_webhook_store
        http_client = app.state.http_client
        webhook = None
        try:
            store = get_webhook_store()
            for r in store.list_active():
                if r.conversation_id == conversation_id:
                    webhook = r
                    break
        except Exception:
            pass
        response_text, _attachments = await process_chat_completion_internal(
            request_data=request_data,
            http_client=http_client,
            webhook=webhook,
        )
        return response_text
    except Exception as exc:
        logger.error("Fallback pipeline failed for %s: %s", conversation_id, exc)
        return None

async def _reconcile_history(
    channel_id: str, guild_id: str, history_messages: List[Any]
) -> None:
    from flow.history import write_history
    session_dir = _resolve_session_dir(channel_id, guild_id)
    history_events = []
    try:
        from channels.listeners.discord_listener import get_discord_client
        _client = get_discord_client()
        bot_id = _client.user.id if _client and _client.user else None
    except Exception:
        bot_id = None
    for msg in reversed(history_messages):
        content = msg.clean_content
        if not content:
            continue
        if bot_id and msg.author.id == bot_id:
            role = "assistant"
            author = ""
        else:
            role = "user"
            author = msg.author.display_name if msg.author else "unknown"
            content = f"[{author}]: {content}"
        history_events.append({
            "id": str(msg.id), "role": role, "author": author,
            "content": content,
            "created_at": msg.created_at.isoformat() if msg.created_at else "",
            "edited_at": msg.edited_at.isoformat() if getattr(msg, "edited_at", None) else "",
            "source": "discord_history_reconcile",
        })
    if history_events:
        write_history(session_dir, messages=[], history_events=history_events)

def _resolve_session_dir(channel_id: str, guild_id: str) -> Any:
    from flow.session_dirs import safe_segment
    from pathlib import Path
    guild_seg = safe_segment(guild_id, "guild")
    channel_seg = safe_segment(channel_id, "channel")
    path = Path(OPENCODE_WORKSPACE_BASE) / guild_seg / channel_seg
    path.mkdir(parents=True, exist_ok=True)
    return path

def _newest_user_message_id(
    history_messages: List[Any], bot_id: Optional[int] = None,
) -> Optional[str]:
    if not history_messages:
        return None
    for msg in sorted(history_messages, key=lambda m: int(m.id), reverse=True):
        if _is_bot_message(msg, bot_id):
            continue
        return str(msg.id)
    return None

def _derive_batch(
    history_messages: List[Any],
    last_classified_id: Optional[str],
    last_classified_at: Optional[str] = None,
    bot_id: Optional[int] = None,
) -> List[Any]:
    if not history_messages:
        return []
    if not last_classified_id:
        non_bot = [
            msg for msg in sorted(history_messages, key=lambda m: int(m.id))
            if not _is_bot_message(msg, bot_id)
        ]
        return non_bot
    cursor_int = int(last_classified_id)
    new_msgs = [
        msg for msg in history_messages
        if int(msg.id) > cursor_int and not _is_bot_message(msg, bot_id)
    ]
    if last_classified_at:
        try:
            classified_dt = datetime.fromisoformat(last_classified_at)
            for msg in history_messages:
                if _is_bot_message(msg, bot_id):
                    continue
                if int(msg.id) <= cursor_int:
                    edited_at = getattr(msg, "edited_at", None)
                    if edited_at and edited_at > classified_dt and msg not in new_msgs:
                        new_msgs.append(msg)
        except (ValueError, TypeError):
            pass
    new_msgs.sort(key=lambda m: int(m.id))
    return new_msgs

def _is_bot_message(msg: Any, bot_id: Optional[int] = None) -> bool:
    if bot_id and msg.author.id == bot_id:
        return True
    if getattr(msg.author, "bot", False):
        return True
    return False

def _discord_message_to_dict(
    msg: Any, conversation_id: str, webhook_id: str, discord_loop: Any,
) -> Dict[str, Any]:
    return {
        "platform": "discord",
        "webhook_id": webhook_id,
        "conversation_id": conversation_id,
        "message_id": str(msg.id),
        "guild_id": str(msg.guild.id) if msg.guild else "",
        "channel_id": str(msg.channel.id) if msg.channel else "",
        "author": msg.author.display_name if msg.author else "unknown",
        "author_id": str(msg.author.id) if msg.author else "",
        "content": msg.clean_content,
        "attachments": [{
            "filename": att.filename, "url": att.url,
            "content_type": att.content_type or "application/octet-stream",
        } for att in msg.attachments],
        "channel_ref": msg.channel,
        "discord_loop": discord_loop,
        "timestamp": msg.created_at.isoformat() if msg.created_at else "",
        "edited_at": msg.edited_at.isoformat() if getattr(msg, "edited_at", None) else "",
        "reply_to_message_id": (
            str(msg.reference.message_id)
            if msg.reference and getattr(msg.reference, "message_id", None)
            else None
        ),
        "event_type": "message_create",
    }
