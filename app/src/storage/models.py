






from __future__ import annotations
from typing import Dict, Any, Optional
from datetime import datetime, timezone, timedelta
import uuid
import json

from sqlmodel import SQLModel, Field

class WebhookRecord(SQLModel, table=True):




    __tablename__ = "webhooks"

    webhook_id: str = Field(
        default_factory=lambda: f"wh_{uuid.uuid4().hex[:12]}",
        primary_key=True,
    )
    conversation_id: str = Field(
        default_factory=lambda: f"conv_{uuid.uuid4().hex[:12]}",
        index=True,
    )
    platform: str
    label: str
    status: str = "active"
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    config_json: str = ""
    pinned_specialist: str = "" 

    def set_config(self, config: Dict[str, Any]) -> None:





        self.config_json = json.dumps(config)

    def get_config(self) -> Dict[str, Any]:





        return json.loads(self.config_json) if self.config_json else {}

class RoutingCacheEntry(SQLModel, table=True):





    __tablename__ = "routing_cache"

    cache_key: str = Field(primary_key=True)
    active_preset: str = ""
    current_tier: int = 0
    context_tokens: int = 0
    condensation_count: int = 0
    pinned: int = 0
    pinned_tier: int | None = None
    pondering: int = 0
    pin_message_count: int = 0
    anchor_window: str = ""
    last_scores: str | None = None
    last_updated: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    expires_at: str = Field(
        default_factory=lambda: (
            datetime.now(timezone.utc) + timedelta(hours=24)
        ).isoformat()
    )

    def set_anchor_window(self, messages: list[str]) -> None:

        self.anchor_window = json.dumps(messages)

    def get_anchor_window(self) -> list[str]:

        return json.loads(self.anchor_window) if self.anchor_window else []

    def set_last_scores(self, scores: Dict[str, Any] | None) -> None:

        self.last_scores = json.dumps(scores) if scores else None

    def get_last_scores(self) -> Dict[str, Any] | None:

        return json.loads(self.last_scores) if self.last_scores else None

    def is_expired(self) -> bool:

        try:
            expiry = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
            return datetime.now(timezone.utc) > expiry
        except (ValueError, TypeError):
            return True

    def touch(self) -> None:

        now = datetime.now(timezone.utc)
        self.last_updated = now.isoformat()
        self.expires_at = (now + timedelta(hours=24)).isoformat()

class ActivityLogEntry(SQLModel, table=True):





    __tablename__ = "activity_log"

    cache_key: str = Field(primary_key=True)
    webhook_id: str | None = None
    last_message_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    last_heartbeat_at: str | None = None
