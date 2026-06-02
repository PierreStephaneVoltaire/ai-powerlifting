"""Tests for Phase 7 cancellable executor registry."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio
import pytest

APP_SRC = str(Path(__file__).resolve().parent.parent / "app" / "src")
if APP_SRC not in sys.path:
    sys.path.insert(0, APP_SRC)

@pytest.fixture(autouse=True)
def clean_registry():
    from channels.cancellable_executor import clear
    clear()
    yield
    clear()

class TestRegistry:
    def test_register_and_deregister(self):
        from channels.cancellable_executor import register, deregister, is_registered
        proc = MagicMock()
        proc.returncode = None
        cancel_event = register("run-1", proc)
        assert is_registered("run-1")
        assert not cancel_event.is_set()
        deregister("run-1")
        assert not is_registered("run-1")

    def test_register_with_existing_cancel_event(self):
        from channels.cancellable_executor import register, is_registered
        proc = MagicMock()
        proc.returncode = None
        existing_event = asyncio.Event()
        cancel_event = register("run-2", proc, cancel_event=existing_event)
        assert cancel_event is existing_event

    def test_register_creates_event_if_none(self):
        from channels.cancellable_executor import register
        proc = MagicMock()
        proc.returncode = None
        cancel_event = register("run-3", proc)
        assert cancel_event is not None
        assert not cancel_event.is_set()

    def test_deregister_nonexistent_is_noop(self):
        from channels.cancellable_executor import deregister
        deregister("nonexistent")

    def test_is_registered_false_for_unknown(self):
        from channels.cancellable_executor import is_registered
        assert not is_registered("unknown")

class TestRequestCancel:
    def test_request_cancel_registered(self):
        from channels.cancellable_executor import register, request_cancel
        proc = MagicMock()
        proc.returncode = None
        cancel_event = register("run-cancel", proc)
        result = request_cancel("run-cancel")
        assert result is True
        assert cancel_event.is_set()

    def test_request_cancel_unregistered(self):
        from channels.cancellable_executor import request_cancel
        result = request_cancel("nonexistent")
        assert result is False

class TestGetCancelEvent:
    def test_get_event_for_registered(self):
        from channels.cancellable_executor import register, get_cancel_event
        proc = MagicMock()
        proc.returncode = None
        cancel_event = register("run-ev", proc)
        result = get_cancel_event("run-ev")
        assert result is cancel_event

    def test_get_event_for_unregistered(self):
        from channels.cancellable_executor import get_cancel_event
        result = get_cancel_event("nonexistent")
        assert result is None

class TestTerminateAndKill:
    @pytest.mark.asyncio
    async def test_terminate_proc_that_exits(self):
        from channels.cancellable_executor import register, terminate_and_kill
        proc = MagicMock()
        proc.returncode = None
        proc.terminate = MagicMock()
        proc.wait = AsyncMock(return_value=0)
        register("run-tk1", proc)
        result = await terminate_and_kill("run-tk1", grace_seconds=2.0)
        assert result is True
        proc.terminate.assert_called_once()

    @pytest.mark.asyncio
    async def test_terminate_proc_already_exited(self):
        from channels.cancellable_executor import register, terminate_and_kill, is_registered
        proc = MagicMock()
        proc.returncode = 0
        register("run-tk2", proc)
        result = await terminate_and_kill("run-tk2")
        assert result is True
        assert not is_registered("run-tk2")

    @pytest.mark.asyncio
    async def test_terminate_proc_needs_kill(self):
        from channels.cancellable_executor import register, terminate_and_kill
        proc = MagicMock()
        proc.returncode = None
        proc.terminate = MagicMock()
        proc.kill = MagicMock()
        call_count = 0
        async def wait_then_timeout():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise asyncio.TimeoutError()
            return -9
        proc.wait = wait_then_timeout
        register("run-tk3", proc)
        result = await terminate_and_kill("run-tk3", grace_seconds=0.1)
        assert result is True
        proc.terminate.assert_called_once()
        proc.kill.assert_called_once()

    @pytest.mark.asyncio
    async def test_terminate_unregistered(self):
        from channels.cancellable_executor import terminate_and_kill
        result = await terminate_and_kill("nonexistent")
        assert result is False

class TestRunCancelledError:
    def test_run_cancelled_error_exists(self):
        from flow.opencode import RunCancelledError
        err = RunCancelledError("test cancel")
        assert str(err) == "test cancel"

class TestOpencodeResult:
    def test_cancelled_field(self):
        from flow.opencode import OpencodeResult
        result = OpencodeResult(returncode=-1, stdout="", stderr="", cancelled=True)
        assert result.cancelled is True
        result2 = OpencodeResult(returncode=0, stdout="ok", stderr="")
        assert result2.cancelled is False

class TestCancelEventThreading:
    def test_cancel_event_threaded_through_execute_route(self):
        import inspect
        from flow.runner import execute_route
        sig = inspect.signature(execute_route)
        assert "cancel_event" in sig.parameters

    def test_cancel_event_threaded_through_run_domain(self):
        import inspect
        from flow.runner import _run_domain
        sig = inspect.signature(_run_domain)
        assert "cancel_event" in sig.parameters

    def test_cancel_event_threaded_through_run_technical(self):
        import inspect
        from flow.runner import _run_technical
        sig = inspect.signature(_run_technical)
        assert "cancel_event" in sig.parameters

    def test_cancel_event_threaded_through_run_opencode(self):
        import inspect
        from flow.opencode import run_opencode
        sig = inspect.signature(run_opencode)
        assert "cancel_event" in sig.parameters

class TestConfigValues:
    def test_grace_seconds_config_exists(self):
        from config import OPENCODE_CANCEL_GRACE_SECONDS
        assert isinstance(OPENCODE_CANCEL_GRACE_SECONDS, int)
        assert OPENCODE_CANCEL_GRACE_SECONDS > 0

    def test_poll_interval_config_exists(self):
        from config import OPENCODE_CANCEL_POLL_INTERVAL_SECONDS
        assert isinstance(OPENCODE_CANCEL_POLL_INTERVAL_SECONDS, float)
        assert OPENCODE_CANCEL_POLL_INTERVAL_SECONDS > 0

class TestDecisionApplierCancelSignal:
    @pytest.mark.asyncio
    async def test_cancel_signals_active_run(self):
        from channels.decision_applier import _apply_cancel_implementation
        from channels.execution_models import ClassifierDecision, IntentRecord
        decision = ClassifierDecision(
            intent_id="int-1",
            kind="implementation_control",
            action="cancel_active_implementation",
            target_task_id="task-1",
            reason="test cancel",
        )
        intent = IntentRecord(
            intent_id="int-1",
            batch_id="batch-1",
            channel_id="ch-1",
            action="cancel_active_implementation",
            kind="implementation_control",
        )
        store = MagicMock()
        task = MagicMock()
        task.status = "implementing"
        task.active_implementer_run_id = "run-1"
        store.get_implementation_task = AsyncMock(return_value=task)
        store.update_implementation_task = AsyncMock(return_value=True)
        store.update_run_record_status = AsyncMock(return_value=True)
        store.put_outbound_message = AsyncMock(return_value=True)
        with patch("channels.cancellable_executor.request_cancel", return_value=True) as mock_req_cancel:
            await _apply_cancel_implementation(
                decision=decision, intent=intent, store=store,
                channel_id="ch-1", conversation_id="conv-1",
            )
        mock_req_cancel.assert_called_once_with("run-1")

    @pytest.mark.asyncio
    async def test_pivot_signals_active_run(self):
        from channels.decision_applier import _apply_pivot_implementation
        from channels.execution_models import ClassifierDecision, IntentRecord
        decision = ClassifierDecision(
            intent_id="int-2",
            kind="implementation_control",
            action="pivot_active_implementation",
            target_task_id="task-2",
            reason="test pivot",
            topic_update={"new_key": "new_value"},
        )
        intent = IntentRecord(
            intent_id="int-2",
            batch_id="batch-2",
            channel_id="ch-2",
            action="pivot_active_implementation",
            kind="implementation_control",
        )
        store = MagicMock()
        task = MagicMock()
        task.status = "implementing"
        task.active_implementer_run_id = "run-2"
        task.topic = {"old_key": "old_value"}
        store.get_implementation_task = AsyncMock(return_value=task)
        store.update_implementation_task = AsyncMock(return_value=True)
        store.update_run_record_status = AsyncMock(return_value=True)
        store.put_outbound_message = AsyncMock(return_value=True)
        with patch("channels.cancellable_executor.request_cancel", return_value=True) as mock_req_cancel:
            await _apply_pivot_implementation(
                decision=decision, intent=intent, store=store,
                channel_id="ch-2", conversation_id="conv-2",
            )
        mock_req_cancel.assert_called_once_with("run-2")

    @pytest.mark.asyncio
    async def test_await_instruction_signals_active_run(self):
        from channels.decision_applier import _apply_await_instruction
        from channels.execution_models import ClassifierDecision, IntentRecord
        decision = ClassifierDecision(
            intent_id="int-3",
            kind="implementation_control",
            action="await_instruction_for_active_implementation",
            target_task_id="task-3",
            reason="test await",
            conflict={"type": "conflict", "summary": "ambiguous"},
        )
        intent = IntentRecord(
            intent_id="int-3",
            batch_id="batch-3",
            channel_id="ch-3",
            action="await_instruction_for_active_implementation",
            kind="implementation_control",
        )
        store = MagicMock()
        task = MagicMock()
        task.status = "implementing"
        task.active_implementer_run_id = "run-3"
        store.get_implementation_task = AsyncMock(return_value=task)
        store.update_implementation_task = AsyncMock(return_value=True)
        store.update_run_record_status = AsyncMock(return_value=True)
        store.put_outbound_message = AsyncMock(return_value=True)
        with patch("channels.cancellable_executor.request_cancel", return_value=True) as mock_req_cancel:
            await _apply_await_instruction(
                decision=decision, intent=intent, store=store,
                channel_id="ch-3", conversation_id="conv-3",
            )
        mock_req_cancel.assert_called_once_with("run-3")
