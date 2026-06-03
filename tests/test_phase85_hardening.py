"""Phase 8.5 correctness hardening tests."""
from __future__ import annotations
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List
from unittest.mock import MagicMock, patch
import pytest

APP_SRC = str(Path(__file__).resolve().parent.parent / "app" / "src")
if APP_SRC not in sys.path:
    sys.path.insert(0, APP_SRC)

import types as _types

def _stub_storage_modules():
    if "sqlmodel" not in sys.modules:
        _sm = _types.ModuleType("sqlmodel")
        class _Base:
            def __init_subclass__(cls, **kw): pass
        _sm.SQLModel = _Base
        _sm.Field = lambda *a, **kw: None
        sys.modules["sqlmodel"] = _sm
    if "storage.models" not in sys.modules:
        _m = _types.ModuleType("storage.models")
        class _WR: pass
        _m.WebhookRecord = _WR
        sys.modules["storage.models"] = _m
    if "num2words" not in sys.modules:
        _n = _types.ModuleType("num2words")
        _n.num2words = lambda n, **kw: str(n)
        sys.modules["num2words"] = _n

_stub_storage_modules()


@dataclass
class _FakeDirective:
    alpha: int
    beta: int
    content: str
    types: List[str]
    global_directive: bool = False
    active: bool = True
    label: str = ""
    version: int = 1


def _fd(alpha, beta, content, types, global_directive=False):
    return _FakeDirective(
        alpha=alpha, beta=beta, content=content, types=types,
        global_directive=global_directive,
    )


def _fmt(directives):
    return "\n".join(f"{d.alpha}-{d.beta} {d.content}" for d in directives)


def _make_ifplan(specialist="coder", model="deepseek/deepseek-v4-flash"):
    from flow.plan import IFPlan
    return IFPlan(
        intent_summary="test",
        interaction_type="domain",
        specialist=specialist,
        thinking_mode=False,
        selected_model=model,
        prompt="Do the task",
        raw="---\n---\nDo the task",
    )


class TestGlobalDirectiveDeduplicationInDomainPrompt:
    def _make_spec(self, directive_types):
        s = MagicMock()
        s.directive_types = directive_types
        s.tools = []
        s.mcp_servers = []
        s.description = "Coding specialist"
        s.template = None
        return s

    def _make_store(self, core_directives, specialist_directives):
        store = MagicMock()
        def side_effect(types):
            return list(core_directives) if "core" in types else list(specialist_directives)
        store.get_for_subagent.side_effect = side_effect
        store.format_directives.side_effect = _fmt
        return store

    def test_global_directive_appears_exactly_once_in_domain_prompt(self):
        global_d = _fd(1, 1, "GLOBAL_CONTENT_XYZ", ["core"], global_directive=True)
        spec_d = _fd(2, 1, "SPECIALIST_CONTENT_ABC", ["code"])
        store = self._make_store([global_d], [global_d, spec_d])
        spec = self._make_spec(["code"])

        with patch("storage.factory.get_directive_store", return_value=store), \
             patch("flow.runner._get_specialist", return_value=spec), \
             patch("agent.specialists.render_specialist_prompt", return_value="SPEC_PROMPT"), \
             patch("flow.runner._main_system_prompt", return_value="MAIN"), \
             patch("flow.runner._tool_protocol_block", return_value=""):
            from flow.runner import _domain_prompt
            prompt = _domain_prompt(_make_ifplan(), "ctx")

        count = prompt.count("GLOBAL_CONTENT_XYZ")
        assert count == 1, f"Global directive appeared {count} times; expected exactly 1"

    def test_specialist_only_directive_still_appears(self):
        global_d = _fd(1, 1, "GLOBAL_CONTENT", ["core"], global_directive=True)
        spec_d = _fd(2, 1, "SPECIALIST_ONLY_CONTENT", ["code"])
        store = self._make_store([global_d], [global_d, spec_d])
        spec = self._make_spec(["code"])

        def _render_with_directives(specialist, task, directives="", **kw):
            return f"SPEC:{directives}"

        with patch("storage.factory.get_directive_store", return_value=store), \
             patch("flow.runner._get_specialist", return_value=spec), \
             patch("agent.specialists.render_specialist_prompt", side_effect=_render_with_directives), \
             patch("flow.runner._main_system_prompt", return_value="MAIN"), \
             patch("flow.runner._tool_protocol_block", return_value=""):
            from flow.runner import _domain_prompt
            prompt = _domain_prompt(_make_ifplan(), "ctx")

        assert "GLOBAL_CONTENT" in prompt
        assert "SPECIALIST_ONLY_CONTENT" in prompt

    def test_no_duplication_when_no_global_directives(self):
        core_d = _fd(1, 1, "CORE_CONTENT", ["core"])
        spec_d = _fd(2, 1, "SPECIALIST_CONTENT", ["code"])
        store = self._make_store([core_d], [spec_d])
        spec = self._make_spec(["code"])

        def _render_with_directives(specialist, task, directives="", **kw):
            return f"SPEC:{directives}"

        with patch("storage.factory.get_directive_store", return_value=store), \
             patch("flow.runner._get_specialist", return_value=spec), \
             patch("agent.specialists.render_specialist_prompt", side_effect=_render_with_directives), \
             patch("flow.runner._main_system_prompt", return_value="MAIN"), \
             patch("flow.runner._tool_protocol_block", return_value=""):
            from flow.runner import _domain_prompt
            prompt = _domain_prompt(_make_ifplan(), "ctx")

        assert prompt.count("CORE_CONTENT") == 1
        assert prompt.count("SPECIALIST_CONTENT") == 1


class TestGlobalDirectiveInPlannerAndClassifier:
    def test_global_directive_appears_in_planner_prompt(self, tmp_path):
        global_d = _fd(1, 1, "GLOBAL_PLANNER_CONTENT", ["core"], global_directive=True)
        mock_store = MagicMock()
        mock_store.get_for_subagent.return_value = [global_d]
        mock_store.format_directives.side_effect = _fmt
        history_path = tmp_path / "history.md"
        history_path.write_text("## User\nhello\n")

        with patch("storage.factory.get_directive_store", return_value=mock_store), \
             patch("flow.runner._main_system_prompt", return_value="MAIN"):
            from flow.runner import _planner_prompt
            prompt = _planner_prompt(
                history_path=history_path,
                model_ids=["deepseek/deepseek-v4-flash"],
                model_selection_rules="",
                specialist_catalog="- coder: coding",
                runtime_context="ctx",
            )

        assert "GLOBAL_PLANNER_CONTENT" in prompt

    def test_global_directive_appears_in_batch_classifier_prompt(self, tmp_path):
        global_d = _fd(1, 1, "GLOBAL_CLASSIFIER_CONTENT", ["core"], global_directive=True)
        mock_store = MagicMock()
        mock_store.get_for_subagent.return_value = [global_d]
        mock_store.format_directives.side_effect = _fmt
        history_path = tmp_path / "history.md"
        history_path.write_text("## User\nhello\n")

        with patch("storage.factory.get_directive_store", return_value=mock_store), \
             patch("flow.batch_classifier._main_system_prompt", return_value="MAIN"):
            from flow.batch_classifier import batch_classifier_prompt
            prompt = batch_classifier_prompt(
                history_path=history_path,
                model_ids=["deepseek/deepseek-v4-flash"],
                model_selection_rules="",
                specialist_catalog="- coder: coding",
                runtime_context="ctx",
                batch_id="batch-001",
                candidate_source_message_ids=["msg-1"],
                active_tasks_summary="",
            )

        assert "GLOBAL_CLASSIFIER_CONTENT" in prompt


class TestDirectiveBlockDeduped:
    def test_deduped_excludes_specified_keys(self):
        d1 = _fd(1, 1, "CONTENT_D1", ["code"], global_directive=True)
        d2 = _fd(2, 1, "CONTENT_D2", ["code"])
        mock_store = MagicMock()
        mock_store.get_for_subagent.return_value = [d1, d2]
        mock_store.format_directives.side_effect = _fmt

        with patch("storage.factory.get_directive_store", return_value=mock_store):
            from flow.runner import _directive_block_deduped
            result = _directive_block_deduped(["code"], exclude_keys={(1, 1)})

        assert "CONTENT_D1" not in result
        assert "CONTENT_D2" in result

    def test_deduped_with_empty_exclude_includes_all(self):
        d1 = _fd(1, 1, "CONTENT_D1", ["code"], global_directive=True)
        d2 = _fd(2, 1, "CONTENT_D2", ["code"])
        mock_store = MagicMock()
        mock_store.get_for_subagent.return_value = [d1, d2]
        mock_store.format_directives.side_effect = _fmt

        with patch("storage.factory.get_directive_store", return_value=mock_store):
            from flow.runner import _directive_block_deduped
            result = _directive_block_deduped(["code"], exclude_keys=set())

        assert "CONTENT_D1" in result
        assert "CONTENT_D2" in result

    def test_core_directive_keys_returns_alpha_beta_set(self):
        d1 = _fd(1, 1, "C1", ["core"])
        d2 = _fd(2, 3, "C2", ["core"])
        mock_store = MagicMock()
        mock_store.get_for_subagent.return_value = [d1, d2]

        with patch("storage.factory.get_directive_store", return_value=mock_store):
            from flow.runner import _core_directive_keys
            keys = _core_directive_keys()

        assert (1, 1) in keys
        assert (2, 3) in keys
        assert len(keys) == 2

    def test_core_directive_keys_returns_empty_on_store_error(self):
        with patch("storage.factory.get_directive_store", side_effect=RuntimeError("unavailable")):
            from flow.runner import _core_directive_keys
            keys = _core_directive_keys()

        assert keys == set()


class TestTechnicalSynthesisPromptsStillParse:
    def test_technical_prompt_renders(self):
        from agent.prompts.loader import render_template
        result = render_template(
            "technical_prompt",
            response_filename="response.md",
            core_directives="CORE_CONTENT",
            runtime_context="ctx",
            plan_prompt="Build it",
        )
        assert "CORE_CONTENT" in result
        assert "response.md" in result

    def test_synthesis_prompt_renders(self):
        from agent.prompts.loader import render_template
        result = render_template(
            "synthesis_prompt",
            response_filename="response.md",
            core_directives="CORE_CONTENT",
            runtime_context="ctx",
            primary_output="primary",
            child_outputs="child",
        )
        assert "CORE_CONTENT" in result
        assert "response.md" in result

    def test_review_prompt_first_line_not_retry(self):
        from agent.prompts.loader import render_template
        result = render_template(
            "technical_review_prompt",
            review_filename="review.task.t1.run.r1.md",
        )
        first_line = result.strip().splitlines()[0].strip()
        assert first_line != "RETRY"
        assert "review.task.t1.run.r1.md" in result

    def test_retry_prompt_first_line_not_retry(self):
        from agent.prompts.loader import render_template
        review = "RETRY\nNeed changes."
        result = render_template(
            "technical_retry_prompt",
            technical_prompt="Build the thing.",
            review_content=review,
        )
        assert "Build the thing." in result
        assert result.strip().splitlines()[0].strip() != "RETRY"
