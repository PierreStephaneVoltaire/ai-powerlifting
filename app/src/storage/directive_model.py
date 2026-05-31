"""Directive model for the directive store.

Directives are behavioral rules that govern the agent's behavior.
Each directive has an alpha tier (priority) and beta number (order within tier),
plus versioning for audit history.

DynamoDB Schema:
    PK: configurable (default "operator", can be set per store instance)
    SK: "{alpha:02d}#{beta:02d}#v{version:03d}" (e.g., "02#19#v001")
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
import re


@dataclass
class Directive:
    """A behavioral directive for the agent.

    Attributes:
        alpha: Priority tier (0-5, lower is higher priority)
        beta: Order within alpha tier
        label: Human-readable label (UPPER_SNAKE_CASE)
        content: Full directive text
        types: Domain types this directive applies to (e.g., ["core", "code", "security"])
        version: Version number (starts at 1, increments on revision)
        created_by: Who created this directive ("operator", "agent", "reflection")
        active: Whether this directive is active
        created_at: ISO 8601 timestamp of creation
        superseded_at: ISO 8601 timestamp when superseded by new version (or None)
        pk: DynamoDB partition key (default "operator")
        global_directive: If True, this directive applies to ALL users regardless of pk.
            Only allowed when pk is "operator". Global directives are always fetched
            by every user but are read-only for non-operator users.
    """
    alpha: int
    beta: int
    label: str
    content: str
    types: list[str] = field(default_factory=lambda: ["core"])
    version: int = 1
    created_by: str = "operator"
    active: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    superseded_at: Optional[str] = None
    pk: str = "operator"
    global_directive: bool = False

    @property
    def sort_key(self) -> str:
        """DynamoDB SK: {alpha:02d}#{beta:02d}#v{version:03d}"""
        return f"{self.alpha:02d}#{self.beta:02d}#v{self.version:03d}"

    @property
    def display_id(self) -> str:
        """Human-readable ID: alpha-beta"""
        return f"{self.alpha}-{self.beta}"

    @property
    def base_key(self) -> str:
        """Base key without version: {alpha:02d}#{beta:02d}"""
        return f"{self.alpha:02d}#{self.beta:02d}"
    
    @classmethod
    def from_dynamodb_item(cls, item: dict) -> "Directive":
        """Parse DynamoDB item into Directive.
        
        SK format: {alpha:02d}#{beta:02d}#v{version:03d}
        
        Args:
            item: DynamoDB item dict
            
        Returns:
            Directive instance
            
        Raises:
            ValueError: If SK format is invalid
        """
        sk = item["sk"]
        match = re.match(r"(\d{2})#(\d{2})#v(\d{3})", sk)
        if not match:
            raise ValueError(f"Invalid SK format: {sk}")
        
        alpha = int(match.group(1))
        beta = int(match.group(2))
        version = int(match.group(3))
        
        # Parse dtype (StringSet) - handle missing gracefully
        dtype_raw = item.get("dtype")
        if isinstance(dtype_raw, set):
            types = list(dtype_raw)
        elif isinstance(dtype_raw, list):
            types = dtype_raw
        else:
            types = ["core"]  # Default fallback

        # Parse global_directive — defaults to False for backward compat
        global_directive = bool(item.get("global_directive", False))

        return cls(
            alpha=alpha,
            beta=beta,
            version=version,
            label=item.get("label", ""),
            content=item.get("content", ""),
            types=types,
            active=item.get("active", True),
            created_by=item.get("created_by", "operator"),
            created_at=item.get("created_at", datetime.now(timezone.utc).isoformat()),
            superseded_at=item.get("superseded_at"),
            pk=item.get("pk", "operator"),
            global_directive=global_directive,
        )
    
    def to_dynamodb_item(self) -> dict:
        """Convert to DynamoDB item format.

        Returns:
            Dict suitable for DynamoDB put_item
        """
        item = {
            "pk": self.pk,
            "sk": self.sort_key,
            "alpha": self.alpha,
            "beta": self.beta,
            "version": self.version,
            "label": self.label,
            "content": self.content,
            "dtype": set(self.types),  # StringSet for types
            "active": self.active,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "global_directive": self.global_directive,
        }
        # Only include superseded_at if it's set
        if self.superseded_at is not None:
            item["superseded_at"] = self.superseded_at
        return item
    
    def __repr__(self) -> str:
        return f"Directive({self.display_id} v{self.version}: {self.label})"
