"""Shared data model for webhook records and routing cache.

Used by both SQLite and future DynamoDB backends.

For SQLite: this IS the table definition (SQLModel, table=True).
For DynamoDB: this is used for serialization/deserialization only.
"""
from __future__ import annotations
from typing import Dict, Any, Optional
from datetime import datetime, timezone, timedelta
import uuid
import json

from sqlmodel import SQLModel, Field


class WebhookRecord(SQLModel, table=True):
    """Webhook record for channel integrations.
    
    Stores webhook configuration for platforms like Discord and OpenWebUI.
    """
    __tablename__ = "webhooks"

    webhook_id: str = Field(
        default_factory=lambda: f"wh_{uuid.uuid4().hex[:12]}",
        primary_key=True,
    )
    conversation_id: str = Field(
        default_factory=lambda: f"conv_{uuid.uuid4().hex[:12]}",
        index=True,
    )
    platform: str  # "discord" | "openwebui"
    label: str  # Human-readable name
    status: str = "active"  # "active" | "inactive"
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    config_json: str = ""  # JSON-serialized platform config
    pinned_specialist: str = "" 

    # --- Convenience methods for config serialization ---

    def set_config(self, config: Dict[str, Any]) -> None:
        """Serialize config dict to JSON string.
        
        Args:
            config: Configuration dictionary to store
        """
        self.config_json = json.dumps(config)

    def get_config(self) -> Dict[str, Any]:
        """Deserialize config from JSON string.
        
        Returns:
            Configuration dictionary, empty dict if not set
        """
        return json.loads(self.config_json) if self.config_json else {}


class RoutingCacheEntry(SQLModel, table=True):
    """Persistent routing cache entry.

    Survives server restarts. Entries expire after 24 hours.
    Stores conversation routing state including pinned presets.
    """
    __tablename__ = "routing_cache"

    cache_key: str = Field(primary_key=True)  # chat_id or channel_id
    active_preset: str = ""  # Preset name, empty if not set = ""
    current_tier: int = 0  # 0=air, 1=standard, 2=heavy
    context_tokens: int = 0
    condensation_count: int = 0
    pinned: int = 0  # SQLite doesn't have bool, use 0/1
    pinned_tier: int | None = None  # Tier when pinned
    pondering: int = 0  # SQLite doesn't have bool, use 0/1
    pin_message_count: int = 0
    anchor_window: str = ""  # JSON array of strings
    last_scores: str | None = None  # JSON blob, nullable
    last_updated: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    expires_at: str = Field(
        default_factory=lambda: (
            datetime.now(timezone.utc) + timedelta(hours=24)
        ).isoformat()
    )

    # --- Convenience methods for JSON fields ---

    def set_anchor_window(self, messages: list[str]) -> None:
        """Serialize anchor window messages to JSON."""
        self.anchor_window = json.dumps(messages)

    def get_anchor_window(self) -> list[str]:
        """Deserialize anchor window messages from JSON."""
        return json.loads(self.anchor_window) if self.anchor_window else []

    def set_last_scores(self, scores: Dict[str, Any] | None) -> None:
        """Serialize scores dict to JSON."""
        self.last_scores = json.dumps(scores) if scores else None

    def get_last_scores(self) -> Dict[str, Any] | None:
        """Deserialize scores dict from JSON."""
        return json.loads(self.last_scores) if self.last_scores else None

    def is_expired(self) -> bool:
        """Check if this cache entry has expired."""
        try:
            expiry = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
            return datetime.now(timezone.utc) > expiry
        except (ValueError, TypeError):
            return True  # Invalid date = expired

    def touch(self) -> None:
        """Update last_updated and reset expiry."""
        now = datetime.now(timezone.utc)
        self.last_updated = now.isoformat()
        self.expires_at = (now + timedelta(hours=24)).isoformat()


class ActivityLogEntry(SQLModel, table=True):
    """Activity log entry for heartbeat system.
    
    Tracks last message and heartbeat times per channel/chat.
    Used to determine when to initiate proactive pondering conversations.
    """
    __tablename__ = "activity_log"

    cache_key: str = Field(primary_key=True)  # channel_id for webhooks, chat_id for HTTP
    webhook_id: str | None = None  # nullable (HTTP chats have no webhook)
    last_message_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    last_heartbeat_at: str | None = None  # ISO timestamp, last proactive ping
