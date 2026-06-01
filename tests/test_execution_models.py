"""Unit tests for channels/execution_models.py — Phase 0.

Covers:
- floats_to_decimals: recursive float-to-Decimal conversion for nested
  decision payloads, including edge cases (None, empty, mixed types).
- get_instance_identity: hostname/uuid identity uniqueness and format.
- Dataclass construction and field defaults for all models.
"""
import sys
from pathlib import Path
from decimal import Decimal

# Ensure app/src is on the path
APP_SRC = str(Path(__file__).resolve().parent.parent / "app" / "src")
if APP_SRC not in sys.path:
    sys.path.insert(0, APP_SRC)

from channels.execution_models import (
    floats_to_decimals,
    get_instance_identity,
    ChannelClassificationState,
    ClassificationBatch,
    ClassifierDecision,
    IntentRecord,
    ImplementationTask,
    OpenCodeRunRecord,
    DiscordOutboundMessage,
)


# ======================================================================
# floats_to_decimals
# ======================================================================

def test_floats_to_decimals_top_level_float():
    assert floats_to_decimals(1.5) == Decimal("1.5")
    assert floats_to_decimals(0.0) == Decimal("0.0")
    assert floats_to_decimals(-3.14) == Decimal("-3.14")


def test_floats_to_decimals_int_unchanged():
    assert floats_to_decimals(42) == 42
    assert floats_to_decimals(0) == 0


def test_floats_to_decimals_string_unchanged():
    assert floats_to_decimals("hello") == "hello"
    assert floats_to_decimals("3.14") == "3.14"


def test_floats_to_decimals_none_unchanged():
    assert floats_to_decimals(None) is None


def test_floats_to_decimals_bool_unchanged():
    assert floats_to_decimals(True) is True
    assert floats_to_decimals(False) is False


def test_floats_to_decimals_simple_dict():
    result = floats_to_decimals({"confidence": 0.85, "name": "test"})
    assert result == {"confidence": Decimal("0.85"), "name": "test"}


def test_floats_to_decimals_nested_dict():
    payload = {
        "confidence": 0.92,
        "nested": {
            "score": 0.7,
            "label": "high",
            "inner": {
                "ratio": 3.14159,
            },
        },
        "count": 5,
    }
    result = floats_to_decimals(payload)
    assert result["confidence"] == Decimal("0.92")
    assert result["nested"]["score"] == Decimal("0.7")
    assert result["nested"]["label"] == "high"
    assert result["nested"]["inner"]["ratio"] == Decimal("3.14159")
    assert result["count"] == 5


def test_floats_to_decimals_list():
    result = floats_to_decimals([1.0, 2.5, "text", None, 3])
    assert result == [Decimal("1.0"), Decimal("2.5"), "text", None, 3]


def test_floats_to_decimals_nested_list_in_dict():
    payload = {
        "scores": [0.1, 0.2, 0.3],
        "labels": ["a", "b"],
    }
    result = floats_to_decimals(payload)
    assert result["scores"] == [Decimal("0.1"), Decimal("0.2"), Decimal("0.3")]
    assert result["labels"] == ["a", "b"]


def test_floats_to_decimals_dict_in_list():
    payload = [
        {"val": 1.5, "id": "a"},
        {"val": 2.5, "id": "b"},
    ]
    result = floats_to_decimals(payload)
    assert result[0]["val"] == Decimal("1.5")
    assert result[1]["val"] == Decimal("2.5")
    assert result[0]["id"] == "a"


def test_floats_to_decimals_empty_structures():
    assert floats_to_decimals({}) == {}
    assert floats_to_decimals([]) == []


def test_floats_to_decimals_classifier_decision_payload():
    """Simulate a realistic ClassifierDecision-like nested payload with floats."""
    payload = {
        "intentId": "intent-001",
        "kind": "social",
        "action": "social_response",
        "sourceMessageIds": ["msg1", "msg2"],
        "targetTaskId": None,
        "confidence": 0.88,
        "reason": "Greeting detected",
        "needsPlanning": False,
        "selectedSpecialist": None,
        "selectedModel": None,
        "socialResponseText": "Hey there!",
        "responseText": None,
        "plannerIntent": {
            "title": "Greeting",
            "intent": "social_greeting",
            "summary": "User greeted the bot",
            "currentGoal": "Respond to greeting",
            "acceptanceCriteria": [],
            "constraints": [],
            "keywords": ["hello", "greet"],
            "entities": [],
            "likelyFiles": [],
            "nonGoals": [],
        },
        "topicUpdate": None,
        "conflict": None,
    }
    result = floats_to_decimals(payload)
    # Only confidence should be converted; everything else stays as-is
    assert result["confidence"] == Decimal("0.88")
    assert result["intentId"] == "intent-001"
    assert result["kind"] == "social"
    assert result["sourceMessageIds"] == ["msg1", "msg2"]
    assert result["needsPlanning"] is False
    assert result["plannerIntent"]["title"] == "Greeting"


def test_floats_to_decimals_batch_with_multiple_decisions():
    """Simulate a full classification batch payload with multiple decisions."""
    batch = {
        "batchSummary": "Two intents: social + task",
        "decisions": [
            {
                "intentId": "intent-001",
                "kind": "social",
                "action": "social_response",
                "confidence": 0.95,
                "reason": "Simple greeting",
                "needsPlanning": False,
            },
            {
                "intentId": "intent-002",
                "kind": "task",
                "action": "start_new_task",
                "confidence": 0.82,
                "reason": "Code request detected",
                "needsPlanning": True,
                "selectedSpecialist": "coder",
                "selectedModel": "deepseek/deepseek-v4-flash",
            },
        ],
    }
    result = floats_to_decimals(batch)
    assert result["decisions"][0]["confidence"] == Decimal("0.95")
    assert result["decisions"][1]["confidence"] == Decimal("0.82")
    assert result["decisions"][1]["selectedSpecialist"] == "coder"
    # Non-float values unchanged
    assert result["batchSummary"] == "Two intents: social + task"


def test_floats_to_decimals_no_mutation():
    """The original dict should not be mutated by floats_to_decimals."""
    original = {"a": 1.5, "b": [2.0, 3.0]}
    result = floats_to_decimals(original)
    assert original["a"] == 1.5  # Still a float
    assert original["b"][0] == 2.0  # Still a float
    assert result["a"] == Decimal("1.5")
    assert result["b"][0] == Decimal("2.0")


def test_floats_to_decimals_deeply_nested():
    """5 levels of nesting with floats at each level."""
    payload = {"l1": {"l2": {"l3": {"l4": {"l5": 0.123}}}}}
    result = floats_to_decimals(payload)
    assert result["l1"]["l2"]["l3"]["l4"]["l5"] == Decimal("0.123")


def test_floats_to_decimals_mixed_numeric_types():
    """Ensure ints stay int, floats become Decimal."""
    payload = {
        "int_val": 42,
        "float_val": 42.0,
        "nested": {"int_val": 100, "float_val": 100.5},
        "list": [1, 2.0, 3, 4.5],
    }
    result = floats_to_decimals(payload)
    assert result["int_val"] == 42
    assert isinstance(result["int_val"], int)
    assert result["float_val"] == Decimal("42.0")
    assert isinstance(result["float_val"], Decimal)
    assert result["nested"]["int_val"] == 100
    assert result["nested"]["float_val"] == Decimal("100.5")
    assert result["list"] == [1, Decimal("2.0"), 3, Decimal("4.5")]


# ======================================================================
# get_instance_identity
# ======================================================================

def test_instance_identity_format():
    identity = get_instance_identity()
    assert "/" in identity, "Identity must contain hostname/uuid separator"
    hostname, uuid_part = identity.split("/", 1)
    assert len(hostname) > 0, "Hostname part must not be empty"
    assert len(uuid_part) == 36, "UUID part must be standard 36-char format"


def test_instance_identity_uniqueness():
    id1 = get_instance_identity()
    id2 = get_instance_identity()
    assert id1 != id2, "Each call must produce a unique identity (different UUID)"


# ======================================================================
# Dataclass construction
# ======================================================================

def test_channel_classification_state_defaults():
    state = ChannelClassificationState(
        channel_id="123",
        status="idle",
        pending=False,
        dirty=False,
        debounce_until=None,
        batch_first_event_at=None,
        max_wait_until=None,
        latest_observed_event_at=None,
        latest_observed_message_id=None,
        latest_observed_edit_at=None,
        last_classifier_started_at=None,
        last_classifier_finished_at=None,
        active_classifier_run_id=None,
        classifier_lock_owner=None,
        classifier_lock_expires_at=None,
        last_classified_message_id=None,
        last_classified_at=None,
        pending_event_count=0,
        version=1,
        updated_at="2025-01-01T00:00:00Z",
    )
    assert state.channel_id == "123"
    assert state.status == "idle"
    assert state.pending is False
    assert state.dirty is False
    assert state.pending_event_count == 0
    assert state.version == 1


def test_classification_batch_defaults():
    batch = ClassificationBatch(
        batch_id="b1",
        channel_id="123",
        classifier_run_id="r1",
        started_at="2025-01-01T00:00:00Z",
        completed_at=None,
        history_fetched_at=None,
        history_oldest_message_id=None,
        history_newest_message_id=None,
        cursor_before_message_id=None,
        cursor_after_message_id=None,
        edited_since=None,
    )
    assert batch.status == "running"
    assert batch.candidate_source_message_ids == []
    assert batch.decisions == []
    assert batch.version == 1
    assert batch.ttl is None


def test_classifier_decision_defaults():
    decision = ClassifierDecision(
        intent_id="i1",
        kind="social",
        action="social_response",
    )
    assert decision.confidence == 0.0
    assert decision.source_message_ids == []
    assert decision.needs_planning is False
    assert decision.selected_specialist is None
    assert decision.planner_intent is None
    assert decision.conflict is None


def test_intent_record_defaults():
    record = IntentRecord(
        intent_id="i1",
        batch_id="b1",
        channel_id="123",
        action="social_response",
        kind="social",
    )
    assert record.status == "pending"
    assert record.source_message_ids == []
    assert record.ttl is None


def test_implementation_task_defaults():
    task = ImplementationTask(
        task_id="t1",
        channel_id="123",
        conversation_id="conv1",
        status="implementing",
        root_discord_message_id="msg1",
    )
    assert task.related_discord_message_ids == []
    assert task.topic == {}
    assert task.queued_message_refs == []
    assert task.control == {}
    assert task.version == 1


def test_opencode_run_record_defaults():
    record = OpenCodeRunRecord(
        run_id="r1",
    )
    assert record.kind == "planner"
    assert record.status == "running"
    assert record.channel_id is None
    assert record.ttl is None


def test_discord_outbound_message_defaults():
    msg = DiscordOutboundMessage(
        outbound_id="o1",
        channel_id="123",
        conversation_id="conv1",
    )
    assert msg.type == "social_response"
    assert msg.priority == 5
    assert msg.status == "queued"
    assert msg.attachments == []
    assert msg.idempotency_key == ""
    assert msg.ttl is None
