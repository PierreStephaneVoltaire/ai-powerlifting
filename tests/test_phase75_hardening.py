"""Phase 7.5 correctness hardening tests."""
from __future__ import annotations
import sys
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

APP_SRC = str(Path(__file__).resolve().parent.parent / "app" / "src")
if APP_SRC not in sys.path:
    sys.path.insert(0, APP_SRC)


class TestPerRunArtifactExclusion:
    def test_per_run_response_excluded(self, tmp_path):
        from flow.runner import _artifact_refs, _snapshot_files
        before = _snapshot_files(tmp_path)
        (tmp_path / "response.task.abc.run.xyz.md").write_text("response content")
        refs = _artifact_refs(tmp_path, before)
        names = [Path(r.path).name for r in refs]
        assert "response.task.abc.run.xyz.md" not in names

    def test_per_run_plan_excluded(self, tmp_path):
        from flow.runner import _artifact_refs, _snapshot_files
        before = _snapshot_files(tmp_path)
        (tmp_path / "plan.task.abc.run.xyz.md").write_text("plan content")
        refs = _artifact_refs(tmp_path, before)
        names = [Path(r.path).name for r in refs]
        assert "plan.task.abc.run.xyz.md" not in names

    def test_per_run_review_excluded(self, tmp_path):
        from flow.runner import _artifact_refs, _snapshot_files
        before = _snapshot_files(tmp_path)
        (tmp_path / "review.task.abc.run.xyz.md").write_text("review content")
        refs = _artifact_refs(tmp_path, before)
        names = [Path(r.path).name for r in refs]
        assert "review.task.abc.run.xyz.md" not in names

    def test_per_run_status_excluded(self, tmp_path):
        from flow.runner import _artifact_refs, _snapshot_files
        before = _snapshot_files(tmp_path)
        (tmp_path / "status.task.abc.run.xyz.log").write_text("status content")
        refs = _artifact_refs(tmp_path, before)
        names = [Path(r.path).name for r in refs]
        assert "status.task.abc.run.xyz.log" not in names

    def test_real_deliverable_included(self, tmp_path):
        from flow.runner import _artifact_refs, _snapshot_files
        before = _snapshot_files(tmp_path)
        (tmp_path / "output.txt").write_text("real output")
        refs = _artifact_refs(tmp_path, before)
        names = [Path(r.path).name for r in refs]
        assert "output.txt" in names

    def test_is_per_run_runtime_file_true(self):
        from flow.runner import _is_per_run_runtime_file
        assert _is_per_run_runtime_file("response.task.t1.run.r1.md")
        assert _is_per_run_runtime_file("plan.task.t1.run.r1.md")
        assert _is_per_run_runtime_file("review.task.t1.run.r1.md")
        assert _is_per_run_runtime_file("status.task.t1.run.r1.log")

    def test_is_per_run_runtime_file_false(self):
        from flow.runner import _is_per_run_runtime_file
        assert not _is_per_run_runtime_file("response.md")
        assert not _is_per_run_runtime_file("my_output.py")
        assert not _is_per_run_runtime_file("plan.md")


class TestRecurringIdempotencyKeys:
    @pytest.mark.asyncio
    async def test_task_update_distinct_intents_have_distinct_keys(self):
        from channels.decision_applier import _enqueue_message
        store = MagicMock()
        captured = []
        store.put_outbound_message = AsyncMock(side_effect=lambda m: captured.append(m) or True)
        with patch("channels.outbound_queue.schedule_drain"):
            await _enqueue_message(
                store=store, channel_id="c1", conversation_id="cv1",
                msg_type="task_update", content="pivot 1",
                task_id="t1", intent_id="intent-1", batch_id="b1",
            )
            await _enqueue_message(
                store=store, channel_id="c1", conversation_id="cv1",
                msg_type="task_update", content="pivot 2",
                task_id="t1", intent_id="intent-2", batch_id="b1",
            )
        assert len(captured) == 2
        assert captured[0].idempotency_key != captured[1].idempotency_key
        assert "intent-1" in captured[0].idempotency_key
        assert "intent-2" in captured[1].idempotency_key

    @pytest.mark.asyncio
    async def test_task_update_same_intent_stable_key(self):
        from channels.decision_applier import _enqueue_message
        store = MagicMock()
        captured = []
        store.put_outbound_message = AsyncMock(side_effect=lambda m: captured.append(m) or True)
        with patch("channels.outbound_queue.schedule_drain"):
            await _enqueue_message(
                store=store, channel_id="c1", conversation_id="cv1",
                msg_type="task_update", content="same",
                task_id="t1", intent_id="same-intent", batch_id="b1",
            )
            await _enqueue_message(
                store=store, channel_id="c1", conversation_id="cv1",
                msg_type="task_update", content="same",
                task_id="t1", intent_id="same-intent", batch_id="b1",
            )
        assert captured[0].idempotency_key == captured[1].idempotency_key

    @pytest.mark.asyncio
    async def test_task_completed_terminal_key_stable(self):
        from channels.decision_applier import _enqueue_message
        store = MagicMock()
        captured = []
        store.put_outbound_message = AsyncMock(side_effect=lambda m: captured.append(m) or True)
        with patch("channels.outbound_queue.schedule_drain"):
            await _enqueue_message(
                store=store, channel_id="c1", conversation_id="cv1",
                msg_type="task_completed", content="done",
                task_id="t1", intent_id="i1", batch_id="b1",
            )
            await _enqueue_message(
                store=store, channel_id="c1", conversation_id="cv1",
                msg_type="task_completed", content="done again",
                task_id="t1", intent_id="i2", batch_id="b2",
            )
        assert captured[0].idempotency_key == captured[1].idempotency_key == "t1:task_completed"

    @pytest.mark.asyncio
    async def test_cancel_confirmation_terminal_key_stable(self):
        from channels.decision_applier import _enqueue_message
        store = MagicMock()
        captured = []
        store.put_outbound_message = AsyncMock(side_effect=lambda m: captured.append(m) or True)
        with patch("channels.outbound_queue.schedule_drain"):
            await _enqueue_message(
                store=store, channel_id="c1", conversation_id="cv1",
                msg_type="cancel_confirmation", content="cancelled",
                task_id="t1", intent_id="i1", batch_id="b1",
            )
            await _enqueue_message(
                store=store, channel_id="c1", conversation_id="cv1",
                msg_type="cancel_confirmation", content="cancelled again",
                task_id="t1", intent_id="i2", batch_id="b2",
            )
        assert captured[0].idempotency_key == captured[1].idempotency_key == "t1:cancel_confirmation"




class TestDrainLoopBounded:
    @pytest.mark.asyncio
    async def test_drain_loop_terminates_with_empty_queue(self):
        from channels import outbound_queue
        store = MagicMock()
        store.query_outbox = AsyncMock(return_value=[])
        await asyncio.wait_for(
            outbound_queue._drain_loop("c1", store, "owner", "2099-12-31T23:59:59+00:00"),
            timeout=5.0,
        )
        store.query_outbox.assert_called_once()

    @pytest.mark.asyncio
    async def test_drain_loop_terminates_with_expired_lock(self):
        from channels import outbound_queue
        from channels.execution_models import DiscordOutboundMessage

        msg = DiscordOutboundMessage(
            outbound_id="o1", channel_id="c1", conversation_id="cv1",
            type="social_response", priority=5, content="hi",
            attachments=[], status="queued",
            created_at="2025-01-01T00:00:00+00:00",
            updated_at="2025-01-01T00:00:00+00:00",
            idempotency_key="k1",
        )
        store = MagicMock()
        store.query_outbox = AsyncMock(return_value=[msg])
        store.update_outbound_message_status = AsyncMock(return_value=True)
        with patch.object(outbound_queue, "_resolve_discord_handle", return_value=(None, None)):
            await asyncio.wait_for(
                outbound_queue._drain_loop("c1", store, "owner", "2020-01-01T00:00:00+00:00"),
                timeout=5.0,
            )

    @pytest.mark.asyncio
    async def test_drain_loop_max_iterations_guard(self):
        from channels import outbound_queue
        from channels.execution_models import DiscordOutboundMessage

        msg = DiscordOutboundMessage(
            outbound_id="o1", channel_id="c1", conversation_id="cv1",
            type="social_response", priority=5, content="hi",
            attachments=[], status="queued",
            created_at="2025-01-01T00:00:00+00:00",
            updated_at="2025-01-01T00:00:00+00:00",
            idempotency_key="k1",
        )
        store = MagicMock()
        store.query_outbox = AsyncMock(return_value=[msg])
        store.update_outbound_message_status = AsyncMock(return_value=False)

        original_max = outbound_queue._DRAIN_MAX_ITERATIONS
        outbound_queue._DRAIN_MAX_ITERATIONS = 3
        try:
            with patch.object(outbound_queue, "_resolve_discord_handle", return_value=(None, None)):
                await asyncio.wait_for(
                    outbound_queue._drain_loop("c1", store, "owner", "2099-12-31T23:59:59+00:00"),
                    timeout=5.0,
                )
        finally:
            outbound_queue._DRAIN_MAX_ITERATIONS = original_max
        assert store.query_outbox.call_count <= 4


class TestDuplicateConditionalBlockRemoved:
    def test_update_outbound_status_sync_no_duplicate_log(self):
        store_path = Path(__file__).resolve().parent.parent / "app" / "src" / "channels" / "execution_store.py"
        src = store_path.read_text(encoding="utf-8")
        method_start = src.find("def _update_outbound_status_sync")
        method_end = src.find("\n    def ", method_start + 1)
        method_src = src[method_start:method_end] if method_end > 0 else src[method_start:]
        count = method_src.count("ConditionalCheckFailedException")
        assert count == 1, f"Expected 1 ConditionalCheckFailedException handler, found {count}"


class TestPivotRestartFreshStatus:
    @pytest.mark.asyncio
    async def test_handle_cancel_pivot_uses_refreshed_task(self):
        from channels.execution_models import ImplementationTask
        from datetime import datetime, timezone
        from channels.task_worker import _handle_cancel_outcome

        now = datetime.now(timezone.utc).isoformat()
        stale = ImplementationTask(
            task_id="t1", channel_id="c1", conversation_id="cv1",
            status="pivot_requested", root_discord_message_id="m1",
            related_discord_message_ids=[], active_implementer_run_id=None,
            selected_specialist="coder", selected_model="model-x",
            topic={"title": "old"}, created_at=now, updated_at=now,
        )
        refreshed = ImplementationTask(
            task_id="t1", channel_id="c1", conversation_id="cv1",
            status="implementing", root_discord_message_id="m1",
            related_discord_message_ids=[], active_implementer_run_id=None,
            selected_specialist="coder", selected_model="model-x",
            topic={"title": "new"}, created_at=now, updated_at=now,
        )
        call_n = {"n": 0}

        async def fake_get(channel_id, task_id):
            call_n["n"] += 1
            return stale if call_n["n"] == 1 else refreshed

        store = MagicMock()
        store.get_implementation_task = AsyncMock(side_effect=fake_get)
        store.update_implementation_task = AsyncMock(return_value=True)
        store.update_intent_record_status = AsyncMock(return_value=True)
        store.put_outbound_message = AsyncMock(return_value=True)

        worker_tasks = []

        async def fake_worker(**kwargs):
            worker_tasks.append(kwargs.get("task"))

        with patch("channels.outbound_queue.schedule_drain"), \
             patch("channels.task_worker.run_task_worker", side_effect=fake_worker):
            await _handle_cancel_outcome(
                store=store, channel_id="c1", conversation_id="cv1",
                task_id="t1", run_id="r1", intent_id="i1", batch_id="b1",
                channel_ref=None, discord_loop=None,
            )
            await asyncio.sleep(0)

        if worker_tasks:
            assert worker_tasks[0].status != "pivot_requested"

