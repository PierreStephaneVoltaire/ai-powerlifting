"""Execution registry models for Discord channel orchestration.

Dataclasses representing channel classification state, batch decisions,
implementation tasks, OpenCode run records, and outbound messages.

These models are used by the DynamoDB execution registry and the channel
coordinator/orchestrator. They are not wired into the live Discord path yet.

Phase 0: Foundations and Invariants — models and helpers only, no behavior change.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def floats_to_decimals(obj: Any) -> Any:
    """Recursively convert float values to Decimal for DynamoDB compatibility.

    DynamoDB boto3 rejects Python float types — all floats must be Decimal.
    Uses str() conversion to preserve precision and avoid floating-point artifacts.

    Reuses the pattern from ``tools/health/core.py::_floats_to_decimals`` and
    ``tools/health/program_store.py::ProgramStore._floats_to_decimals``.
    This is the canonical shared helper for the execution registry modules.
    """
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: floats_to_decimals(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [floats_to_decimals(v) for v in obj]
    return obj


def get_instance_identity() -> str:
    """Return a stable per-process identity string for lock ownership.

    Combines the hostname with a per-process UUID so that:
    - Multiple pods have distinct identities (different hostnames).
    - Multiple processes on the same pod have distinct identities (different UUIDs).
    - The identity is stable for the lifetime of one process.

    Used by classifier and outbound locks so lock ownership is meaningful
    once ``replicas > 1``.
    """
    import socket
    return f"{socket.gethostname()}/{uuid.uuid4()}"


# ---------------------------------------------------------------------------
# Channel Classification State
# ---------------------------------------------------------------------------

@dataclass
class ChannelClassificationState:
    """Per-channel classifier/debounce state and pending activity signal.

    Stored in DynamoDB under ``pk=CHANNEL#<channel_id>, sk=STATE#classification``.
    ``pending=True`` means "there is channel activity to classify"; it does
    not mean messages are stored in DynamoDB.  ``latest_observed_message_id``
    and timestamps are cursors/hints only.  On old message edits,
    ``latest_observed_edit_at`` and ``dirty=True`` are enough to force a
    fresh history fetch and reclassification pass.
    """

    channel_id: str
    status: Literal["idle", "debouncing", "classifying"]
    pending: bool
    dirty: bool
    debounce_until: str | None
    batch_first_event_at: str | None
    max_wait_until: str | None
    latest_observed_event_at: str | None
    latest_observed_message_id: str | None
    latest_observed_edit_at: str | None
    last_classifier_started_at: str | None
    last_classifier_finished_at: str | None
    active_classifier_run_id: str | None
    classifier_lock_owner: str | None
    classifier_lock_expires_at: str | None
    last_classified_message_id: str | None
    last_classified_at: str | None
    pending_event_count: int
    version: int
    updated_at: str


# ---------------------------------------------------------------------------
# Classification Batch
# ---------------------------------------------------------------------------

@dataclass
class ClassificationBatch:
    """One execution of the planner/router over freshly fetched Discord history.

    Stored in DynamoDB under ``pk=CHANNEL#<channel_id>, sk=BATCH#<batch_id>``.
    """

    batch_id: str
    channel_id: str
    classifier_run_id: str
    started_at: str
    completed_at: str | None
    history_fetched_at: str | None
    history_oldest_message_id: str | None
    history_newest_message_id: str | None
    cursor_before_message_id: str | None
    cursor_after_message_id: str | None
    edited_since: str | None
    candidate_source_message_ids: list[str] = field(default_factory=list)
    status: Literal["running", "completed", "failed"] = "running"
    batch_summary: str | None = None
    decisions: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    version: int = 1
    ttl: int | None = None


# ---------------------------------------------------------------------------
# Classifier Decision
# ---------------------------------------------------------------------------

@dataclass
class ClassifierDecision:
    """A single intent decision produced by the batch classifier.

    The existing planner/router is extended so its output can represent
    multiple decisions, not just one route.
    """

    intent_id: str
    kind: Literal["social", "task", "implementation_control", "clarification", "ignore"]
    action: Literal[
        "social_response",
        "start_new_task",
        "append_to_active_implementation",
        "pivot_active_implementation",
        "cancel_active_implementation",
        "queue_on_active_implementation",
        "await_instruction_for_active_implementation",
        "ask_clarifying_target",
        "ignore",
    ]
    source_message_ids: list[str] = field(default_factory=list)
    target_task_id: str | None = None
    confidence: float = 0.0
    reason: str = ""
    needs_planning: bool = False
    selected_specialist: str | None = None
    selected_model: str | None = None
    social_response_text: str | None = None
    response_text: str | None = None
    planner_intent: dict[str, Any] | None = None
    topic_update: dict[str, Any] | None = None
    conflict: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Intent Record
# ---------------------------------------------------------------------------

@dataclass
class IntentRecord:
    """Persisted record of a single classifier decision being applied.

    Stored in DynamoDB under ``pk=BATCH#<batch_id>, sk=INTENT#<intent_id>``.
    """

    intent_id: str
    batch_id: str
    channel_id: str
    action: str
    kind: str
    source_message_ids: list[str] = field(default_factory=list)
    target_task_id: str | None = None
    status: Literal[
        "pending", "applying", "running", "completed", "failed", "skipped"
    ] = "pending"
    created_at: str = ""
    updated_at: str = ""
    error: str | None = None
    ttl: int | None = None


# ---------------------------------------------------------------------------
# Implementation Task
# ---------------------------------------------------------------------------

@dataclass
class ImplementationTask:
    """Tracked implementation task within a channel.

    Stored in DynamoDB under ``pk=CHANNEL#<channel_id>, sk=TASK#<task_id>``.
    ``queued_message_refs`` contains message IDs/timestamps/reasons, not
    full message content.  Workers read the current per-channel
    ``history.md`` before using those refs.
    """

    task_id: str
    channel_id: str
    conversation_id: str
    status: Literal[
        "implementing",
        "awaiting_instruction",
        "cancel_requested",
        "pivot_requested",
        "completed",
        "failed",
        "stale",
    ]
    root_discord_message_id: str
    related_discord_message_ids: list[str] = field(default_factory=list)
    active_implementer_run_id: str | None = None
    latest_planner_run_id: str | None = None
    selected_specialist: str | None = None
    selected_model: str | None = None
    topic: dict[str, Any] = field(default_factory=dict)
    pending_conflict: dict[str, Any] | None = None
    queued_message_refs: list[dict[str, Any]] = field(default_factory=list)
    control: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
    version: int = 1
    ttl: int | None = None


# ---------------------------------------------------------------------------
# OpenCode Run Record
# ---------------------------------------------------------------------------

@dataclass
class OpenCodeRunRecord:
    """Lifecycle record for one OpenCode subprocess invocation.

    Stored in DynamoDB under ``pk=RUN#<run_id>, sk=META`` and also
    ``pk=TASK#<task_id>, sk=RUN#<run_id>``.
    ``config_path`` and ``session_marker_path`` capture the per-run OpenCode
    config file and continue-marker introduced for concurrent-run safety.
    """

    run_id: str
    channel_id: str | None = None
    task_id: str | None = None
    batch_id: str | None = None
    kind: Literal[
        "classifier", "planner", "implementer", "social",
        "domain", "technical", "review", "handoff",
    ] = "planner"
    agent: str = ""
    model: str = ""
    status: Literal[
        "running", "completed", "failed",
        "cancel_requested", "cancelled", "timed_out",
    ] = "running"
    started_at: str = ""
    completed_at: str | None = None
    title: str | None = None
    session_dir: str | None = None
    config_path: str | None = None
    session_marker_path: str | None = None
    history_path: str | None = None
    plan_path: str | None = None
    response_path: str | None = None
    status_path: str | None = None
    returncode: int | None = None
    error: str | None = None
    ttl: int | None = None


# ---------------------------------------------------------------------------
# Discord Outbound Message
# ---------------------------------------------------------------------------

@dataclass
class DiscordOutboundMessage:
    """Queued outbound Discord message.

    Stored in DynamoDB under
    ``pk=CHANNEL#<channel_id>,
     sk=OUTBOX#<priority>#<send_after_or_created_at>#<outbound_id>``.
    """

    outbound_id: str
    channel_id: str
    conversation_id: str
    task_id: str | None = None
    intent_id: str | None = None
    batch_id: str | None = None
    type: Literal[
        "social_response",
        "clarifying_question",
        "task_started",
        "task_update",
        "task_completed",
        "task_failed",
        "await_instruction",
        "cancel_confirmation",
    ] = "social_response"
    priority: int = 5
    content: str = ""
    attachments: list[dict[str, Any]] = field(default_factory=list)
    reply_to_message_id: str | None = None
    allowed_mentions: dict[str, Any] | None = None
    status: Literal["queued", "sending", "sent", "failed"] = "queued"
    send_after: str | None = None
    created_at: str = ""
    updated_at: str = ""
    discord_message_id: str | None = None
    idempotency_key: str = ""
    ttl: int | None = None