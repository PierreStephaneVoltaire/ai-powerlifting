










from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal

def floats_to_decimals(obj: Any) -> Any:









    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: floats_to_decimals(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [floats_to_decimals(v) for v in obj]
    return obj

def get_instance_identity() -> str:










    import socket
    return f"{socket.gethostname()}/{uuid.uuid4()}"

@dataclass
class ChannelClassificationState:


    







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

@dataclass
class ClassificationBatch:




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

@dataclass
class ClassifierDecision:






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

@dataclass
class IntentRecord:




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

@dataclass
class ImplementationTask:








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

@dataclass
class OpenCodeRunRecord:





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

@dataclass
class DiscordOutboundMessage:

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
