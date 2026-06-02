










from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from channels.execution_models import ImplementationTask, OpenCodeRunRecord
from channels.execution_store import get_execution_store
from config import OPENCODE_CANCEL_POLL_INTERVAL_SECONDS

logger = logging.getLogger(__name__)

def _per_run_filenames(task_id: str, run_id: str) -> dict[str, str]:
    return {
        "response_filename": f"response.task.{task_id}.run.{run_id}.md",
        "review_filename": f"review.task.{task_id}.run.{run_id}.md",
        "status_filename": f"status.task.{task_id}.run.{run_id}.log",
    }

async def _poll_task_control(
    task_id: str,
    channel_id: str,
    run_id: str,
    cancel_event: asyncio.Event,
) -> None:
    store = get_execution_store()
    while not cancel_event.is_set():
        await asyncio.sleep(OPENCODE_CANCEL_POLL_INTERVAL_SECONDS)
        if cancel_event.is_set():
            return
        try:
            task = await store.get_implementation_task(channel_id, task_id)
            if task is None:
                continue
            if task.status in ("cancel_requested", "pivot_requested", "awaiting_instruction"):
                logger.info(
                    "Task control change detected for task %s: status=%s, setting cancel event for run %s",
                    task_id,
                    task.status,
                    run_id,
                )
                cancel_event.set()
                return
        except Exception as exc:
            logger.debug("Poll task control failed for %s: %s", task_id, exc)

async def run_task_worker(
    *,
    task: ImplementationTask,
    decision: Any,
    batch_id: str,
    intent_id: str,
    channel_ref: Any,
    discord_loop: Any,
) -> None:
    from channels.context import set_platform_context, clear_platform_context
    from channels.decision_applier import _enqueue_message
    from flow.batch_classifier import decision_to_ifplan
    from flow.context import build_runtime_context
    from flow.runner import execute_route
    from flow.opencode import RunCancelledError
    from channels.channel_coordinator import _resolve_session_dir

    channel_id = task.channel_id
    conversation_id = task.conversation_id
    task_id = task.task_id
    run_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    filenames = _per_run_filenames(task_id, run_id)
    response_filename = filenames["response_filename"]
    review_filename = filenames["review_filename"]
    status_filename = filenames["status_filename"]

    config_path = None
    session_marker_path = None
    cancel_event = asyncio.Event()
    poll_task = None

    set_platform_context("discord", channel_ref, discord_loop)
    store = get_execution_store()

    try:
        guild_id = str(channel_ref.guild.id) if channel_ref and hasattr(channel_ref, "guild") else "unknown"
        session_dir = _resolve_session_dir(channel_id, guild_id)
        state_dir = session_dir / ".if"
        state_dir.mkdir(parents=True, exist_ok=True)
        config_path = state_dir / f"opencode.run.{run_id}.json"
        agent = task.selected_specialist or "general"
        session_marker_path = state_dir / f"opencode-{agent}.run.{run_id}.session"

        run_record = OpenCodeRunRecord(
            run_id=run_id,
            channel_id=channel_id,
            task_id=task_id,
            batch_id=batch_id,
            kind="implementer",
            agent=agent,
            model=task.selected_model or "",
            status="running",
            started_at=now,
            completed_at=None,
            title=task.topic.get("title") if isinstance(task.topic, dict) else None,
            session_dir=str(session_dir),
            config_path=str(config_path),
            session_marker_path=str(session_marker_path),
            history_path=str(session_dir / "history.md"),
            plan_path=str(session_dir / f"plan.task.{task_id}.run.{run_id}.md"),
            response_path=str(session_dir / response_filename),
            status_path=str(state_dir / status_filename),
            returncode=None,
            error=None,
            ttl=None,
        )
        await store.put_run_record(run_record)

        await store.update_implementation_task(
            channel_id=channel_id,
            task_id=task_id,
            from_status=task.status,
            to_status="implementing",
            active_implementer_run_id=run_id,
            latest_planner_run_id=run_id,
        )

        plan = decision_to_ifplan(decision)
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
            session_dir=session_dir,
        )

        poll_task = asyncio.create_task(
            _poll_task_control(task_id, channel_id, run_id, cancel_event)
        )

        try:
            flow_result = await execute_route(
                plan=plan,
                session_dir=Path(str(session_dir)),
                runtime_context=runtime_context,
                http_client=http_client,
                run_id=run_id,
                response_filename=response_filename,
                review_filename=review_filename,
                status_filename=status_filename,
                cancel_event=cancel_event,
            )
        except RunCancelledError:
            logger.info("Run %s cancelled for task %s, checking task status", run_id, task_id)
            await _handle_cancel_outcome(
                store=store,
                channel_id=channel_id,
                conversation_id=conversation_id,
                task_id=task_id,
                run_id=run_id,
                intent_id=intent_id,
                batch_id=batch_id,
                channel_ref=channel_ref,
                discord_loop=discord_loop,
            )
            return

        await store.update_implementation_task(
            channel_id=channel_id,
            task_id=task_id,
            from_status="implementing",
            to_status="completed",
        )

        result_attachments = []
        if flow_result.file_refs:
            result_attachments = [
                {"filename": ref.path.split("/")[-1], "url": ref.path, "description": ref.description}
                for ref in flow_result.file_refs
            ]

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
        )

        await store.update_intent_record_status(
            batch_id=batch_id,
            intent_id=intent_id,
            from_status="running",
            to_status="completed",
        )

    except RunCancelledError:
        await _handle_cancel_outcome(
            store=store,
            channel_id=channel_id,
            conversation_id=conversation_id,
            task_id=task_id,
            run_id=run_id,
            intent_id=intent_id,
            batch_id=batch_id,
            channel_ref=channel_ref,
            discord_loop=discord_loop,
        )
    except Exception:
        logger.exception("Task worker failed for task %s", task_id)
        try:
            current_task = await store.get_implementation_task(channel_id, task_id)
            from_status = current_task.status if current_task else "implementing"
            if from_status in ("cancel_requested", "pivot_requested", "awaiting_instruction"):
                await _handle_cancel_outcome(
                    store=store,
                    channel_id=channel_id,
                    conversation_id=conversation_id,
                    task_id=task_id,
                    run_id=run_id,
                    intent_id=intent_id,
                    batch_id=batch_id,
                    channel_ref=channel_ref,
                    discord_loop=discord_loop,
                )
                return
            await store.update_implementation_task(
                channel_id=channel_id,
                task_id=task_id,
                from_status=from_status,
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
            )
            await store.update_intent_record_status(
                batch_id=batch_id,
                intent_id=intent_id,
                from_status="running",
                to_status="failed",
                error="execution_failed",
            )
        except Exception:
            logger.exception("Task failure cleanup failed for task %s", task_id)
    finally:
        if poll_task is not None and not poll_task.done():
            poll_task.cancel()
            try:
                await poll_task
            except asyncio.CancelledError:
                pass
        clear_platform_context()

async def _handle_cancel_outcome(
    *,
    store: Any,
    channel_id: str,
    conversation_id: str,
    task_id: str,
    run_id: str,
    intent_id: str,
    batch_id: str,
    channel_ref: Any,
    discord_loop: Any,
) -> None:
    from channels.decision_applier import _enqueue_message
    current_task = await store.get_implementation_task(channel_id, task_id)
    if current_task is None:
        logger.warning("Task %s not found during cancel outcome handling", task_id)
        return

    status = current_task.status

    if status == "cancel_requested":
        await store.update_implementation_task(
            channel_id=channel_id,
            task_id=task_id,
            from_status="cancel_requested",
            to_status="completed",
        )
        await _enqueue_message(
            store=store,
            channel_id=channel_id,
            conversation_id=conversation_id,
            msg_type="cancel_confirmation",
            content=f"Task {task_id} cancelled",
            priority=4,
            task_id=task_id,
            intent_id=intent_id,
            batch_id=batch_id,
        )
        await store.update_intent_record_status(
            batch_id=batch_id,
            intent_id=intent_id,
            from_status="running",
            to_status="completed",
        )

    elif status == "pivot_requested":
        updated = await store.update_implementation_task(
            channel_id=channel_id,
            task_id=task_id,
            from_status="pivot_requested",
            to_status="implementing",
            active_implementer_run_id=None,
        )
        if not updated:
            logger.warning("Pivot transition failed for task %s; may have already been restarted", task_id)
            return
        await _enqueue_message(
            store=store,
            channel_id=channel_id,
            conversation_id=conversation_id,
            msg_type="task_update",
            content=f"Task {task_id} pivoting with updated topic, starting new run",
            priority=4,
            task_id=task_id,
            intent_id=intent_id,
            batch_id=batch_id,
        )
        refreshed_for_pivot = await store.get_implementation_task(channel_id, task_id)
        if refreshed_for_pivot is None:
            logger.warning("Task %s not found for pivot restart", task_id)
            return
        from channels.execution_models import ClassifierDecision
        pivot_decision = ClassifierDecision(
            intent_id=str(uuid.uuid4()),
            kind="implementation_control",
            action="pivot_active_implementation",
            target_task_id=task_id,
            reason="Pivot after cancel of run %s" % run_id,
            selected_specialist=refreshed_for_pivot.selected_specialist,
            selected_model=refreshed_for_pivot.selected_model,
            planner_intent=refreshed_for_pivot.topic,
        )
        import asyncio as _asyncio
        from channels.task_worker import run_task_worker
        _asyncio.ensure_future(run_task_worker(
            task=refreshed_for_pivot,
            decision=pivot_decision,
            batch_id=batch_id,
            intent_id=str(uuid.uuid4()),
            channel_ref=channel_ref,
            discord_loop=discord_loop,
        ))

    elif status == "awaiting_instruction":
        conflict = current_task.pending_conflict or {}
        conflict_summary = conflict.get("summary", "") if conflict else ""
        conflict_type = conflict.get("type", "unknown") if conflict else "unknown"
        content = f"Task {task_id} awaiting instruction ({conflict_type})"
        if conflict_summary:
            content += f": {conflict_summary}"
        await _enqueue_message(
            store=store,
            channel_id=channel_id,
            conversation_id=conversation_id,
            msg_type="await_instruction",
            content=content,
            priority=4,
            task_id=task_id,
            intent_id=intent_id,
            batch_id=batch_id,
        )
    else:
        logger.warning(
            "Unexpected task status %s during cancel outcome for task %s",
            status,
            task_id,
        )
        try:
            await store.update_implementation_task(
                channel_id=channel_id,
                task_id=task_id,
                from_status=status,
                to_status="failed",
            )
        except Exception:
            pass
