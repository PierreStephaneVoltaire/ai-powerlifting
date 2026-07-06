from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

_federation_store: Optional[Any] = None


def _get_federation_store():
    global _federation_store
    if _federation_store is None:
        import os
        from _federation_store import FederationStore
        _federation_store = FederationStore(
            table_name=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"),
            pk=os.environ.get("HEALTH_PROGRAM_PK", "operator"),
            region=os.environ.get("AWS_REGION", "ca-central-1"),
        )
    return _federation_store


def _federation_store_for(pk: str | None):
    """Return the FederationStore singleton, retargeted to pk when provided."""
    store = _get_federation_store()
    if pk:
        store.pk = pk
    return store


GOAL_TYPES = {
    "qualify_for_federation",
    "hit_total",
    "peak_for_meet",
    "make_podium",
    "conservative_pr",
    "train_through",
    "rank_percentile",
    "improve_dots",
    "maintain_weight_class",
    "coach_defined",
}
GOAL_PRIORITIES = {"primary", "secondary", "optional"}
ATTEMPT_STRATEGY_MODES = {
    "max_total",
    "qualify",
    "minimum_total",
    "podium",
    "train_through",
    "conservative_pr",
}
RISK_TOLERANCES = {"low", "medium", "high"}
FEDERATION_STATUSES = {"active", "archived"}
STANDARD_STATUSES = {"active", "archived"}
STANDARD_SEXES = {"male", "female"}
STANDARD_EQUIPMENT = {"raw", "wraps", "single-ply", "multi-ply"}
STANDARD_EVENTS = {"sbd", "bench-only", "deadlift-only"}

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _validate_iso_date(value: Any, field_name: str) -> None:
    if value in (None, ""):
        return
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a YYYY-MM-DD string")
    datetime.strptime(value, "%Y-%m-%d")

def _validate_choice(value: Any, valid_values: set[str], field_name: str, default: str | None = None) -> str:
    resolved = value if value not in (None, "") else default
    if resolved is None:
        raise ValueError(f"{field_name} is required")
    resolved = str(resolved)
    if resolved not in valid_values:
        raise ValueError(f"{field_name} must be one of {sorted(valid_values)}")
    return resolved

def _sanitize_federation_record(record: dict[str, Any], now: str) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise ValueError("Each federation must be an object")

    name = str(record.get("name") or "").strip()
    if not name:
        raise ValueError("federation.name is required")

    clean_record: dict[str, Any] = {
        "id": str(record.get("id") or uuid.uuid4()),
        "name": name,
        "status": _validate_choice(record.get("status"), FEDERATION_STATUSES, "federation.status", default="active"),
        "created_at": str(record.get("created_at") or now),
        "updated_at": now,
    }

    for field in ("abbreviation", "region", "notes"):
        value = record.get(field)
        if value not in (None, ""):
            clean_record[field] = value

    return clean_record
def _sanitize_qualification_standard(
    record: dict[str, Any],
    now: str,
    federation_ids: set[str],
) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise ValueError("Each qualification standard must be an object")

    federation_id = str(record.get("federation_id") or "").strip()
    if not federation_id:
        raise ValueError("qualification_standard.federation_id is required")
    if federation_id not in federation_ids:
        raise ValueError(f"qualification_standard.federation_id '{federation_id}' does not match any federation in the library")

    _validate_iso_date(record.get("qualifying_start_date"), "qualification_standard.qualifying_start_date")
    _validate_iso_date(record.get("qualifying_end_date"), "qualification_standard.qualifying_end_date")

    try:
        season_year = int(record.get("season_year"))
    except (TypeError, ValueError):
        raise ValueError("qualification_standard.season_year must be an integer")

    weight_class_kg = record.get("weight_class_kg")
    if weight_class_kg is None:
        raise ValueError("qualification_standard.weight_class_kg is required")

    required_total_kg = record.get("required_total_kg")
    if required_total_kg is None:
        raise ValueError("qualification_standard.required_total_kg is required")

    clean_record: dict[str, Any] = {
        "id": str(record.get("id") or uuid.uuid4()),
        "federation_id": federation_id,
        "season_year": season_year,
        "sex": _validate_choice(record.get("sex"), STANDARD_SEXES, "qualification_standard.sex"),
        "equipment": _validate_choice(record.get("equipment"), STANDARD_EQUIPMENT, "qualification_standard.equipment"),
        "event": _validate_choice(record.get("event"), STANDARD_EVENTS, "qualification_standard.event"),
        "weight_class_kg": weight_class_kg,
        "required_total_kg": required_total_kg,
        "source_type": "user_entered",
        "status": _validate_choice(
            record.get("status"),
            STANDARD_STATUSES,
            "qualification_standard.status",
            default="active",
        ),
        "updated_at": now,
    }

    optional_fields = (
        "competition_name",
        "age_class",
        "division",
        "qualifying_start_date",
        "qualifying_end_date",
        "source_url",
        "source_label",
    )
    for field in optional_fields:
        value = record.get(field)
        if value not in (None, ""):
            clean_record[field] = value

    return clean_record

def _build_federation_library_payload(library: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(library, dict):
        raise ValueError("library must be an object")

    store = _get_federation_store()
    now = _utc_now_iso()
    federation_rows = library.get("federations") or []
    standard_rows = library.get("qualification_standards") or []
    if not isinstance(federation_rows, list):
        raise ValueError("library.federations must be an array")
    if not isinstance(standard_rows, list):
        raise ValueError("library.qualification_standards must be an array")

    federations = [
        _sanitize_federation_record(record, now)
        for record in federation_rows
    ]
    federation_ids = {str(record["id"]) for record in federations}
    standards = [
        _sanitize_qualification_standard(record, now, federation_ids)
        for record in standard_rows
    ]

    return {
        "pk": store.pk,
        "sk": store.FEDERATIONS_SK,
        "updated_at": now,
        "federations": federations,
        "qualification_standards": standards,
    }

def _floats_to_decimals(obj):
    """Recursively convert float values to Decimal for DynamoDB compatibility.

    DynamoDB boto3 rejects Python float types — all floats must be Decimal.
    Uses str() conversion to preserve precision and avoid floating-point artifacts.
    """
    from decimal import Decimal
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: _floats_to_decimals(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_floats_to_decimals(v) for v in obj]
    return obj

async def _write_federation_library(library: dict[str, Any]) -> dict[str, Any]:
    store = _get_federation_store()
    item = _floats_to_decimals(library)
    await asyncio.get_running_loop().run_in_executor(None, lambda: store.table.put_item(Item=item))
    try:
        from cache_invalidation import invalidate_analysis_caches
        invalidate_analysis_caches(store.pk, getattr(store, "_table_name", None), getattr(store, "_region", None))
    except Exception as exc:
        logger.warning("[HealthTools] Analysis cache invalidation failed after federation update: %s", exc)
    return library

async def health_update_federation_library(args: dict | None = None, library: dict | None = None) -> dict:
    """Replace the shared federation library document."""
    if library is None and isinstance(args, dict):
        if args.get("library"):
            library = args.get("library")
        elif "federations" in args or "qualification_standards" in args:
            library = {
                "federations": args.get("federations") or [],
                "qualification_standards": args.get("qualification_standards") or [],
            }
    pk = args.get("pk") if isinstance(args, dict) else None
    _federation_store_for(pk)
    payload = _build_federation_library_payload(library)
    return await _write_federation_library(payload)
