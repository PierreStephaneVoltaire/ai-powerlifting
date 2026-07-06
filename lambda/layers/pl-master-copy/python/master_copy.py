"""Python-side mirror of ``utils/powerlifting-app/backend/src/services/masterCopy.ts``.

Seeds per-user copies of the master competition and master federation tables
for a single user. This is a "best-effort" path: if one source table fails
the other is still attempted and the failure is logged but not raised.

User copy schema mirrors ``masterCopy.ts`` exactly (USER_COMPETITIONS_TABLE).
User copy schema for federations is a slimmer counterpart covering the fields
the powerlifting-app frontend reads from the per-user federation row.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


def _to_dynamo(obj: Any) -> Any:
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: _to_dynamo(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_dynamo(v) for v in obj]
    return obj


def _sanitize_decimals(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return float(obj) if obj % 1 > 0 else int(obj)
    if isinstance(obj, dict):
        return {k: _sanitize_decimals(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_decimals(v) for v in obj]
    return obj


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _scan_all(table, table_name: str) -> List[dict]:
    """Paginated Scan of an entire table (master comps / feds are small)."""
    items: List[dict] = []
    last_key: Optional[dict] = None
    scan_kwargs: Dict[str, Any] = {"TableName": table_name}
    while True:
        if last_key:
            scan_kwargs["ExclusiveStartKey"] = last_key
        resp = table.scan(**scan_kwargs)
        for it in resp.get("Items", []) or []:
            items.append(_sanitize_decimals(it))
        last_key = resp.get("LastEvaluatedKey")
        if not last_key:
            break
    return items


def _batch_write(table, table_name: str, items: List[dict]) -> None:
    """BatchWriteItem 25 at a time, retrying UnprocessedItems."""
    if not items:
        return
    for start in range(0, len(items), 25):
        batch = items[start : start + 25]
        request_items = [
            {"PutRequest": {"Item": _to_dynamo(it)}} for it in batch
        ]
        try:
            resp = table.meta.client.batch_write_item(
                RequestItems={table_name: request_items}
            )
        except ClientError as exc:
            logger.error(
                "[MasterCopyService] BatchWriteItem failed on %s: %s",
                table_name,
                exc,
            )
            continue
        unprocessed = (resp.get("UnprocessedItems") or {}).get(table_name, [])
        retry = 0
        while unprocessed and retry < 3:
            retry += 1
            try:
                resp2 = table.meta.client.batch_write_item(
                    RequestItems={table_name: unprocessed}
                )
            except ClientError as exc:
                logger.error(
                    "[MasterCopyService] BatchWriteItem retry failed on %s: %s",
                    table_name,
                    exc,
                )
                break
            unprocessed = (resp2.get("UnprocessedItems") or {}).get(table_name, [])


def _build_competition_user_copy(user_pk: str, master: dict, now: str) -> dict:
    """Mirror masterCopy.ts seedCompetitionCopies — user-owned fields default."""
    pk = str(master.get("pk") or "")
    master_id = pk.replace("COMP#", "", 1) if pk.startswith("COMP#") else pk
    return {
        "pk": user_pk,
        "sk": f"COMP#{master_id}",
        "master_id": master_id,
        "name": master.get("name", "") or "",
        "start_date": master.get("start_date", "") or "",
        "end_date": master.get("end_date"),
        "federation_label": master.get("federation_label", "") or "",
        "federation_slug": master.get("federation_slug"),
        "federation_website_url": master.get("federation_website_url"),
        "venue_name": master.get("venue_name"),
        "venue_address": master.get("venue_address"),
        "venue_city": master.get("venue_city"),
        "venue_state": master.get("venue_state"),
        "venue_country": master.get("venue_country"),
        "venue_postal_code": master.get("venue_postal_code"),
        "website_url": master.get("website_url"),
        "testing_status": master.get("testing_status", "unknown") or "unknown",
        "registration_status": master.get("registration_status", "unknown") or "unknown",
        "registration_url": master.get("registration_url"),
        "registration_end_date": master.get("registration_end_date"),
        "source_url": master.get("source_url"),
        "source_name": master.get("source_name"),
        "event_type": master.get("event_type"),
        "last_verified_at": master.get("last_verified_at"),
        "cancelled": bool(master.get("cancelled", False)),
        "user_status": "available",
        "weight_class_kg": None,
        "body_weight_kg": None,
        "targets": None,
        "results": None,
        "post_meet_report": None,
        "hotel_required": False,
        "counts_toward_federation_ids": [],
        "between_comp_plan": None,
        "comp_day_protocol": None,
        "decision_date": None,
        "attempt_selection": None,
        "attempt_strategy_mode": None,
        "qualifying_standard_id": None,
        "qualifying_total_kg": None,
        "projected_at_t_minus_1w": None,
        "projection_snapshot_date": None,
        "notes": "",
        "created_at": now,
        "updated_at": now,
    }


def _build_federation_user_copy(user_pk: str, master: dict, now: str) -> dict:
    """Slimmer per-user federation copy than the comp one."""
    pk = str(master.get("pk") or "")
    fed_id = pk.replace("FED#", "", 1) if pk.startswith("FED#") else pk
    raw_standards = master.get("qualification_standards")
    standards = raw_standards if isinstance(raw_standards, list) else []
    return {
        "pk": user_pk,
        "sk": f"FED#{fed_id}",
        "master_id": fed_id,
        "name": master.get("name", "") or "",
        "slug": master.get("slug", "") or "",
        "country": master.get("country", "") or "",
        "website_url": master.get("website_url", "") or "",
        "qualification_standards": standards,
        "user_status": "available",
        "notes": "",
        "created_at": now,
        "updated_at": now,
    }


class MasterCopyService:
    """Reads master tables and writes per-user copies.

    Env vars (matches ``dynamo.ts`` constants in the TypeScript backend):

      - ``POWERLIFTING_MASTER_COMPETITIONS_TABLE`` (default: ``powerlifting-master-competitions``)
      - ``POWERLIFTING_USER_COMPETITIONS_TABLE``   (default: ``powerlifting-user-competitions``)
      - ``POWERLIFTING_MASTER_FEDERATIONS_TABLE``  (default: ``powerlifting-master-federations``)
      - ``POWERLIFTING_USER_FEDERATIONS_TABLE``    (default: ``powerlifting-user-federations``)
    """

    def __init__(self, table_prefix: str = "", region: str = "ca-central-1") -> None:
        self._table_prefix = table_prefix
        self._region = region
        self._resource = boto3.resource("dynamodb", region_name=region)
        self._master_comps = os.environ.get(
            "POWERLIFTING_MASTER_COMPETITIONS_TABLE", "powerlifting-master-competitions"
        )
        self._user_comps = os.environ.get(
            "POWERLIFTING_USER_COMPETITIONS_TABLE", "powerlifting-user-competitions"
        )
        self._master_feds = os.environ.get(
            "POWERLIFTING_MASTER_FEDERATIONS_TABLE", "powerlifting-master-federations"
        )
        self._user_feds = os.environ.get(
            "POWERLIFTING_USER_FEDERATIONS_TABLE", "powerlifting-user-federations"
        )

    def _table(self, name: str):
        return self._resource.Table(name)

    def _seed_competitions_sync(self, user_pk: str) -> int:
        try:
            masters = _scan_all(self._table(self._master_comps), self._master_comps)
        except Exception as exc:
            logger.error(
                "[MasterCopyService] Failed to scan %s: %s", self._master_comps, exc
            )
            return 0
        if not masters:
            return 0
        now = _now_iso()
        user_copies = [_build_competition_user_copy(user_pk, m, now) for m in masters]
        try:
            _batch_write(self._table(self._user_comps), self._user_comps, user_copies)
        except Exception as exc:
            logger.error(
                "[MasterCopyService] Failed to batch-write %s: %s",
                self._user_comps,
                exc,
            )
            return 0
        return len(user_copies)

    def _seed_federations_sync(self, user_pk: str) -> int:
        try:
            masters = _scan_all(self._table(self._master_feds), self._master_feds)
        except Exception as exc:
            logger.error(
                "[MasterCopyService] Failed to scan %s: %s", self._master_feds, exc
            )
            return 0
        if not masters:
            return 0
        now = _now_iso()
        user_copies = [_build_federation_user_copy(user_pk, m, now) for m in masters]
        try:
            _batch_write(self._table(self._user_feds), self._user_feds, user_copies)
        except Exception as exc:
            logger.error(
                "[MasterCopyService] Failed to batch-write %s: %s",
                self._user_feds,
                exc,
            )
            return 0
        return len(user_copies)

    def seed_user_from_master_sync(self, user_pk: str) -> dict:
        """Best-effort seed. Per-table failures are logged and counted as 0."""
        comps = 0
        feds = 0
        try:
            comps = self._seed_competitions_sync(user_pk)
        except Exception as exc:
            logger.error(
                "[MasterCopyService] Unexpected failure seeding comps for %s: %s",
                user_pk,
                exc,
            )
        try:
            feds = self._seed_federations_sync(user_pk)
        except Exception as exc:
            logger.error(
                "[MasterCopyService] Unexpected failure seeding feds for %s: %s",
                user_pk,
                exc,
            )
        return {"competitions": comps, "federations": feds}

    async def seed_user_from_master(self, user_pk: str) -> dict:
        return await asyncio.get_running_loop().run_in_executor(
            None, lambda: self.seed_user_from_master_sync(user_pk)
        )
