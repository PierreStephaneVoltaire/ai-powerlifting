"""DynamoDB-backed store for a per-user federation library.

A federation library is a per-user collection of federation slugs the user
cares about, plus the qualifying standards they've saved. Stored in the
``if-health`` table as a single item per user:

    - pk = <user_pk>
    - sk = "federation_library#v1"
    - entries = [{"federation_slug": "...", "display_name": "...",
                  "parent_slug": "...", "qualifying_standards": [...]}, ...]
    - updated_at = ISO8601 timestamp

This module is a thin async wrapper around a single get/put so the Fission
tools stay small.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, List, Optional

import boto3

logger = logging.getLogger(__name__)

LIBRARY_SK = "federation_library#v1"


def _to_dynamo(obj: Any) -> Any:
    """Recursively convert float values to Decimal for DynamoDB compatibility."""
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: _to_dynamo(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_dynamo(v) for v in obj]
    return obj


def _sanitize_decimals(obj: Any) -> Any:
    """Recursively convert Decimal values back to int/float for JSON."""
    if isinstance(obj, Decimal):
        return float(obj) if obj % 1 > 0 else int(obj)
    if isinstance(obj, dict):
        return {k: _sanitize_decimals(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_decimals(v) for v in obj]
    return obj


def _normalize_entry(raw: Any) -> dict:
    """Coerce one entry to a stable shape before persistence."""
    if not isinstance(raw, dict):
        return {}
    entry = dict(raw)
    entry["federation_slug"] = str(entry.get("federation_slug") or "").strip()
    entry["display_name"] = str(entry.get("display_name") or "").strip()
    parent = entry.get("parent_slug")
    entry["parent_slug"] = str(parent).strip() if isinstance(parent, str) and parent.strip() else ""
    standards = entry.get("qualifying_standards")
    if not isinstance(standards, list):
        standards = []
    entry["qualifying_standards"] = [s for s in standards if isinstance(s, dict)]
    return entry


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class FederationLibraryStore:
    """Async store for the per-user federation library item."""

    def __init__(
        self,
        table_name: Optional[str] = None,
        pk: str = "operator",
        region: str = "ca-central-1",
    ) -> None:
        self._table_name = table_name or "if-health"
        self._pk = pk
        self._region = region
        self._table = None

    @property
    def pk(self) -> str:
        return self._pk

    @pk.setter
    def pk(self, value: str) -> None:
        self._pk = value

    @property
    def table(self):
        if self._table is None:
            self._table = boto3.resource("dynamodb", region_name=self._region).Table(
                self._table_name
            )
        return self._table

    def get_library_sync(self) -> dict:
        """Return the library item, or an empty library if none exists."""
        resp = self.table.get_item(Key={"pk": self._pk, "sk": LIBRARY_SK})
        item = resp.get("Item")
        if not item:
            return {
                "pk": self._pk,
                "sk": LIBRARY_SK,
                "entries": [],
                "updated_at": "",
            }
        return _sanitize_decimals(item)

    async def get_library(self) -> dict:
        return await asyncio.get_running_loop().run_in_executor(None, self.get_library_sync)

    def set_library_sync(self, entries: List[dict]) -> dict:
        """Replace the library entries; updates ``updated_at`` and writes the item."""
        if not isinstance(entries, list):
            raise ValueError("entries must be a list of federation library entries")
        normalized = [_normalize_entry(e) for e in entries if isinstance(e, dict)]
        now = _now_iso()
        item = {
            "pk": self._pk,
            "sk": LIBRARY_SK,
            "entries": normalized,
            "updated_at": now,
        }
        self.table.put_item(Item=_to_dynamo(item))
        return _sanitize_decimals(item)

    async def set_library(self, entries: List[dict]) -> dict:
        return await asyncio.get_running_loop().run_in_executor(
            None, lambda: self.set_library_sync(entries)
        )
