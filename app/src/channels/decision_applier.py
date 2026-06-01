"""Decision Applier — Phase 4 of the Discord channel orchestration plan.

Translates ClassifierDecision records into concrete side effects: outbound
messages, implementation task CRUD, and route execution.  Every action is
idempotent via DynamoDB conditional writes and intent-status state machines
defined in ExecutionStore.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from channels.execution_models import (
    ClassifierDecision,
    DiscordOutboundMessage,
    IntentRecord,
    ImplementationTask,
)
from channels.execution_store import get_execution_store

logger = logging.getLogger(__name__)

_ACTION_DISPATCH = {
    "social_response": "_apply_social_response",
    "ask_clarifying_target": "_apply_clarifying_question",
    "ignore": "_apply_ignore",
    "start_new_task": "_apply_start_new_task",
    "append_to_active_implementation": "_apply_append_to_active",
    "queue_on_active_implementation": "_apply_queue_on_active",
    "await_instruction_for_active_implementation": "_apply_await_instruction",
    "cancel_active_implementation": "_apply_cancel_implementation",
    "pivot_active_implementation": "_apply_pivot_implementation",
}


async def apply_decision(
    decision: ClassifierDecision,
    batch_id: str,
    channel_id: str,
    conversation_id: str,
    channel_ref: Any = None,
    discord_loop: Any = None,
) -> bool:
    store = get_execution_store()
    intent = await store.get_intent_record(batch_id, decision.intent_id)
    if intent is None:
        logger.error(
            "Intent record not found for intent_id=%s batch_id=%s",
            decision.intent_id,
            batch_id,
        )
        return False
    if intent.status != "pending":
        return True
    transitioned = await store.update_intent_record_status(
        batch_id=batch_id,
        intent_id=decision.intent_id,
        from_status="pending",
        to_status="applying",
    )
    if not transitioned:
        return True
    method_name = _ACTION_DISPATCH.get(decision.action)
    if method_name is None:
        logger.error(
            "Unknown decision action %s for intent %s",
            decision.action,
            decision.intent_id,
        )
        await store.update_intent_record_status(
            batch_id=batch_id,
            intent_id=decision.intent_id,
            from_status="applying",
            to_status="failed",
            error=f"unknown_action:{decision.action}",
        )
        return False
    handler = globals().get(method_name)
    if handler is None:
        logger.error(
            "Handler %s not found for action %s",
            method_name,
            decision.action,
        )
        await store.update_intent_record_status(
            batch_id=batch_id,
            intent_id=decision.intent_id,
            from_status="applying",
            to_status="failed",
            error=f"handler_missing:{method_name}",
        )
        return False
    _HANDLER_OWNS_TERMINAL = {"_apply_start_new_task", "_apply_ignore"}
    handler_owns_terminal = method_name in _HANDLER_OWNS_TERMINAL
    try:
        result = await handler(
            decision=decision,
            intent=intent,
            store=store,
            channel_id=channel_id,
            conversation_id=conversation_id,
            channel_ref=channel_ref,
            discord_loop=discord_loop,
        )
    except Exception:
        logger.exception(
            "Decision apply failed for intent %s action %s",
            decision.intent_id,
            decision.action,
        )
        await store.update_intent_record_status(
            batch_id=batch_id,
            intent_id=decision.intent_id,
            from_status="applying",
            to_status="failed",
            error="apply_exception",
        )
        return False
    if not handler_owns_terminal:
        if result:
            await store.update_intent_record_status(
                batch_id=batch_id,
                intent_id=decision.intent_id,
                from_status="applying",
                to_status="completed",
            )
        else:
            await store.update_intent_record_status(
                batch_id=batch_id,
                intent_id=decision.intent_id,
                from_status="applying",
                to_status="failed",
            )
    return result


async def apply_batch_decisions(
    decisions: List[ClassifierDecision],
    batch_id: str,
    channel_id: str,
    conversation_id: str,
    channel_ref: Any = None,
    discord_loop: Any = None,
) -> List[bool]:
    results: List[bool] = []
    for decision in decisions:
        result = await apply_decision(
            decision=decision,
            batch_id=batch_id,
            channel_id=channel_id,
            conversation_id=conversation_id,
            channel_ref=channel_ref,
            discord_loop=discord_loop,
        )
        results.append(result)
    return results


async def _enqueue_message(
    store: Any,
    channel_id: str,
    conversation_id: str,
    msg_type: str,
    content: str,
    priority: int = 5,
    task_id: Optional[str] = None,
    intent_id: Optional[str] = None,
    batch_id: Optional[str] = None,
    reply_to_message_id: Optional[str] = None,
    attachments: Optional[list] = None,
    channel_ref: Any = None,
    discord_loop: Any = None,
) -> bool:
    outbound_id = str(uuid.uuid4())
    idempotency_key = f"{batch_id or 'nb'}:{intent_id or 'ni'}:{msg_type}:{outbound_id}"
    now = datetime.now(timezone.utc).isoformat()
    msg = DiscordOutboundMessage(
        outbound_id=outbound_id,
        channel_id=channel_id,
        conversation_id=conversation_id,
        task_id=task_id,
        intent_id=intent_id,
        batch_id=batch_id,
        type=msg_type,
        priority=priority,
        content=content,
        attachments=attachments or [],
        reply_to_message_id=reply_to_message_id,
        status="queued",
        created_at=now,
        updated_at=now,
        idempotency_key=idempotency_key,
    )
    stored = await store.put_outbound_message(msg)
    if channel_ref is not None and discord_loop is not None:
        _deliver_outbound_now(msg, channel_ref, discord_loop)
    return stored


def _deliver_outbound_now(
    msg: DiscordOutboundMessage,
    channel_ref: Any,
    discord_loop: Any,
) -> None:
    from channels.chunker import chunk_response
    from channels.delivery import deliver_to_channel
    try:
        chunks = chunk_response(msg.content)
        import asyncio
        asyncio.ensure_future(
            deliver_to_channel(
                platform="discord",
                channel_ref=channel_ref,
                chunks=chunks,
                attachments=msg.attachments,
                discord_loop=discord_loop,
            )
        )
    except Exception:
        logger.exception(
            "Immediate delivery failed for outbound %s",
            msg.outbound_id,
        )


async def _apply_social_response(
    decision: ClassifierDecision,
    intent: IntentRecord,
    store: Any,
    **kwargs: Any,
) -> bool:
    content = decision.social_response_text or decision.response_text
    if content:
        text = content
    else:
        from flow.batch_classifier import decision_to_ifplan
        from flow.runner import execute_route
        from flow.context import build_runtime_context
        from channels.channel_coordinator import _resolve_session_dir

        channel_id = kwargs["channel_id"]
        conversation_id = kwargs["conversation_id"]
        channel_ref = kwargs.get("channel_ref")
        plan = decision_to_ifplan(decision)
        guild_id = str(channel_ref.guild.id) if channel_ref and hasattr(channel_ref, "guild") else "unknown"
        session_dir = _resolve_session_dir(channel_id, guild_id)
        http_client = None
        try:
            from main import app
            http_client = getattr(app.state, "http_client", None)
        except Exception:
            pass
        runtime_context = build_runtime_context(
            messages=[],
            context_id=conversation_id,
            cache_key=conversation_id,
            session_dir=Path(str(session_dir)),
        )
        flow_result = await execute_route(
            plan=plan,
            session_dir=Path(str(session_dir)),
            runtime_context=runtime_context,
            http_client=http_client,
        )
        text = flow_result.content
    reply_to = decision.source_message_ids[0] if decision.source_message_ids else None
    return await _enqueue_message(
        store=store,
        channel_id=kwargs["channel_id"],
        conversation_id=kwargs["conversation_id"],
        msg_type="social_response",
        content=text,
        intent_id=decision.intent_id,
        batch_id=intent.batch_id,
        reply_to_message_id=reply_to,
        channel_ref=kwargs.get("channel_ref"),
        discord_loop=kwargs.get("discord_loop"),
    )


async def _apply_clarifying_question(
    decision: ClassifierDecision,
    intent: IntentRecord,
    store: Any,
    **kwargs: Any,
) -> bool:
    content = decision.response_text or decision.social_response_text or decision.reason
    reply_to = decision.source_message_ids[0] if decision.source_message_ids else None
    return await _enqueue_message(
        store=store,
        channel_id=kwargs["channel_id"],
        conversation_id=kwargs["conversation_id"],
        msg_type="clarifying_question",
        content=content or "",
        priority=3,
        intent_id=decision.intent_id,
        batch_id=intent.batch_id,
        reply_to_message_id=reply_to,
        channel_ref=kwargs.get("channel_ref"),
        discord_loop=kwargs.get("discord_loop"),
    )


async def _apply_ignore(
    decision: ClassifierDecision,
    intent: IntentRecord,
    store: Any,
    **kwargs: Any,
) -> bool:
    return await store.update_intent_record_status(
        batch_id=intent.batch_id,
        intent_id=decision.intent_id,
        from_status="applying",
        to_status="skipped",
    )


async def _apply_start_new_task(
    decision: ClassifierDecision,
    intent: IntentRecord,
    store: Any,
    **kwargs: Any,
) -> bool:
    channel_id = kwargs["channel_id"]
    conversation_id = kwargs["conversation_id"]
    channel_ref = kwargs.get("channel_ref")
    discord_loop = kwargs.get("discord_loop")
    now = datetime.now(timezone.utc).isoformat()
    task_id = str(uuid.uuid4())
    root_msg_id = decision.source_message_ids[0] if decision.source_message_ids else ""
    task = ImplementationTask(
        task_id=task_id,
        channel_id=channel_id,
        conversation_id=conversation_id,
        status="implementing",
        root_discord_message_id=root_msg_id,
        related_discord_message_ids=decision.source_message_ids[1:] if len(decision.source_message_ids) > 1 else [],
        selected_specialist=decision.selected_specialist,
        selected_model=decision.selected_model,
        topic=decision.planner_intent or {},
        created_at=now,
        updated_at=now,
    )
    created = await store.put_implementation_task(task)
    if not created:
        logger.info("Implementation task %s already exists, skipping", task_id)
        await store.update_intent_record_status(
            batch_id=intent.batch_id,
            intent_id=intent.intent_id,
            from_status="applying",
            to_status="completed",
        )
        return True
    await store.update_intent_record_status(
        batch_id=intent.batch_id,
        intent_id=intent.intent_id,
        from_status="applying",
        to_status="running",
        target_task_id=task_id,
    )
    await _enqueue_message(
        store=store,
        channel_id=channel_id,
        conversation_id=conversation_id,
        msg_type="task_started",
        content=f"Task started: {task_id}",
        priority=5,
        task_id=task_id,
        intent_id=decision.intent_id,
        batch_id=intent.batch_id,
        reply_to_message_id=root_msg_id or None,
        channel_ref=channel_ref,
        discord_loop=discord_loop,
    )
    import asyncio as _asyncio
    _asyncio.ensure_future(_run_task_execution(
        decision=decision,
        intent_id=intent.intent_id,
        batch_id=intent.batch_id,
        task_id=task_id,
        channel_id=channel_id,
        conversation_id=conversation_id,
        channel_ref=channel_ref,
        discord_loop=discord_loop,
        store=store,
    ))
    return True


async def _run_task_execution(
    decision: ClassifierDecision,
    intent_id: str,
    batch_id: str,
    task_id: str,
    channel_id: str,
    conversation_id: str,
    channel_ref: Any,
    discord_loop: Any,
    store: Any,
) -> None:
    from flow.batch_classifier import decision_to_ifplan
    from flow.runner import execute_route
    from flow.context import build_runtime_context
    from channels.channel_coordinator import _resolve_session_dir

    plan = decision_to_ifplan(decision)
    guild_id = str(channel_ref.guild.id) if channel_ref and hasattr(channel_ref, "guild") else "unknown"
    session_dir = _resolve_session_dir(channel_id, guild_id)
    http_client = None
    try:
        from main import app
        http_client = getattr(app.state, "http_client", None)
    except Exception:
        pass
    runtime_context = build_runtime_context(
        messages=[],
        context_id=conversation_id,
        cache_key=conversation_id,
        session_dir=Path(str(session_dir)),
    )
    try:
        flow_result = await execute_route(
            plan=plan,
            session_dir=Path(str(session_dir)),
            runtime_context=runtime_context,
            http_client=http_client,
        )
        await store.update_implementation_task(
            channel_id=channel_id,
            task_id=task_id,
            from_status="implementing",
            to_status="completed",
        )
        result_attachments = [
            {"filename": ref.filename, "url": ref.url, "local_path": ref.local_path}
            for ref in flow_result.file_refs
        ] if flow_result.file_refs else []
        await _enqueue_message(
            store=store,
            channel_id=channel_id,
            conversation_id=conversation_id,
            msg_type="task_completed",
            content=flow_result.content,
            priority=5,
            task_id=task_id,
            intent_id=intent_id,
            batch_id=batch_id,
            attachments=result_attachments,
            channel_ref=channel_ref,
            discord_loop=discord_loop,
        )
        await store.update_intent_record_status(
            batch_id=batch_id,
            intent_id=intent_id,
            from_status="running",
            to_status="completed",
        )
    except Exception:
        logger.exception("Route execution failed for task %s", task_id)
        await store.update_implementation_task(
            channel_id=channel_id,
            task_id=task_id,
            from_status="implementing",
            to_status="failed",
        )
        await _enqueue_message(
            store=store,
            channel_id=channel_id,
            conversation_id=conversation_id,
            msg_type="task_failed",
            content=f"Task failed: {task_id}",
            priority=5,
            task_id=task_id,
            intent_id=intent_id,
            batch_id=batch_id,
            channel_ref=channel_ref,
            discord_loop=discord_loop,
        )
        await store.update_intent_record_status(
            batch_id=batch_id,
            intent_id=intent_id,
            from_status="running",
            to_status="failed",
            error="execution_failed",
        )


async def _apply_append_to_active(
    decision: ClassifierDecision,
    intent: IntentRecord,
    store: Any,
    **kwargs: Any,
) -> bool:
    channel_id = kwargs["channel_id"]
    if not decision.target_task_id:
        logger.error("append_to_active requires target_task_id for intent %s", decision.intent_id)
        return False
    task = await store.get_implementation_task(channel_id, decision.target_task_id)
    if task is None:
        logger.error("Task %s not found for append_to_active", decision.target_task_id)
        return False
    new_refs = [
        {
            "message_id": mid,
            "reason": "append_to_active",
            "intent_id": decision.intent_id,
        }
        for mid in decision.source_message_ids
    ]
    return await store.append_task_queued_refs(
        channel_id=channel_id,
        task_id=decision.target_task_id,
        refs=new_refs,
        expected_version=task.version,
    )


async def _apply_queue_on_active(
    decision: ClassifierDecision,
    intent: IntentRecord,
    store: Any,
    **kwargs: Any,
) -> bool:
    channel_id = kwargs["channel_id"]
    if not decision.target_task_id:
        logger.error("queue_on_active requires target_task_id for intent %s", decision.intent_id)
        return False
    task = await store.get_implementation_task(channel_id, decision.target_task_id)
    if task is None:
        logger.error("Task %s not found for queue_on_active", decision.target_task_id)
        return False
    new_refs = [
        {
            "message_id": mid,
            "reason": "queued",
            "intent_id": decision.intent_id,
        }
        for mid in decision.source_message_ids
    ]
    return await store.append_task_queued_refs(
        channel_id=channel_id,
        task_id=decision.target_task_id,
        refs=new_refs,
        expected_version=task.version,
    )


async def _apply_await_instruction(
    decision: ClassifierDecision,
    intent: IntentRecord,
    store: Any,
    **kwargs: Any,
) -> bool:
    channel_id = kwargs["channel_id"]
    conversation_id = kwargs["conversation_id"]
    channel_ref = kwargs.get("channel_ref")
    discord_loop = kwargs.get("discord_loop")
    if not decision.target_task_id:
        logger.error("await_instruction requires target_task_id for intent %s", decision.intent_id)
        return False
    task = await store.get_implementation_task(channel_id, decision.target_task_id)
    if task is None:
        logger.error("Task %s not found for await_instruction", decision.target_task_id)
        return False
    conflict = decision.conflict or {}
    updated = await store.update_implementation_task(
        channel_id=channel_id,
        task_id=decision.target_task_id,
        from_status=task.status,
        to_status="awaiting_instruction",
        pending_conflict=conflict,
    )
    if not updated:
        return False
    conflict_summary = conflict.get("summary", "") if conflict else ""
    conflict_type = conflict.get("type", "unknown") if conflict else "unknown"
    content = f"Task {decision.target_task_id} awaiting instruction ({conflict_type})"
    if conflict_summary:
        content += f": {conflict_summary}"
    return await _enqueue_message(
        store=store,
        channel_id=channel_id,
        conversation_id=conversation_id,
        msg_type="await_instruction",
        content=content,
        priority=4,
        task_id=decision.target_task_id,
        intent_id=decision.intent_id,
        batch_id=intent.batch_id,
        channel_ref=channel_ref,
        discord_loop=discord_loop,
    )


async def _apply_cancel_implementation(
    decision: ClassifierDecision,
    intent: IntentRecord,
    store: Any,
    **kwargs: Any,
) -> bool:
    channel_id = kwargs["channel_id"]
    conversation_id = kwargs["conversation_id"]
    channel_ref = kwargs.get("channel_ref")
    discord_loop = kwargs.get("discord_loop")
    if not decision.target_task_id:
        logger.error("cancel_implementation requires target_task_id for intent %s", decision.intent_id)
        return False
    task = await store.get_implementation_task(channel_id, decision.target_task_id)
    if task is None:
        logger.error("Task %s not found for cancel_implementation", decision.target_task_id)
        return False
    updated = await store.update_implementation_task(
        channel_id=channel_id,
        task_id=decision.target_task_id,
        from_status=task.status,
        to_status="cancel_requested",
    )
    if not updated:
        return False
    return await _enqueue_message(
        store=store,
        channel_id=channel_id,
        conversation_id=conversation_id,
        msg_type="cancel_confirmation",
        content=f"Cancel requested for task {decision.target_task_id}",
        priority=4,
        task_id=decision.target_task_id,
        intent_id=decision.intent_id,
        batch_id=intent.batch_id,
        channel_ref=channel_ref,
        discord_loop=discord_loop,
    )


async def _apply_pivot_implementation(
    decision: ClassifierDecision,
    intent: IntentRecord,
    store: Any,
    **kwargs: Any,
) -> bool:
    channel_id = kwargs["channel_id"]
    conversation_id = kwargs["conversation_id"]
    channel_ref = kwargs.get("channel_ref")
    discord_loop = kwargs.get("discord_loop")
    if not decision.target_task_id:
        logger.error("pivot_implementation requires target_task_id for intent %s", decision.intent_id)
        return False
    task = await store.get_implementation_task(channel_id, decision.target_task_id)
    if task is None:
        logger.error("Task %s not found for pivot_implementation", decision.target_task_id)
        return False
    merged_topic = dict(task.topic)
    if decision.topic_update:
        merged_topic.update(decision.topic_update)
    updated = await store.update_implementation_task(
        channel_id=channel_id,
        task_id=decision.target_task_id,
        from_status=task.status,
        to_status="pivot_requested",
        topic=merged_topic,
    )
    if not updated:
        return False
    return await _enqueue_message(
        store=store,
        channel_id=channel_id,
        conversation_id=conversation_id,
        msg_type="task_update",
        content=f"Task {decision.target_task_id} pivot requested with updated topic",
        priority=4,
        task_id=decision.target_task_id,
        intent_id=decision.intent_id,
        batch_id=intent.batch_id,
        channel_ref=channel_ref,
        discord_loop=discord_loop,
    )
