"""Tests for Phase 6 task worker and per-run file isolation."""
import sys
from pathlib import Path

APP_SRC = str(Path(__file__).resolve().parent.parent / "app" / "src")
if APP_SRC not in sys.path:
    sys.path.insert(0, APP_SRC)

import pytest
from channels.execution_models import OpenCodeRunRecord, ImplementationTask
from channels.task_worker import _per_run_filenames


class TestPerRunFilenames:
    def test_response_filename_format(self):
        result = _per_run_filenames("task-1", "run-1")
        assert result["response_filename"] == "response.task.task-1.run.run-1.md"

    def test_review_filename_format(self):
        result = _per_run_filenames("task-1", "run-1")
        assert result["review_filename"] == "review.task.task-1.run.run-1.md"

    def test_status_filename_format(self):
        result = _per_run_filenames("task-1", "run-1")
        assert result["status_filename"] == "status.task.task-1.run.run-1.log"

    def test_different_tasks_different_filenames(self):
        t1 = _per_run_filenames("task-1", "run-1")
        t2 = _per_run_filenames("task-2", "run-2")
        assert t1["response_filename"] != t2["response_filename"]
        assert t1["review_filename"] != t2["review_filename"]
        assert t1["status_filename"] != t2["status_filename"]

    def test_same_task_different_runs_different_filenames(self):
        r1 = _per_run_filenames("task-1", "run-1")
        r2 = _per_run_filenames("task-1", "run-2")
        assert r1["response_filename"] != r2["response_filename"]

    def test_uuid_format_filenames(self):
        task_id = "a" * 36
        run_id = "b" * 36
        result = _per_run_filenames(task_id, run_id)
        assert task_id in result["response_filename"]
        assert run_id in result["response_filename"]


class TestOpenCodeRunRecord:
    def test_run_record_defaults(self):
        record = OpenCodeRunRecord(run_id="r1")
        assert record.run_id == "r1"
        assert record.channel_id is None
        assert record.task_id is None
        assert record.batch_id is None
        assert record.kind == "planner"
        assert record.status == "running"
        assert record.returncode is None
        assert record.error is None
        assert record.config_path is None
        assert record.session_marker_path is None

    def test_run_record_with_task(self):
        record = OpenCodeRunRecord(
            run_id="r1",
            channel_id="ch1",
            task_id="t1",
            batch_id="b1",
            kind="implementer",
            agent="coder",
            model="model-1",
            status="running",
            started_at="2025-01-01T00:00:00Z",
            session_dir="/tmp/ws",
            config_path="/tmp/.if/opencode.run.r1.json",
            session_marker_path="/tmp/.if/opencode-coder.run.r1.session",
            history_path="/tmp/ws/history.md",
            plan_path="/tmp/ws/plan.task.t1.run.r1.md",
            response_path="/tmp/ws/response.task.t1.run.r1.md",
            status_path="/tmp/.if/status.task.t1.run.r1.log",
        )
        assert record.kind == "implementer"
        assert record.config_path == "/tmp/.if/opencode.run.r1.json"
        assert record.session_marker_path == "/tmp/.if/opencode-coder.run.r1.session"


class TestWriteOpencodeConfigRunId:
    def test_config_path_without_run_id(self):
        from pathlib import Path
        from flow.opencode_config import write_opencode_config
        import tempfile
        import os

        with tempfile.TemporaryDirectory() as tmp:
            session_dir = Path(tmp)
            path = write_opencode_config(session_dir, tool_names=[], mcp_servers=[])
            assert path == session_dir / "opencode.json"
            assert path.exists()

    def test_config_path_with_run_id(self):
        from pathlib import Path
        from flow.opencode_config import write_opencode_config
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            session_dir = Path(tmp)
            path = write_opencode_config(session_dir, tool_names=[], mcp_servers=[], run_id="run-abc")
            assert path == session_dir / ".if" / "opencode.run.run-abc.json"
            assert path.exists()
            assert not (session_dir / "opencode.json").exists()


class TestRunnerPerRunParams:
    def test_status_file_default(self):
        from pathlib import Path
        from flow.runner import _status_file
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = _status_file(Path(tmp))
            assert path.name == "status.log"

    def test_status_file_custom(self):
        from pathlib import Path
        from flow.runner import _status_file
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = _status_file(Path(tmp), filename="status.task.t1.run.r1.log")
            assert path.name == "status.task.t1.run.r1.log"

    def test_domain_prompt_default_response(self):
        from flow.runner import _domain_prompt
        from flow.plan import fallback_plan

        plan = fallback_plan(
            prompt="test",
            selected_model="m1",
            specialist="general",
            interaction_type="social",
        )
        result = _domain_prompt(plan, "context")
        assert "response.md" in result

    def test_domain_prompt_custom_response(self):
        from flow.runner import _domain_prompt
        from flow.plan import fallback_plan

        plan = fallback_plan(
            prompt="test",
            selected_model="m1",
            specialist="general",
            interaction_type="social",
        )
        result = _domain_prompt(plan, "context", response_filename="response.task.t1.run.r1.md")
        assert "response.task.t1.run.r1.md" in result
        assert "response.md" not in result
