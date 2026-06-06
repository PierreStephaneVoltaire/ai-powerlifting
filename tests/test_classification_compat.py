"""Tests for flow.plan.parse_classification_text — kind/action compatibility validation.

Covers:
- Incompatible kind+action combinations are rejected
- Compatible kind+action combinations are accepted
- All KIND_ACTION_COMPAT entries are validated
"""
import json
import sys
from pathlib import Path

import pytest

APP_SRC = str(Path(__file__).resolve().parent.parent / "app" / "src")
if APP_SRC not in sys.path:
    sys.path.insert(0, APP_SRC)

from flow.plan import (
    ClassificationParseError,
    KIND_ACTION_COMPAT,
    VALID_CLASSIFIER_KINDS,
    VALID_CLASSIFIER_ACTIONS,
    parse_classification_text,
)


ELIGIBLE_MODELS = ["deepseek/deepseek-v4-flash"]
KNOWN_SPECIALISTS = {"coder", "scripter"}


def _make_classification_json(kind: str, action: str, **overrides) -> str:
    """Build a minimal valid classification JSON with one decision."""
    decision = {
        "intentId": "intent-1",
        "kind": kind,
        "action": action,
        "sourceMessageIds": ["msg-1"],
        "confidence": 0.9,
        "reason": "test",
        "needsPlanning": False,
    }
    decision.update(overrides)
    return json.dumps({
        "batchSummary": "test batch",
        "decisions": [decision],
    })


# --- Incompatible combinations ---

def test_task_with_append_to_active_rejected():
    """kind=task + action=append_to_active_implementation is incompatible."""
    text = _make_classification_json("task", "append_to_active_implementation")
    with pytest.raises(ClassificationParseError, match="action append_to_active_implementation incompatible with kind task"):
        parse_classification_text(text, ELIGIBLE_MODELS, KNOWN_SPECIALISTS)


def test_task_with_pivot_active_rejected():
    """kind=task + action=pivot_active_implementation is incompatible."""
    text = _make_classification_json("task", "pivot_active_implementation")
    with pytest.raises(ClassificationParseError, match="action pivot_active_implementation incompatible with kind task"):
        parse_classification_text(text, ELIGIBLE_MODELS, KNOWN_SPECIALISTS)


def test_task_with_cancel_active_rejected():
    """kind=task + action=cancel_active_implementation is incompatible."""
    text = _make_classification_json("task", "cancel_active_implementation")
    with pytest.raises(ClassificationParseError, match="action cancel_active_implementation incompatible with kind task"):
        parse_classification_text(text, ELIGIBLE_MODELS, KNOWN_SPECIALISTS)


def test_social_with_start_new_task_rejected():
    """kind=social + action=start_new_task is incompatible."""
    text = _make_classification_json("social", "start_new_task")
    with pytest.raises(ClassificationParseError, match="action start_new_task incompatible with kind social"):
        parse_classification_text(text, ELIGIBLE_MODELS, KNOWN_SPECIALISTS)


def test_social_with_append_to_active_rejected():
    """kind=social + action=append_to_active_implementation is incompatible."""
    text = _make_classification_json("social", "append_to_active_implementation")
    with pytest.raises(ClassificationParseError, match="action append_to_active_implementation incompatible with kind social"):
        parse_classification_text(text, ELIGIBLE_MODELS, KNOWN_SPECIALISTS)


def test_implementation_control_with_social_response_rejected():
    """kind=implementation_control + action=social_response is incompatible."""
    text = _make_classification_json("implementation_control", "social_response")
    with pytest.raises(ClassificationParseError, match="action social_response incompatible with kind implementation_control"):
        parse_classification_text(text, ELIGIBLE_MODELS, KNOWN_SPECIALISTS)


def test_implementation_control_with_start_new_task_rejected():
    """kind=implementation_control + action=start_new_task is incompatible."""
    text = _make_classification_json("implementation_control", "start_new_task")
    with pytest.raises(ClassificationParseError, match="action start_new_task incompatible with kind implementation_control"):
        parse_classification_text(text, ELIGIBLE_MODELS, KNOWN_SPECIALISTS)


def test_clarification_with_social_response_rejected():
    """kind=clarification + action=social_response is incompatible."""
    text = _make_classification_json("clarification", "social_response")
    with pytest.raises(ClassificationParseError, match="action social_response incompatible with kind clarification"):
        parse_classification_text(text, ELIGIBLE_MODELS, KNOWN_SPECIALISTS)


# --- Compatible combinations ---

def test_social_with_social_response_accepted():
    """kind=social + action=social_response is valid."""
    text = _make_classification_json("social", "social_response", socialResponseText="Hi there!")
    result = parse_classification_text(text, ELIGIBLE_MODELS, KNOWN_SPECIALISTS)
    assert len(result.decisions) == 1
    assert result.decisions[0].kind == "social"
    assert result.decisions[0].action == "social_response"


def test_task_with_start_new_task_accepted():
    """kind=task + action=start_new_task is valid."""
    text = _make_classification_json("task", "start_new_task")
    result = parse_classification_text(text, ELIGIBLE_MODELS, KNOWN_SPECIALISTS)
    assert len(result.decisions) == 1
    assert result.decisions[0].kind == "task"
    assert result.decisions[0].action == "start_new_task"


def test_implementation_control_with_append_accepted():
    """kind=implementation_control + action=append_to_active_implementation is valid."""
    text = _make_classification_json(
        "implementation_control",
        "append_to_active_implementation",
        targetTaskId="task-1",
    )
    result = parse_classification_text(text, ELIGIBLE_MODELS, KNOWN_SPECIALISTS)
    assert len(result.decisions) == 1
    assert result.decisions[0].kind == "implementation_control"
    assert result.decisions[0].action == "append_to_active_implementation"


def test_clarification_with_ask_clarifying_target_accepted():
    """kind=clarification + action=ask_clarifying_target is valid."""
    text = _make_classification_json("clarification", "ask_clarifying_target")
    result = parse_classification_text(text, ELIGIBLE_MODELS, KNOWN_SPECIALISTS)
    assert len(result.decisions) == 1
    assert result.decisions[0].kind == "clarification"
    assert result.decisions[0].action == "ask_clarifying_target"


def test_ignore_kind_with_ignore_action_accepted():
    """kind=ignore + action=ignore is valid."""
    text = _make_classification_json("ignore", "ignore")
    result = parse_classification_text(text, ELIGIBLE_MODELS, KNOWN_SPECIALISTS)
    assert len(result.decisions) == 1
    assert result.decisions[0].kind == "ignore"
    assert result.decisions[0].action == "ignore"


def test_any_kind_with_ignore_action_accepted():
    """action=ignore is valid for all kinds."""
    for kind in VALID_CLASSIFIER_KINDS:
        text = _make_classification_json(kind, "ignore")
        result = parse_classification_text(text, ELIGIBLE_MODELS, KNOWN_SPECIALISTS)
        assert len(result.decisions) == 1


# --- Exhaustive compat check ---

def test_all_compat_entries_match_knowledge():
    """Verify KIND_ACTION_COMPAT matches the documented rules."""
    assert KIND_ACTION_COMPAT["social"] == {"social_response", "ignore"}
    assert KIND_ACTION_COMPAT["task"] == {"start_new_task", "ignore"}
    assert KIND_ACTION_COMPAT["implementation_control"] == {
        "append_to_active_implementation",
        "pivot_active_implementation",
        "cancel_active_implementation",
        "queue_on_active_implementation",
        "await_instruction_for_active_implementation",
        "ignore",
    }
    assert KIND_ACTION_COMPAT["clarification"] == {"ask_clarifying_target", "ignore"}
    assert KIND_ACTION_COMPAT["ignore"] == {"ignore"}
