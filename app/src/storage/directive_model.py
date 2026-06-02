








from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
import re

@dataclass
class Directive:


















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
        return f"{self.alpha:02d}#{self.beta:02d}#v{self.version:03d}"

    @property
    def display_id(self) -> str:

        return f"{self.alpha}-{self.beta}"

    @property
    def base_key(self) -> str:
        """Base key without version: {alpha:02d}#{beta:02d}"""
        return f"{self.alpha:02d}#{self.beta:02d}"
    
    @classmethod
    def from_dynamodb_item(cls, item: dict) -> "Directive":












        sk = item["sk"]
        match = re.match(r"(\d{2})#(\d{2})#v(\d{3})", sk)
        if not match:
            raise ValueError(f"Invalid SK format: {sk}")
        
        alpha = int(match.group(1))
        beta = int(match.group(2))
        version = int(match.group(3))
        
        dtype_raw = item.get("dtype")
        if isinstance(dtype_raw, set):
            types = list(dtype_raw)
        elif isinstance(dtype_raw, list):
            types = dtype_raw
        else:
            types = ["core"]

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





        item = {
            "pk": self.pk,
            "sk": self.sort_key,
            "alpha": self.alpha,
            "beta": self.beta,
            "version": self.version,
            "label": self.label,
            "content": self.content,
            "dtype": set(self.types),
            "active": self.active,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "global_directive": self.global_directive,
        }
        if self.superseded_at is not None:
            item["superseded_at"] = self.superseded_at
        return item
    
    def __repr__(self) -> str:
        return f"Directive({self.display_id} v{self.version}: {self.label})"
