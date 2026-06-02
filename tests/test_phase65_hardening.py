"""Phase 6.5 correctness hardening tests."""
from __future__ import annotations
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

APP_SRC = str(Path(__file__).resolve().parent.parent / "app" / "src")
if APP_SRC not in sys.path:
    sys.path.insert(0, APP_SRC)

def _make_ifplan(interaction_type="domain", specialist="coder", model="deepseek/deepseek-v4-flash"):
    from flow.plan import IFPlan
    return IFPlan(
        intent_summary="test",
        interaction_type=interaction_type,
        specialist=specialist,
        thinking_mode=False,
        selected_model=model,
        prompt="Do the thing",
        raw="---\n---\nDo the thing",
    )

class TestConfigPathPlumbing:
    @pytest.mark.asyncio
    async def test_run_domain_passes_config_path(self, tmp_path):
        plan = _make_ifplan()
        run_id = "run-abc-123"
        expected_config = tmp_path / ".if" / f"opencode.run.{run_id}.json"
        mock_result = MagicMock(returncode=0, stdout="", stderr="")
        with patch("flow.runner.write_opencode_config", return_value=expected_config) as mock_cfg, \
             patch("flow.runner.run_opencode", new_callable=AsyncMock, return_value=mock_result) as mock_oc, \
             patch("flow.runner._specialist_prompt", return_value=("", [], [])), \
             patch("flow.runner._artifact_refs", return_value=[]), \
             patch("flow.runner._parse_handoffs", return_value=("done", [])), \
             patch("flow.runner.send_status", new_callable=AsyncMock):
            rf = f"response.task.t.run.{run_id}.md"
            (tmp_path / rf).write_text("done")
            from flow.runner import _run_domain
            await _run_domain(plan, tmp_path, "ctx", run_id=run_id, response_filename=rf)
        mock_cfg.assert_called_once_with(tmp_path, tool_names=[], mcp_servers=[], run_id=run_id)
        kw = mock_oc.call_args.kwargs
        assert kw.get("config_path") == expected_config
        assert kw.get("run_id") == run_id

    @pytest.mark.asyncio
    async def test_run_domain_no_config_when_no_run_id(self, tmp_path):
        plan = _make_ifplan()
        mock_result = MagicMock(returncode=0, stdout="", stderr="")
        with patch("flow.runner.write_opencode_config", return_value=tmp_path / "opencode.json"), \
             patch("flow.runner.run_opencode", new_callable=AsyncMock, return_value=mock_result) as mock_oc, \
             patch("flow.runner._specialist_prompt", return_value=("", [], [])), \
             patch("flow.runner._artifact_refs", return_value=[]), \
             patch("flow.runner._parse_handoffs", return_value=("done", [])), \
             patch("flow.runner.send_status", new_callable=AsyncMock):
            (tmp_path / "response.md").write_text("done")
            from flow.runner import _run_domain
            await _run_domain(plan, tmp_path, "ctx")
        kw = mock_oc.call_args.kwargs
        assert kw.get("config_path") is None
        assert kw.get("session_marker_path") is None

    @pytest.mark.asyncio
    async def test_run_technical_passes_config_path(self, tmp_path):
        plan = _make_ifplan(interaction_type="technical", specialist="general")
        run_id = "run-tech-999"
        expected_config = tmp_path / ".if" / f"opencode.run.{run_id}.json"
        mock_result = MagicMock(returncode=0, stdout="", stderr="")
        with patch("flow.runner.write_opencode_config", return_value=expected_config) as mock_cfg, \
             patch("flow.runner.run_opencode", new_callable=AsyncMock, return_value=mock_result) as mock_oc, \
             patch("flow.runner._artifact_refs", return_value=[]), \
             patch("flow.runner.send_status", new_callable=AsyncMock):
            rf = f"response.task.t.run.{run_id}.md"
            rv = f"review.task.t.run.{run_id}.md"
            (tmp_path / rf).write_text("done")
            from flow.runner import _run_technical
            await _run_technical(plan, tmp_path, "ctx", run_id=run_id, response_filename=rf, review_filename=rv)
        mock_cfg.assert_called_once_with(tmp_path, tool_names=[], mcp_servers=[], run_id=run_id)
        kw = mock_oc.call_args_list[0].kwargs
        assert kw.get("config_path") == expected_config

class TestSessionMarkerPlumbing:
    @pytest.mark.asyncio
    async def test_run_domain_passes_per_run_marker(self, tmp_path):
        plan = _make_ifplan(specialist="coder")
        run_id = "run-marker-test"
        mock_result = MagicMock(returncode=0, stdout="", stderr="")
        with patch("flow.runner.write_opencode_config", return_value=tmp_path / ".if" / "cfg.json"), \
             patch("flow.runner.run_opencode", new_callable=AsyncMock, return_value=mock_result) as mock_oc, \
             patch("flow.runner._specialist_prompt", return_value=("", [], [])), \
             patch("flow.runner._artifact_refs", return_value=[]), \
             patch("flow.runner._parse_handoffs", return_value=("done", [])), \
             patch("flow.runner.send_status", new_callable=AsyncMock):
            rf = f"response.task.t.run.{run_id}.md"
            (tmp_path / rf).write_text("done")
            from flow.runner import _run_domain
            await _run_domain(plan, tmp_path, "ctx", run_id=run_id, response_filename=rf)
        kw = mock_oc.call_args.kwargs
        marker = kw.get("session_marker_path")
        assert marker is not None
        assert run_id in str(marker)
        assert "opencode-" in str(marker)
        assert ".session" in str(marker)

    @pytest.mark.asyncio
    async def test_concurrent_runs_have_distinct_markers(self, tmp_path):
        plan = _make_ifplan(specialist="coder")
        run_id_a, run_id_b = "run-a-111", "run-b-222"
        mock_result = MagicMock(returncode=0, stdout="", stderr="")
        markers = []
        async def capture(**kwargs):
            if kwargs.get("session_marker_path"):
                markers.append(kwargs["session_marker_path"])
            return mock_result
        with patch("flow.runner.write_opencode_config", return_value=tmp_path / ".if" / "cfg.json"), \
             patch("flow.runner.run_opencode", new_callable=AsyncMock, side_effect=capture), \
             patch("flow.runner._specialist_prompt", return_value=("", [], [])), \
             patch("flow.runner._artifact_refs", return_value=[]), \
             patch("flow.runner._parse_handoffs", return_value=("done", [])), \
             patch("flow.runner.send_status", new_callable=AsyncMock):
            from flow.runner import _run_domain
            (tmp_path / f"response.task.t.run.{run_id_a}.md").write_text("done")
            (tmp_path / f"response.task.t.run.{run_id_b}.md").write_text("done")
            await _run_domain(plan, tmp_path, "ctx", run_id=run_id_a, response_filename=f"response.task.t.run.{run_id_a}.md")
            await _run_domain(plan, tmp_path, "ctx", run_id=run_id_b, response_filename=f"response.task.t.run.{run_id_b}.md")
        assert len(markers) == 2
        assert markers[0] != markers[1]
        assert run_id_a in str(markers[0])
        assert run_id_b in str(markers[1])

class TestRunIfFlowThinkingModeNoNameError:
    @pytest.mark.asyncio
    async def test_thinking_mode_social_no_name_error(self, tmp_path):
        from flow.plan import IFPlan
        plan = IFPlan(intent_summary="test", interaction_type="social", specialist="general",
            thinking_mode=True, selected_model="deepseek/deepseek-v4-flash",
            prompt="Deep thoughts", raw="---\n---\nDeep thoughts")
        with patch("flow.runner._run_planner", new_callable=AsyncMock, return_value=plan), \
             patch("flow.runner._run_domain", new_callable=AsyncMock, return_value=("deep", [])), \
             patch("flow.runner.build_runtime_context", return_value="ctx"), \
             patch("flow.runner.resolve_session_dir", return_value=tmp_path), \
             patch("flow.runner.write_history", return_value=tmp_path / "history.md"), \
             patch("flow.runner.send_status", new_callable=AsyncMock), \
             patch("flow.runner.strip_files_line", return_value=("deep", [])):
            from flow.runner import run_if_flow
            result = await run_if_flow(
                request_data={"messages": [{"role": "user", "content": "Deep?"}]},
                http_client=AsyncMock(), cache_key="k1", context_id="c1")
        assert result.content == "deep"

    @pytest.mark.asyncio
    async def test_thinking_mode_does_not_pass_run_id_kwargs(self, tmp_path):
        from flow.plan import IFPlan
        plan = IFPlan(intent_summary="test", interaction_type="social", specialist="general",
            thinking_mode=True, selected_model="deepseek/deepseek-v4-flash",
            prompt="Think", raw="---\n---\nThink")
        captured = []
        async def fake_run_domain(the_plan, session_dir, runtime_ctx, **kwargs):
            captured.append(kwargs)
            return ("resp", [])
        with patch("flow.runner._run_planner", new_callable=AsyncMock, return_value=plan), \
             patch("flow.runner._run_domain", side_effect=fake_run_domain), \
             patch("flow.runner.build_runtime_context", return_value="ctx"), \
             patch("flow.runner.resolve_session_dir", return_value=tmp_path), \
             patch("flow.runner.write_history", return_value=tmp_path / "history.md"), \
             patch("flow.runner.send_status", new_callable=AsyncMock), \
             patch("flow.runner.strip_files_line", return_value=("resp", [])):
            from flow.runner import run_if_flow
            await run_if_flow(
                request_data={"messages": [{"role": "user", "content": "Think"}]},
                http_client=AsyncMock(), cache_key="k1", context_id="c1")
        assert len(captured) == 1
        kw = captured[0]
        assert "run_id" not in kw
        assert "response_filename" not in kw
        assert "status_filename" not in kw

class TestTechnicalReviewPromptFString:
    @pytest.mark.asyncio
    async def test_review_prompt_contains_actual_filename(self, tmp_path):
        plan = _make_ifplan(interaction_type="technical", specialist="general")
        run_id = "run-rev-42"
        review_filename = f"review.task.t.run.{run_id}.md"
        mock_result = MagicMock(returncode=0, stdout="", stderr="")
        review_prompts = []
        async def capture(**kwargs):
            if kwargs.get("agent") == "planner":
                review_prompts.append(kwargs.get("prompt", ""))
            return mock_result
        with patch("flow.runner.write_opencode_config", return_value=tmp_path / ".if" / "cfg.json"), \
             patch("flow.runner.run_opencode", new_callable=AsyncMock, side_effect=capture), \
             patch("flow.runner._artifact_refs", return_value=[]), \
             patch("flow.runner.send_status", new_callable=AsyncMock):
            rf = f"response.task.t.run.{run_id}.md"
            (tmp_path / rf).write_text("resp")
            from flow.runner import _run_technical
            await _run_technical(plan, tmp_path, "ctx", run_id=run_id, response_filename=rf, review_filename=review_filename)
        assert len(review_prompts) >= 1
        assert review_filename in review_prompts[0]
        assert "{_review_filename}" not in review_prompts[0]

    @pytest.mark.asyncio
    async def test_retry_loop_reads_correct_review_file(self, tmp_path):
        plan = _make_ifplan(interaction_type="technical", specialist="general")
        run_id = "run-retry-55"
        rf = f"response.task.t.run.{run_id}.md"
        rv = f"review.task.t.run.{run_id}.md"
        review_path = tmp_path / rv
        calls = {"n": 0}
        async def fake_run(**kwargs):
            calls["n"] += 1
            if kwargs.get("agent") == "planner":
                review_path.write_text("RETRY\nNeed more")
            else:
                (tmp_path / rf).write_text("fixed")
            return MagicMock(returncode=0, stdout="", stderr="")
        with patch("flow.runner.write_opencode_config", return_value=tmp_path / ".if" / "cfg.json"), \
             patch("flow.runner.run_opencode", new_callable=AsyncMock, side_effect=fake_run), \
             patch("flow.runner._artifact_refs", return_value=[]), \
             patch("flow.runner.send_status", new_callable=AsyncMock):
            from flow.runner import _run_technical
            content, _ = await _run_technical(plan, tmp_path, "ctx", run_id=run_id, response_filename=rf, review_filename=rv)
        assert calls["n"] == 3
        assert content == "fixed"

class TestOutboundIdempotencyKey:
    @pytest.mark.asyncio
    async def test_social_response_key_stable(self):
        from channels.decision_applier import _enqueue_message
        store = MagicMock()
        captured = []
        store.put_outbound_message = AsyncMock(side_effect=lambda m: captured.append(m) or True)
        with patch("channels.outbound_queue.schedule_drain"):
            await _enqueue_message(store=store, channel_id="c1", conversation_id="cv1", msg_type="social_response", content="hi", batch_id="b1", intent_id="i1")
            await _enqueue_message(store=store, channel_id="c1", conversation_id="cv1", msg_type="social_response", content="hi", batch_id="b1", intent_id="i1")
        assert captured[0].idempotency_key == captured[1].idempotency_key
        assert captured[0].idempotency_key == "b1:i1:social_response"
        assert captured[0].outbound_id != captured[1].outbound_id

    @pytest.mark.asyncio
    async def test_task_completed_scoped_to_task(self):
        from channels.decision_applier import _enqueue_message
        store = MagicMock()
        captured = []
        store.put_outbound_message = AsyncMock(side_effect=lambda m: captured.append(m) or True)
        with patch("channels.outbound_queue.schedule_drain"):
            await _enqueue_message(store=store, channel_id="c1", conversation_id="cv1", msg_type="task_completed", content="done", task_id="task-abc", batch_id="b1", intent_id="i1")
            await _enqueue_message(store=store, channel_id="c1", conversation_id="cv1", msg_type="task_completed", content="done", task_id="task-abc", batch_id="b2", intent_id="i2")
        assert captured[0].idempotency_key == captured[1].idempotency_key
        assert captured[0].idempotency_key == "task-abc:task_completed"

    @pytest.mark.asyncio
    async def test_task_failed_scoped_to_task(self):
        from channels.decision_applier import _enqueue_message
        store = MagicMock()
        captured = []
        store.put_outbound_message = AsyncMock(side_effect=lambda m: captured.append(m) or True)
        with patch("channels.outbound_queue.schedule_drain"):
            await _enqueue_message(store=store, channel_id="c1", conversation_id="cv1", msg_type="task_failed", content="err", task_id="task-xyz")
        assert captured[0].idempotency_key == "task-xyz:task_failed"

    @pytest.mark.asyncio
    async def test_key_has_no_random_component(self):
        from channels.decision_applier import _enqueue_message
        store = MagicMock()
        captured = []
        store.put_outbound_message = AsyncMock(side_effect=lambda m: captured.append(m) or True)
        with patch("channels.outbound_queue.schedule_drain"):
            for _ in range(3):
                await _enqueue_message(store=store, channel_id="c1", conversation_id="cv1", msg_type="clarifying_question", content="?", batch_id="b1", intent_id="i1")
        keys = [m.idempotency_key for m in captured]
        assert len(set(keys)) == 1
        assert keys[0] == "b1:i1:clarifying_question"

class TestSynthesizeHandoffsMarkerPlumbing:
    @pytest.mark.asyncio
    async def test_synthesize_handoffs_wires_config_and_marker(self, tmp_path):
        plan = _make_ifplan(specialist="coder")
        run_id = "synth-run-77"
        rf = f"response.task.t.run.{run_id}.md"
        expected_config = tmp_path / ".if" / f"opencode.run.{run_id}.json"
        captured = {}
        async def capture(**kwargs):
            captured.update(kwargs)
            (tmp_path / rf).write_text("synthesized")
            return MagicMock(returncode=0, stdout="", stderr="")
        with patch("flow.runner.write_opencode_config", return_value=expected_config), \
             patch("flow.runner.run_opencode", new_callable=AsyncMock, side_effect=capture), \
             patch("flow.runner.send_status", new_callable=AsyncMock):
            from flow.runner import _synthesize_handoffs
            await _synthesize_handoffs(
                plan=plan, session_dir=tmp_path, runtime_context="ctx",
                primary="primary", child_outputs=["child1"],
                uploaded_files=None, run_id=run_id, response_filename=rf)
        assert captured.get("config_path") == expected_config
        assert captured.get("run_id") == run_id
        marker = captured.get("session_marker_path")
        assert marker is not None
        assert run_id in str(marker)
        assert ".session" in str(marker)
