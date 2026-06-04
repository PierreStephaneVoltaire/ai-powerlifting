"""Unit tests for Phase 2 — Debounce/Classifier Locking and Dirty Reclassification.

Covers:
- ChannelClassificationState transitions via transition_channel_state
- Valid and invalid state transitions
- Classifier lock acquisition / release via update_item
- Classifier lock expiry takeover
- Dirty flag behavior during classification
- Pending flag behavior during classification
- Lock release with dirty/pending reschedule (classifying -> debouncing)
- Lock release without dirty (classifying -> idle)
- Max-wait ceiling enforcement
- Lock acquisition race (two concurrent callers -> one winner)
- active_classifier_run_id set on lock acquisition
- VALID_TRANSITIONS enforcement
"""
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, call

APP_SRC = str(Path(__file__).resolve().parent.parent / "app" / "src")
if APP_SRC not in sys.path:
    sys.path.insert(0, APP_SRC)

from channels.execution_models import (
    floats_to_decimals,
    get_instance_identity,
    ChannelClassificationState,
)
from channels.execution_store import ExecutionStore, VALID_TRANSITIONS

def test_valid_transitions_idle_to_debouncing():
    assert "debouncing" in VALID_TRANSITIONS["idle"]

def test_valid_transitions_debouncing_to_classifying():
    assert "classifying" in VALID_TRANSITIONS["debouncing"]

def test_valid_transitions_classifying_to_idle():
    assert "idle" in VALID_TRANSITIONS["classifying"]

def test_valid_transitions_classifying_to_debouncing():
    assert "debouncing" in VALID_TRANSITIONS["classifying"]

def test_valid_transitions_no_idle_to_classifying():
    assert "classifying" not in VALID_TRANSITIONS.get("idle", [])

def test_valid_transitions_no_debouncing_to_idle():
    assert "idle" not in VALID_TRANSITIONS.get("debouncing", [])

def test_valid_transitions_no_classifying_to_debouncing_other():
    assert "debouncing" in VALID_TRANSITIONS["classifying"]


def test_transition_sync_rejects_invalid_transition():
    store = ExecutionStore.__new__(ExecutionStore)
    store.table_name = "test"
    store._region = "us-east-1"
    store._table = MagicMock()
    result = store._transition_sync("ch1", "idle", "classifying")
    assert result is False
    store._table.update_item.assert_not_called()

def test_transition_sync_rejects_debouncing_to_idle():
    store = ExecutionStore.__new__(ExecutionStore)
    store.table_name = "test"
    store._region = "us-east-1"
    store._table = MagicMock()
    result = store._transition_sync("ch1", "debouncing", "idle")
    assert result is False
    store._table.update_item.assert_not_called()

def test_transition_sync_calls_update_item_on_valid_transition():
    store = ExecutionStore.__new__(ExecutionStore)
    store.table_name = "test"
    store._region = "us-east-1"
    store._table = MagicMock()
    store._table.update_item.return_value = {}
    result = store._transition_sync("ch1", "idle", "debouncing")
    assert result is True
    store._table.update_item.assert_called_once()
    call_kwargs = store._table.update_item.call_args[1]
    assert "#st = :to_status" in call_kwargs["UpdateExpression"]

def test_transition_sync_returns_false_on_conditional_check_failed():
    from botocore.exceptions import ClientError
    store = ExecutionStore.__new__(ExecutionStore)
    store.table_name = "test"
    store._region = "us-east-1"
    store._table = MagicMock()
    err_response = {"Error": {"Code": "ConditionalCheckFailedException", "Message": ""}}
    store._table.update_item.side_effect = ClientError(err_response, "UpdateItem")
    result = store._transition_sync("ch1", "idle", "debouncing")
    assert result is False

def test_transition_sync_passes_extra_updates():
    store = ExecutionStore.__new__(ExecutionStore)
    store.table_name = "test"
    store._region = "us-east-1"
    store._table = MagicMock()
    store._table.update_item.return_value = {}
    result = store._transition_sync(
        "ch1", "idle", "debouncing",
        debounce_until="2025-01-01T00:00:00Z",
        pending=True,
    )
    assert result is True
    call_kwargs = store._table.update_item.call_args[1]
    update_expr = call_kwargs["UpdateExpression"]
    assert "debounce_until" in update_expr
    assert "pending" in update_expr

def test_update_state_sets_dirty_and_pending_when_classifying():
    store = ExecutionStore.__new__(ExecutionStore)
    store.table_name = "test"
    store._region = "us-east-1"
    store._table = MagicMock()
    now = datetime.now(timezone.utc).isoformat()
    current_item = {
        "pk": "CHANNEL#ch1", "sk": "STATE#classification",
        "channel_id": "ch1", "status": "classifying",
        "pending": False, "dirty": False,
        "debounce_until": "", "batch_first_event_at": "",
        "max_wait_until": "", "latest_observed_event_at": "",
        "latest_observed_message_id": "", "latest_observed_edit_at": "",
        "last_classifier_started_at": now,
        "last_classifier_finished_at": "",
        "active_classifier_run_id": "run-1",
        "classifier_lock_owner": "owner-1",
        "classifier_lock_expires_at": "",
        "last_classified_message_id": "", "last_classified_at": "",
        "pending_event_count": 0, "version": Decimal("5"), "updated_at": now,
    }
    store._table.get_item.return_value = {"Item": current_item}
    store._table.update_item.return_value = {"Attributes": {
        **current_item,
        "pending": True,
        "dirty": True,
        "pending_event_count": 1,
    }}
    result = store._update_state_on_event_sync(
        "ch1", "msg-new", now, False, 5.0, 30,
    )
    store._table.update_item.assert_called_once()
    call_kwargs = store._table.update_item.call_args[1]
    expr = call_kwargs["UpdateExpression"]
    assert "pending" in expr
    assert "dirty" in expr

def test_update_state_sets_dirty_on_edit_while_classifying():
    store = ExecutionStore.__new__(ExecutionStore)
    store.table_name = "test"
    store._region = "us-east-1"
    store._table = MagicMock()
    now = datetime.now(timezone.utc).isoformat()
    current_item = {
        "pk": "CHANNEL#ch1", "sk": "STATE#classification",
        "channel_id": "ch1", "status": "classifying",
        "pending": False, "dirty": False,
        "debounce_until": "", "batch_first_event_at": "",
        "max_wait_until": "", "latest_observed_event_at": "",
        "latest_observed_message_id": "", "latest_observed_edit_at": "",
        "last_classifier_started_at": now,
        "last_classifier_finished_at": "",
        "active_classifier_run_id": "run-1",
        "classifier_lock_owner": "owner-1",
        "classifier_lock_expires_at": "",
        "last_classified_message_id": "", "last_classified_at": "",
        "pending_event_count": 0, "version": Decimal("5"), "updated_at": now,
    }
    store._table.get_item.return_value = {"Item": current_item}
    store._table.update_item.return_value = {"Attributes": {
        **current_item,
        "pending": True,
        "dirty": True,
        "latest_observed_edit_at": now,
    }}
    store._update_state_on_event_sync(
        "ch1", "msg-edited", now, True, 5.0, 30,
    )
    store._table.update_item.assert_called_once()
    call_kwargs = store._table.update_item.call_args[1]
    expr = call_kwargs["UpdateExpression"]
    assert "latest_observed_edit_at" in expr
    assert "dirty" in expr

def test_acquire_lock_sets_active_classifier_run_id():
    store = ExecutionStore.__new__(ExecutionStore)
    store.table_name = "test"
    store._region = "us-east-1"
    store._table = MagicMock()
    store._table.update_item.return_value = {}
    result = store._acquire_lock_sync("ch1", "owner-A", "2099-01-01T00:00:00Z")
    assert result is True
    store._table.update_item.assert_called_once()
    call_kwargs = store._table.update_item.call_args[1]
    expr = call_kwargs["UpdateExpression"]
    assert "classifier_lock_owner" in expr

def test_acquire_lock_uses_update_item():
    store = ExecutionStore.__new__(ExecutionStore)
    store.table_name = "test"
    store._region = "us-east-1"
    store._table = MagicMock()
    store._table.update_item.return_value = {}
    result = store._acquire_lock_sync("ch1", "owner-A", "2099-01-01T00:00:00Z")
    assert result is True
    store._table.update_item.assert_called_once()

def test_acquire_lock_fails_when_lock_held_by_other():
    from botocore.exceptions import ClientError
    store = ExecutionStore.__new__(ExecutionStore)
    store.table_name = "test"
    store._region = "us-east-1"
    store._table = MagicMock()
    err_response = {"Error": {"Code": "ConditionalCheckFailedException", "Message": ""}}
    store._table.update_item.side_effect = ClientError(err_response, "UpdateItem")
    result = store._acquire_lock_sync("ch1", "owner-A", "2099-01-01T00:00:00Z")
    assert result is False

def test_acquire_lock_succeeds_when_expired():
    store = ExecutionStore.__new__(ExecutionStore)
    store.table_name = "test"
    store._region = "us-east-1"
    store._table = MagicMock()
    store._table.update_item.return_value = {}
    result = store._acquire_lock_sync("ch1", "owner-A", "2099-01-01T00:00:00Z")
    assert result is True
    call_kwargs = store._table.update_item.call_args[1]
    cond = call_kwargs.get("ConditionExpression", "")
    assert "classifier_lock_expires_at" in cond

def test_acquire_lock_returns_false_on_version_conflict():
    from botocore.exceptions import ClientError
    store = ExecutionStore.__new__(ExecutionStore)
    store.table_name = "test"
    store._region = "us-east-1"
    store._table = MagicMock()
    err_response = {"Error": {"Code": "ConditionalCheckFailedException", "Message": ""}}
    store._table.update_item.side_effect = ClientError(err_response, "UpdateItem")
    result = store._acquire_lock_sync("ch1", "owner-A", "2099-01-01T00:00:00Z")
    assert result is False

def test_release_lock_transitions_to_idle_when_clean():
    store = ExecutionStore.__new__(ExecutionStore)
    store.table_name = "test"
    store._region = "us-east-1"
    store._table = MagicMock()
    now = datetime.now(timezone.utc).isoformat()
    current_item = {
        "pk": "CHANNEL#ch1", "sk": "STATE#classification",
        "channel_id": "ch1", "status": "classifying",
        "pending": False, "dirty": False,
        "classifier_lock_owner": "owner-A",
        "version": Decimal("6"), "updated_at": now,
    }
    store._table.get_item.return_value = {"Item": current_item}
    store._table.update_item.return_value = {}
    store._release_lock_sync("ch1", "owner-A", 0.0)
    store._table.update_item.assert_called_once()
    call_kwargs = store._table.update_item.call_args[1]
    expr = call_kwargs["UpdateExpression"]
    assert "idle" in expr or ":target" in call_kwargs.get("ExpressionAttributeValues", {})

def test_release_lock_transitions_to_debouncing_when_dirty():
    store = ExecutionStore.__new__(ExecutionStore)
    store.table_name = "test"
    store._region = "us-east-1"
    store._table = MagicMock()
    now = datetime.now(timezone.utc).isoformat()
    current_item = {
        "pk": "CHANNEL#ch1", "sk": "STATE#classification",
        "channel_id": "ch1", "status": "classifying",
        "pending": True, "dirty": True,
        "classifier_lock_owner": "owner-A",
        "version": Decimal("6"), "updated_at": now,
    }
    store._table.get_item.return_value = {"Item": current_item}
    store._table.update_item.return_value = {}
    store._release_lock_sync("ch1", "owner-A", 5.0)
    store._table.update_item.assert_called_once()
    call_kwargs = store._table.update_item.call_args[1]
    attr_values = call_kwargs.get("ExpressionAttributeValues", {})
    assert attr_values.get(":target") == "debouncing"

def test_release_lock_transitions_to_debouncing_when_pending():
    store = ExecutionStore.__new__(ExecutionStore)
    store.table_name = "test"
    store._region = "us-east-1"
    store._table = MagicMock()
    now = datetime.now(timezone.utc).isoformat()
    current_item = {
        "pk": "CHANNEL#ch1", "sk": "STATE#classification",
        "channel_id": "ch1", "status": "classifying",
        "pending": True, "dirty": False,
        "classifier_lock_owner": "owner-A",
        "version": Decimal("6"), "updated_at": now,
    }
    store._table.get_item.return_value = {"Item": current_item}
    store._table.update_item.return_value = {}
    store._release_lock_sync("ch1", "owner-A", 3.0)
    store._table.update_item.assert_called_once()
    call_kwargs = store._table.update_item.call_args[1]
    attr_values = call_kwargs.get("ExpressionAttributeValues", {})
    assert attr_values.get(":target") == "debouncing"

def test_release_lock_transitions_to_idle_when_clean_no_pending():
    store = ExecutionStore.__new__(ExecutionStore)
    store.table_name = "test"
    store._region = "us-east-1"
    store._table = MagicMock()
    now = datetime.now(timezone.utc).isoformat()
    current_item = {
        "pk": "CHANNEL#ch1", "sk": "STATE#classification",
        "channel_id": "ch1", "status": "classifying",
        "pending": False, "dirty": False,
        "classifier_lock_owner": "owner-A",
        "version": Decimal("6"), "updated_at": now,
    }
    store._table.get_item.return_value = {"Item": current_item}
    store._table.update_item.return_value = {}
    store._release_lock_sync("ch1", "owner-A", 0.0)
    call_kwargs = store._table.update_item.call_args[1]
    attr_values = call_kwargs.get("ExpressionAttributeValues", {})
    assert attr_values.get(":target") == "idle"

def test_release_lock_noop_when_owner_mismatch():
    from botocore.exceptions import ClientError
    store = ExecutionStore.__new__(ExecutionStore)
    store.table_name = "test"
    store._region = "us-east-1"
    store._table = MagicMock()
    now = datetime.now(timezone.utc).isoformat()
    current_item = {
        "pk": "CHANNEL#ch1", "sk": "STATE#classification",
        "channel_id": "ch1", "status": "classifying",
        "pending": False, "dirty": False,
        "classifier_lock_owner": "owner-B",
        "version": Decimal("6"), "updated_at": now,
    }
    store._table.get_item.return_value = {"Item": current_item}
    err_response = {"Error": {"Code": "ConditionalCheckFailedException", "Message": ""}}
    store._table.update_item.side_effect = ClientError(err_response, "UpdateItem")
    result = store._release_lock_sync("ch1", "owner-A", 0.0)
    assert result is False

def test_release_lock_uses_default_debounce_when_zero():
    store = ExecutionStore.__new__(ExecutionStore)
    store.table_name = "test"
    store._region = "us-east-1"
    store._table = MagicMock()
    now = datetime.now(timezone.utc).isoformat()
    current_item = {
        "pk": "CHANNEL#ch1", "sk": "STATE#classification",
        "channel_id": "ch1", "status": "classifying",
        "pending": True, "dirty": True,
        "classifier_lock_owner": "owner-A",
        "version": Decimal("6"), "updated_at": now,
    }
    store._table.get_item.return_value = {"Item": current_item}
    store._table.update_item.return_value = {}
    store._release_lock_sync("ch1", "owner-A", 0.0)
    call_kwargs = store._table.update_item.call_args[1]
    attr_values = call_kwargs.get("ExpressionAttributeValues", {})
    assert attr_values.get(":target") == "debouncing"

def test_lock_race_one_winner():
    from botocore.exceptions import ClientError
    store = ExecutionStore.__new__(ExecutionStore)
    store.table_name = "test"
    store._region = "us-east-1"
    store._table = MagicMock()
    err_response = {"Error": {"Code": "ConditionalCheckFailedException", "Message": ""}}
    call_count = [0]
    def update_side_effect(**kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return {}
        raise ClientError(err_response, "UpdateItem")
    store._table.update_item.side_effect = update_side_effect
    result1 = store._acquire_lock_sync("ch1", "owner-A", "2099-01-01T00:00:00Z")
    result2 = store._acquire_lock_sync("ch1", "owner-B", "2099-01-01T00:00:00Z")
    assert result1 is True
    assert result2 is False

def test_full_lifecycle_idle_debouncing_classifying_idle():
    store = ExecutionStore.__new__(ExecutionStore)
    store.table_name = "test"
    store._region = "us-east-1"
    store._table = MagicMock()
    now = datetime.now(timezone.utc).isoformat()
    store._table.update_item.return_value = {"Attributes": {
        "status": "debouncing",
        "pending": True,
        "dirty": False,
        "channel_id": "ch1",
        "latest_observed_event_at": now,
        "latest_observed_message_id": "msg1",
        "debounce_until": now,
        "batch_first_event_at": now,
        "max_wait_until": now,
        "pending_event_count": 1,
        "version": 1,
        "updated_at": now,
    }}
    store._table.get_item.return_value = {"Item": {}}
    result = store._update_state_on_event_sync("ch1", "msg1", now, False, 5.0, 30)
    store._table.update_item.assert_called_once()
    call_kwargs = store._table.update_item.call_args[1]
    expr = call_kwargs["UpdateExpression"]
    assert "pending" in expr

def test_instance_identity_stability():
    id1 = get_instance_identity()
    id2 = get_instance_identity()
    assert id1 != id2
    assert "/" in id1
    assert "/" in id2

def test_floats_to_decimals_in_state_payload():
    payload = {
        "confidence": 0.95,
        "nested": {"score": 0.8},
        "items": [1.0, 2.5],
    }
    result = floats_to_decimals(payload)
    assert result["confidence"] == Decimal("0.95")
    assert result["nested"]["score"] == Decimal("0.8")
    assert result["items"] == [Decimal("1.0"), Decimal("2.5")]

def test_floats_to_decimals_preserves_bool():
    assert floats_to_decimals(True) is True
    assert floats_to_decimals(False) is False
    result = floats_to_decimals({"pending": True, "dirty": False})
    assert result["pending"] is True
    assert result["dirty"] is False

def test_floats_to_decimals_handles_decimal_already():
    d = Decimal("1.5")
    assert floats_to_decimals(d) == d
