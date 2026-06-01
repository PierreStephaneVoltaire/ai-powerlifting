"""Tests for channels.decision_applier."""
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

APP_SRC = str(Path(__file__).resolve().parent.parent / "app" / "src")
if APP_SRC not in sys.path:
    sys.path.insert(0, APP_SRC)

from channels.execution_models import ClassifierDecision, IntentRecord, ImplementationTask
from channels.decision_applier import apply_decision, apply_batch_decisions


def _make_decision(**overrides) -> ClassifierDecision:
    defaults = dict(
        intent_id="intent-1",
        kind="social",
        action="social_response",
        source_message_ids=["msg-1"],
        target_task_id=None,
        confidence=0.9,
        reason="test reason",
        needs_planning=False,
        selected_specialist=None,
        selected_model=None,
        social_response_text=None,
        response_text=None,
        planner_intent=None,
        topic_update=None,
        conflict=None,
    )
    defaults.update(overrides)
    return ClassifierDecision(**defaults)


def _make_intent(decision: ClassifierDecision, batch_id: str = "batch-1") -> IntentRecord:
    return IntentRecord(
        intent_id=decision.intent_id,
        batch_id=batch_id,
        channel_id="chan-1",
        action=decision.action,
        kind=decision.kind,
        source_message_ids=decision.source_message_ids,
        target_task_id=decision.target_task_id,
        status="pending",
        created_at="2025-01-01T00:00:00+00:00",
        updated_at="2025-01-01T00:00:00+00:00",
    )


def _mock_store():
    store = MagicMock()
    store.get_intent_record = AsyncMock(return_value=None)
    store.update_intent_record_status = AsyncMock(return_value=True)
    store.put_implementation_task = AsyncMock(return_value=True)
    store.get_implementation_task = AsyncMock(return_value=None)
    store.update_implementation_task = AsyncMock(return_value=True)
    store.append_task_queued_refs = AsyncMock(return_value=True)
    store.put_outbound_message = AsyncMock(return_value=True)
    return store


@pytest.mark.asyncio
async def test_apply_decision_skips_non_pending_intent():
    decision = _make_decision()
    intent = _make_intent(decision)
    intent.status = "completed"
    store = _mock_store()
    store.get_intent_record = AsyncMock(return_value=intent)

    with patch("channels.decision_applier.get_execution_store", return_value=store), \
         patch("channels.outbound_queue.schedule_drain"):
        result = await apply_decision(
            decision=decision,
            batch_id="batch-1",
            channel_id="chan-1",
            conversation_id="conv-1",
        )

    assert result is True
    store.update_intent_record_status.assert_not_called()


@pytest.mark.asyncio
async def test_apply_decision_fails_if_intent_not_found():
    decision = _make_decision()
    store = _mock_store()
    store.get_intent_record = AsyncMock(return_value=None)

    with patch("channels.decision_applier.get_execution_store", return_value=store), \
         patch("channels.outbound_queue.schedule_drain"):
        result = await apply_decision(
            decision=decision,
            batch_id="batch-1",
            channel_id="chan-1",
            conversation_id="conv-1",
        )

    assert result is False


@pytest.mark.asyncio
async def test_apply_decision_fails_if_pending_to_applying_fails():
    decision = _make_decision()
    intent = _make_intent(decision)
    store = _mock_store()
    store.get_intent_record = AsyncMock(return_value=intent)
    store.update_intent_record_status = AsyncMock(return_value=False)

    with patch("channels.decision_applier.get_execution_store", return_value=store), \
         patch("channels.outbound_queue.schedule_drain"):
        result = await apply_decision(
            decision=decision,
            batch_id="batch-1",
            channel_id="chan-1",
            conversation_id="conv-1",
        )

    assert result is True


@pytest.mark.asyncio
async def test_social_response_with_text():
    decision = _make_decision(
        action="social_response",
        social_response_text="Hello there!",
    )
    intent = _make_intent(decision)
    store = _mock_store()
    store.get_intent_record = AsyncMock(return_value=intent)

    with patch("channels.decision_applier.get_execution_store", return_value=store), \
         patch("channels.outbound_queue.schedule_drain") as mock_drain:
        result = await apply_decision(
            decision=decision,
            batch_id="batch-1",
            channel_id="chan-1",
            conversation_id="conv-1",
        )

    assert result is True
    store.put_outbound_message.assert_called_once()
    msg = store.put_outbound_message.call_args[0][0]
    assert msg.type == "social_response"
    assert msg.content == "Hello there!"
    mock_drain.assert_called()


@pytest.mark.asyncio
async def test_clarifying_question():
    decision = _make_decision(
        action="ask_clarifying_target",
        kind="clarification",
        response_text="What do you mean?",
    )
    intent = _make_intent(decision)
    store = _mock_store()
    store.get_intent_record = AsyncMock(return_value=intent)

    with patch("channels.decision_applier.get_execution_store", return_value=store), \
         patch("channels.outbound_queue.schedule_drain"):
        result = await apply_decision(
            decision=decision,
            batch_id="batch-1",
            channel_id="chan-1",
            conversation_id="conv-1",
        )

    assert result is True
    store.put_outbound_message.assert_called_once()
    msg = store.put_outbound_message.call_args[0][0]
    assert msg.type == "clarifying_question"
    assert msg.priority == 3
    assert msg.content == "What do you mean?"


@pytest.mark.asyncio
async def test_ignore_action():
    decision = _make_decision(action="ignore", kind="ignore")
    intent = _make_intent(decision)
    store = _mock_store()
    store.get_intent_record = AsyncMock(return_value=intent)

    with patch("channels.decision_applier.get_execution_store", return_value=store), \
         patch("channels.outbound_queue.schedule_drain"):
        result = await apply_decision(
            decision=decision,
            batch_id="batch-1",
            channel_id="chan-1",
            conversation_id="conv-1",
        )

    assert result is True
    store.put_outbound_message.assert_not_called()
    status_calls = store.update_intent_record_status.call_args_list
    assert any(
        c.kwargs.get("to_status") == "skipped" or (len(c.args) > 2 and c.args[2] == "skipped")
        for c in status_calls
    )


@pytest.mark.asyncio
async def test_start_new_task_creates_task_record():
    decision = _make_decision(
        action="start_new_task",
        kind="task",
        selected_specialist="coder",
        selected_model="deepseek/deepseek-v4-flash",
        source_message_ids=["msg-1", "msg-2"],
        planner_intent={"title": "Fix bug"},
    )
    intent = _make_intent(decision)
    store = _mock_store()
    store.get_intent_record = AsyncMock(return_value=intent)

    mock_flow_result = MagicMock()
    mock_flow_result.content = "Task complete"
    mock_flow_result.file_refs = []

    fake_session_dir = Path("/tmp/fake-session")

    with patch("channels.decision_applier.get_execution_store", return_value=store), \
         patch("flow.batch_classifier.decision_to_ifplan", return_value=MagicMock()), \
         patch("flow.runner.execute_route", new_callable=AsyncMock, return_value=mock_flow_result), \
         patch("channels.channel_coordinator._resolve_session_dir", return_value=fake_session_dir), \
         patch("flow.context.build_runtime_context", return_value=MagicMock()), \
         patch("channels.outbound_queue.schedule_drain"):
        result = await apply_decision(
            decision=decision,
            batch_id="batch-1",
            channel_id="chan-1",
            conversation_id="conv-1",
        )

    assert result is True
    store.put_implementation_task.assert_called_once()
    task = store.put_implementation_task.call_args[0][0]
    assert isinstance(task, ImplementationTask)
    assert task.status == "implementing"
    assert task.selected_specialist == "coder"
    assert task.selected_model == "deepseek/deepseek-v4-flash"
    assert task.root_discord_message_id == "msg-1"
    assert task.related_discord_message_ids == ["msg-2"]


@pytest.mark.asyncio
async def test_append_to_active_requires_target_task_id():
    decision = _make_decision(
        action="append_to_active_implementation",
        kind="implementation_control",
        target_task_id=None,
    )
    intent = _make_intent(decision)
    store = _mock_store()
    store.get_intent_record = AsyncMock(return_value=intent)

    with patch("channels.decision_applier.get_execution_store", return_value=store), \
         patch("channels.outbound_queue.schedule_drain"):
        result = await apply_decision(
            decision=decision,
            batch_id="batch-1",
            channel_id="chan-1",
            conversation_id="conv-1",
        )

    assert result is False


@pytest.mark.asyncio
async def test_append_to_active_appends_refs():
    decision = _make_decision(
        action="append_to_active_implementation",
        kind="implementation_control",
        target_task_id="task-99",
        source_message_ids=["msg-a", "msg-b"],
    )
    intent = _make_intent(decision)
    existing_task = ImplementationTask(
        task_id="task-99",
        channel_id="chan-1",
        conversation_id="conv-1",
        status="implementing",
        root_discord_message_id="msg-root",
        version=3,
    )
    store = _mock_store()
    store.get_intent_record = AsyncMock(return_value=intent)
    store.get_implementation_task = AsyncMock(return_value=existing_task)

    with patch("channels.decision_applier.get_execution_store", return_value=store), \
         patch("channels.outbound_queue.schedule_drain"):
        result = await apply_decision(
            decision=decision,
            batch_id="batch-1",
            channel_id="chan-1",
            conversation_id="conv-1",
        )

    assert result is True
    store.append_task_queued_refs.assert_called_once()
    refs = store.append_task_queued_refs.call_args.kwargs["refs"]
    assert len(refs) == 2
    assert refs[0]["reason"] == "append_to_active"
    assert refs[0]["message_id"] == "msg-a"
    assert refs[1]["message_id"] == "msg-b"


@pytest.mark.asyncio
async def test_queue_on_active():
    decision = _make_decision(
        action="queue_on_active_implementation",
        kind="implementation_control",
        target_task_id="task-42",
        source_message_ids=["msg-x"],
    )
    intent = _make_intent(decision)
    existing_task = ImplementationTask(
        task_id="task-42",
        channel_id="chan-1",
        conversation_id="conv-1",
        status="implementing",
        root_discord_message_id="msg-root",
        version=2,
    )
    store = _mock_store()
    store.get_intent_record = AsyncMock(return_value=intent)
    store.get_implementation_task = AsyncMock(return_value=existing_task)

    with patch("channels.decision_applier.get_execution_store", return_value=store), \
         patch("channels.outbound_queue.schedule_drain"):
        result = await apply_decision(
            decision=decision,
            batch_id="batch-1",
            channel_id="chan-1",
            conversation_id="conv-1",
        )

    assert result is True
    refs = store.append_task_queued_refs.call_args.kwargs["refs"]
    assert len(refs) == 1
    assert refs[0]["reason"] == "queued"
    assert refs[0]["message_id"] == "msg-x"


@pytest.mark.asyncio
async def test_await_instruction_sets_awaiting():
    decision = _make_decision(
        action="await_instruction_for_active_implementation",
        kind="implementation_control",
        target_task_id="task-7",
        conflict={"type": "scope_overlap", "summary": "Two tasks touch same file"},
    )
    intent = _make_intent(decision)
    existing_task = ImplementationTask(
        task_id="task-7",
        channel_id="chan-1",
        conversation_id="conv-1",
        status="implementing",
        root_discord_message_id="msg-root",
    )
    store = _mock_store()
    store.get_intent_record = AsyncMock(return_value=intent)
    store.get_implementation_task = AsyncMock(return_value=existing_task)

    with patch("channels.decision_applier.get_execution_store", return_value=store), \
         patch("channels.outbound_queue.schedule_drain"):
        result = await apply_decision(
            decision=decision,
            batch_id="batch-1",
            channel_id="chan-1",
            conversation_id="conv-1",
        )

    assert result is True
    update_call = store.update_implementation_task.call_args
    assert update_call.kwargs["to_status"] == "awaiting_instruction"
    assert update_call.kwargs["pending_conflict"] == {
        "type": "scope_overlap",
        "summary": "Two tasks touch same file",
    }


@pytest.mark.asyncio
async def test_cancel_implementation():
    decision = _make_decision(
        action="cancel_active_implementation",
        kind="implementation_control",
        target_task_id="task-cancel",
    )
    intent = _make_intent(decision)
    existing_task = ImplementationTask(
        task_id="task-cancel",
        channel_id="chan-1",
        conversation_id="conv-1",
        status="implementing",
        root_discord_message_id="msg-root",
    )
    store = _mock_store()
    store.get_intent_record = AsyncMock(return_value=intent)
    store.get_implementation_task = AsyncMock(return_value=existing_task)

    with patch("channels.decision_applier.get_execution_store", return_value=store), \
         patch("channels.outbound_queue.schedule_drain"):
        result = await apply_decision(
            decision=decision,
            batch_id="batch-1",
            channel_id="chan-1",
            conversation_id="conv-1",
        )

    assert result is True
    update_call = store.update_implementation_task.call_args
    assert update_call.kwargs["to_status"] == "cancel_requested"


@pytest.mark.asyncio
async def test_pivot_implementation_merges_topic():
    decision = _make_decision(
        action="pivot_active_implementation",
        kind="implementation_control",
        target_task_id="task-pivot",
        topic_update={"new_key": "new_value"},
    )
    intent = _make_intent(decision)
    existing_task = ImplementationTask(
        task_id="task-pivot",
        channel_id="chan-1",
        conversation_id="conv-1",
        status="implementing",
        root_discord_message_id="msg-root",
        topic={"existing_key": "existing_value"},
    )
    store = _mock_store()
    store.get_intent_record = AsyncMock(return_value=intent)
    store.get_implementation_task = AsyncMock(return_value=existing_task)

    with patch("channels.decision_applier.get_execution_store", return_value=store), \
         patch("channels.outbound_queue.schedule_drain"):
        result = await apply_decision(
            decision=decision,
            batch_id="batch-1",
            channel_id="chan-1",
            conversation_id="conv-1",
        )

    assert result is True
    update_call = store.update_implementation_task.call_args
    assert update_call.kwargs["to_status"] == "pivot_requested"
    merged = update_call.kwargs["topic"]
    assert merged["existing_key"] == "existing_value"
    assert merged["new_key"] == "new_value"


@pytest.mark.asyncio
async def test_apply_batch_decisions():
    d1 = _make_decision(intent_id="int-a", action="social_response", social_response_text="Hi")
    d2 = _make_decision(intent_id="int-b", action="ignore", kind="ignore")
    i1 = _make_intent(d1)
    i2 = _make_intent(d2)
    store = _mock_store()

    async def _get_intent(batch_id, intent_id):
        if intent_id == "int-a":
            return i1
        if intent_id == "int-b":
            return i2
        return None

    store.get_intent_record = AsyncMock(side_effect=_get_intent)

    with patch("channels.decision_applier.get_execution_store", return_value=store), \
         patch("channels.outbound_queue.schedule_drain"):
        results = await apply_batch_decisions(
            decisions=[d1, d2],
            batch_id="batch-1",
            channel_id="chan-1",
            conversation_id="conv-1",
        )

    assert len(results) == 2
    assert results[0] is True
    assert results[1] is True


@pytest.mark.asyncio
async def test_enqueue_message_idempotency():
    decision = _make_decision(
        action="social_response",
        social_response_text="Test idempotency",
    )
    intent = _make_intent(decision)
    store = _mock_store()
    store.get_intent_record = AsyncMock(return_value=intent)

    with patch("channels.decision_applier.get_execution_store", return_value=store), \
         patch("channels.outbound_queue.schedule_drain"):
        result = await apply_decision(
            decision=decision,
            batch_id="batch-1",
            channel_id="chan-1",
            conversation_id="conv-1",
        )

    assert result is True
    store.put_outbound_message.assert_called_once()
    msg = store.put_outbound_message.call_args[0][0]
    parts = msg.idempotency_key.split(":")
    assert parts[0] == "batch-1"
    assert parts[1] == "intent-1"
    assert parts[2] == "social_response"
    assert len(parts) == 3


@pytest.mark.asyncio
async def test_decision_failure_updates_intent_to_failed():
    decision = _make_decision(
        action="cancel_active_implementation",
        kind="implementation_control",
        target_task_id="task-bad",
    )
    intent = _make_intent(decision)
    store = _mock_store()
    store.get_intent_record = AsyncMock(return_value=intent)
    store.get_implementation_task = AsyncMock(side_effect=RuntimeError("boom"))

    with patch("channels.decision_applier.get_execution_store", return_value=store), \
         patch("channels.outbound_queue.schedule_drain"):
        result = await apply_decision(
            decision=decision,
            batch_id="batch-1",
            channel_id="chan-1",
            conversation_id="conv-1",
        )

    assert result is False
    status_calls = store.update_intent_record_status.call_args_list
    last_call = status_calls[-1]
    assert last_call.kwargs.get("to_status") == "failed" or last_call[1].get("to_status") == "failed"


@pytest.mark.asyncio
async def test_enqueue_triggers_drain():
    """schedule_drain is called when outbound message is stored."""
    decision = _make_decision(
        action="social_response",
        social_response_text="Hello!",
    )
    intent = _make_intent(decision)
    store = _mock_store()
    store.get_intent_record = AsyncMock(return_value=intent)

    with patch("channels.decision_applier.get_execution_store", return_value=store), \
         patch("channels.outbound_queue.schedule_drain") as mock_drain:
        result = await apply_decision(
            decision=decision,
            batch_id="batch-1",
            channel_id="chan-1",
            conversation_id="conv-1",
        )

    assert result is True
    mock_drain.assert_called_once_with("chan-1")


@pytest.mark.asyncio
async def test_enqueue_no_drain_on_store_failure():
    """schedule_drain is NOT called when put_outbound_message returns False."""
    decision = _make_decision(
        action="social_response",
        social_response_text="Hello!",
    )
    intent = _make_intent(decision)
    store = _mock_store()
    store.get_intent_record = AsyncMock(return_value=intent)
    store.put_outbound_message = AsyncMock(return_value=False)

    with patch("channels.decision_applier.get_execution_store", return_value=store), \
         patch("channels.outbound_queue.schedule_drain") as mock_drain:
        result = await apply_decision(
            decision=decision,
            batch_id="batch-1",
            channel_id="chan-1",
            conversation_id="conv-1",
        )

    assert result is False
    mock_drain.assert_not_called()
