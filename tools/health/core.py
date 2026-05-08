"""Health tool plugin core — training program management and powerlifting tools.

Business logic for health tools. Used by tools/health/tool.py SDK wrappers.

Self-initialising:
    The module lazily creates its own ProgramStore and HealthDocsRAG
    instances on first access via _get_store() / _get_rag().
"""
from __future__ import annotations

import asyncio
import copy
import json
import logging
import os
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional, Literal

# Import from health infrastructure module (app/src/health/)

logger = logging.getLogger(__name__)


# Module-level store instance (set via init_tools)
_store: Optional[ProgramStore] = None
_template_store: Optional[Any] = None
_import_store: Optional[Any] = None
_glossary_store: Optional[Any] = None
_federation_store: Optional[Any] = None
_rag: Optional[Any] = None  # HealthDocsRAG type, avoid circular import


def _get_store():
    """Lazily create and return the ProgramStore singleton."""
    global _store
    if _store is None:
        import os
        from program_store import ProgramStore as _PS
        _store = _PS(
            table_name=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"),
            pk=os.environ.get("HEALTH_PROGRAM_PK", "operator"),
            region=os.environ.get("AWS_REGION", "ca-central-1"),
        )
        logger.info("[HealthTools] ProgramStore initialised from env vars")
    return _store

def _get_template_store():
    global _template_store
    if _template_store is None:
        import os
        from template_store import TemplateStore
        _template_store = TemplateStore(
            table_name=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"),
            pk=os.environ.get("HEALTH_PROGRAM_PK", "operator"),
            region=os.environ.get("AWS_REGION", "ca-central-1"),
        )
    return _template_store

def _get_import_store():
    global _import_store
    if _import_store is None:
        import os
        from import_store import ImportStore
        _import_store = ImportStore(
            table_name=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"),
            pk=os.environ.get("HEALTH_PROGRAM_PK", "operator"),
            region=os.environ.get("AWS_REGION", "ca-central-1"),
        )
    return _import_store

def _get_glossary_store():
    global _glossary_store
    if _glossary_store is None:
        import os
        from glossary_store import GlossaryStore
        _glossary_store = GlossaryStore(
            table_name=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"),
            pk=os.environ.get("HEALTH_PROGRAM_PK", "operator"),
            region=os.environ.get("AWS_REGION", "ca-central-1"),
        )
    return _glossary_store

def _get_federation_store():
    global _federation_store
    if _federation_store is None:
        import os
        from federation_store import FederationStore
        _federation_store = FederationStore(
            table_name=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"),
            pk=os.environ.get("HEALTH_PROGRAM_PK", "operator"),
            region=os.environ.get("AWS_REGION", "ca-central-1"),
        )
    return _federation_store

def _get_rag():
    """Lazily create and return the HealthDocsRAG singleton."""
    global _rag
    if _rag is None:
        import os
        from rag import HealthDocsRAG
        _rag = HealthDocsRAG(
            docs_dir=os.environ.get("HEALTH_DOCS_DIR", "docs/health"),
        )
        logger.info("[HealthTools] HealthDocsRAG initialised from env vars")
    return _rag


def _get_table_and_pk():
    store = _get_store()
    return store.table, store.pk, store


def _resolve_program_sk(table, pk: str, version: str) -> str:
    if version == "current":
        pointer = table.get_item(Key={"pk": pk, "sk": "program#current"}).get("Item")
        if pointer:
            return pointer.get("ref_sk", "program#v001")
        return "program#v001"
    return f"program#{version}"


def _load_program_version(version: str, pk: str | None = None) -> tuple[dict, str, Any]:
    table, default_pk, _store = _get_table_and_pk()
    active_pk = pk or default_pk
    sk = _resolve_program_sk(table, active_pk, version)
    item = table.get_item(Key={"pk": active_pk, "sk": sk}).get("Item")
    if not item:
        raise ValueError(f"Program version {version} not found")
    program = copy.deepcopy(item)
    program.pop("pk", None)
    program.pop("sk", None)
    from session_store import SessionStore
    session_store = SessionStore(
        table_name=os.environ.get("IF_SESSIONS_TABLE_NAME", "if-sessions"),
        pk=active_pk,
        region=os.environ.get("AWS_REGION", "ca-central-1"),
        source_table_name=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"),
    )
    program["sessions"] = session_store.list_sessions_sync(
        sk,
        program.get("phases", []) if isinstance(program.get("phases"), list) else [],
    )
    return program, sk, _store


def _save_program_version(program: dict, sk: str, pk: str | None = None) -> None:
    table, default_pk, store = _get_table_and_pk()
    active_pk = pk or default_pk
    item = copy.deepcopy(program)
    sessions = item.pop("sessions", [])
    item["pk"] = active_pk
    item["sk"] = sk
    table.put_item(Item=_floats_to_decimals(item))
    if isinstance(sessions, list):
        from session_store import SessionStore
        session_store = SessionStore(
            table_name=os.environ.get("IF_SESSIONS_TABLE_NAME", "if-sessions"),
            pk=active_pk,
            region=os.environ.get("AWS_REGION", "ca-central-1"),
            source_table_name=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"),
        )
        session_store.replace_program_sessions_sync(
            sk,
            sessions,
            program.get("phases", []) if isinstance(program.get("phases"), list) else [],
        )
    store.invalidate_cache()
    try:
        from cache_invalidation import invalidate_analysis_caches
        invalidate_analysis_caches(active_pk, getattr(store, "_table_name", None), getattr(store, "_region", None))
    except Exception as exc:
        logger.warning("[HealthTools] Analysis cache invalidation failed: %s", exc)


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


def _string_list_with_legacy(values: Any, legacy_value: Any, field_name: str) -> list[str]:
    resolved: list[str] = []
    if values is not None:
        if not isinstance(values, list):
            raise ValueError(f"{field_name} must be an array when provided")
        for item in values:
            text = str(item or "").strip()
            if text and text not in resolved:
                resolved.append(text)
    legacy_text = str(legacy_value or "").strip()
    if legacy_text and legacy_text not in resolved:
        resolved.append(legacy_text)
    return resolved


def _sanitize_goal_record(goal: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(goal, dict):
        raise ValueError("Each goal must be an object")

    title = str(goal.get("title") or "").strip()
    if not title:
        raise ValueError("goal.title is required")

    goal_type = _validate_choice(goal.get("goal_type"), GOAL_TYPES, "goal.goal_type")
    strategy_default = {
        "qualify_for_federation": "qualify",
        "make_podium": "podium",
        "train_through": "train_through",
        "conservative_pr": "conservative_pr",
    }.get(goal_type, "max_total")

    target_competition_dates = _string_list_with_legacy(
        goal.get("target_competition_dates"),
        goal.get("target_competition_date"),
        "goal.target_competition_dates",
    )
    for value in target_competition_dates:
        _validate_iso_date(value, "goal.target_competition_dates[]")
    _validate_iso_date(goal.get("target_competition_date"), "goal.target_competition_date")
    _validate_iso_date(goal.get("target_date"), "goal.target_date")
    target_standard_ids = _string_list_with_legacy(
        goal.get("target_standard_ids"),
        goal.get("target_standard_id"),
        "goal.target_standard_ids",
    )

    acceptable_weight_classes = goal.get("acceptable_weight_classes_kg")
    if acceptable_weight_classes is not None and not isinstance(acceptable_weight_classes, list):
        raise ValueError("goal.acceptable_weight_classes_kg must be an array when provided")

    clean_goal: dict[str, Any] = {
        "id": str(goal.get("id") or uuid.uuid4()),
        "title": title,
        "goal_type": goal_type,
        "priority": _validate_choice(goal.get("priority"), GOAL_PRIORITIES, "goal.priority", default="secondary"),
        "strategy_mode": _validate_choice(
            goal.get("strategy_mode"),
            ATTEMPT_STRATEGY_MODES,
            "goal.strategy_mode",
            default=strategy_default,
        ),
        "risk_tolerance": _validate_choice(
            goal.get("risk_tolerance"),
            RISK_TOLERANCES,
            "goal.risk_tolerance",
            default="medium",
        ),
    }

    optional_scalar_fields = (
        "target_date",
        "target_federation_id",
        "target_total_kg",
        "target_dots",
        "target_ipf_gl",
        "target_weight_class_kg",
        "max_acceptable_bodyweight_loss_pct",
        "max_acceptable_water_cut_pct",
        "notes",
    )
    for field in optional_scalar_fields:
        value = goal.get(field)
        if value is not None:
            clean_goal[field] = value

    if target_competition_dates:
        clean_goal["target_competition_dates"] = target_competition_dates
        clean_goal["target_competition_date"] = target_competition_dates[0]
    elif goal.get("target_competition_date") is not None:
        clean_goal["target_competition_date"] = goal.get("target_competition_date")

    if target_standard_ids:
        clean_goal["target_standard_ids"] = target_standard_ids
        clean_goal["target_standard_id"] = target_standard_ids[0]
    elif goal.get("target_standard_id") is not None:
        clean_goal["target_standard_id"] = goal.get("target_standard_id")

    if acceptable_weight_classes is not None:
        clean_goal["acceptable_weight_classes_kg"] = acceptable_weight_classes

    return clean_goal


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


def _string_ids(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    deduped: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in deduped:
            deduped.append(text)
    return deduped


def _competition_snapshot_payload(projection: dict, snapshot_date: date) -> dict:
    return {
        "squat_kg": projection.get("squat"),
        "bench_kg": projection.get("bench"),
        "deadlift_kg": projection.get("deadlift"),
        "total_kg": projection.get("total"),
    }


def _snapshot_competitions_in_program(
    program: dict,
    snapshot_date: date,
    allow_retrospective: bool = False,
) -> tuple[dict, list[dict]]:
    from analytics import meet_projection

    competitions = program.get("competitions", []) or []
    updated: list[dict] = []
    target_comp_date = snapshot_date + timedelta(days=7)

    for comp in competitions:
        comp_date = None
        if comp.get("date"):
            try:
                comp_date = datetime.strptime(comp.get("date", ""), "%Y-%m-%d").date()
            except ValueError:
                comp_date = None
        if comp_date is None or comp_date != target_comp_date:
            continue
        if comp.get("projected_at_t_minus_1w") is not None:
            continue
        if comp.get("status") not in ("confirmed", "optional") and not allow_retrospective:
            continue

        projection = meet_projection(program, program.get("sessions", []), comp_date=comp.get("date"), ref_date=snapshot_date)
        if "total" not in projection:
            continue

        snapshot = _competition_snapshot_payload(projection, snapshot_date)
        comp["projected_at_t_minus_1w"] = snapshot
        comp["projection_snapshot_date"] = snapshot_date.isoformat()
        updated.append({
            "date": comp.get("date"),
            "name": comp.get("name"),
            "projected_at_t_minus_1w": snapshot,
            "projection_snapshot_date": snapshot_date.isoformat(),
        })

    if updated:
        program["competitions"] = competitions
        meta = program.setdefault("meta", {})
        meta["updated_at"] = datetime.utcnow().isoformat()

    return program, updated


def _complete_competition_in_program(
    program: dict,
    comp_date: str,
    results: dict,
    body_weight_kg: float,
    allow_retrospective: bool = True,
    post_meet_report: Optional[dict] = None,
) -> dict:
    target = None
    for comp in program.get("competitions", []) or []:
        if comp.get("date") == comp_date:
            target = comp
            break
    if target is None:
        raise ValueError(f"Competition not found with date={comp_date}")

    if target.get("projected_at_t_minus_1w") is None:
        comp_dt = datetime.strptime(comp_date, "%Y-%m-%d").date()
        snapshot_date = comp_dt - timedelta(days=7)
        program, _ = _snapshot_competitions_in_program(program, snapshot_date, allow_retrospective=allow_retrospective)
        for comp in program.get("competitions", []) or []:
            if comp.get("date") == comp_date:
                target = comp
                break

    snapshot = target.get("projected_at_t_minus_1w") or {}
    from analytics import compute_prr
    prr = compute_prr(results, snapshot)

    completed_results = copy.deepcopy(results)
    completed_results["projected_at_t_minus_1w"] = snapshot
    completed_results["prr"] = prr

    target.update({
        "status": "completed",
        "results": completed_results,
        "body_weight_kg": body_weight_kg,
    })
    if post_meet_report is not None:
        target["post_meet_report"] = copy.deepcopy(post_meet_report)
    if snapshot:
        target["projected_at_t_minus_1w"] = snapshot
    if target.get("projection_snapshot_date") is None and snapshot:
        target["projection_snapshot_date"] = (datetime.strptime(comp_date, "%Y-%m-%d").date() - timedelta(days=7)).isoformat()

    meta = program.setdefault("meta", {})
    meta["updated_at"] = datetime.utcnow().isoformat()
    return target


# =============================================================================
# Tool Functions
# =============================================================================

async def health_get_program() -> dict:
    """Get the full training program.

    Returns:
        Full program dict from cache or DynamoDB

    Raises:
        ProgramNotFoundError: If no program exists
        RuntimeError: If store not initialized or DynamoDB fails
    """
    store = _get_store()
    return await store.get_program()


async def health_comp_countdown() -> dict:
    """Calculate competition countdown metrics.

    Uses program.meta.comp_date and current date to calculate:
    - Days and weeks until competition
    - Current training week and phase
    - Whether currently in a break period
    - Number of remaining sessions

    Returns:
        {
            "days_to_comp": 98,
            "weeks_to_comp": 14,
            "current_week": 2,
            "current_phase": "Hypertrophy",
            "in_break": false,
            "next_break": null,
            "sessions_remaining": 52
        }

    Raises:
        ProgramNotFoundError: If no program exists
        RuntimeError: If store not initialized or DynamoDB fails
    """
    store = _get_store()
    program = await store.get_program()

    meta = program.get("meta", {})
    comp_date_str = meta.get("comp_date")

    today = date.today()

    # Calculate days/weeks to comp
    if comp_date_str:
        try:
            comp_date = datetime.strptime(comp_date_str, "%Y-%m-%d").date()
            days_to_comp = (comp_date - today).days
            weeks_to_comp = days_to_comp // 7
        except ValueError:
            days_to_comp = None
            weeks_to_comp = None
    else:
        days_to_comp = None
        weeks_to_comp = None

    # Calculate current week from program start
    program_start_str = meta.get("program_start")
    if program_start_str:
        try:
            program_start = datetime.strptime(program_start_str, "%Y-%m-%d").date()
            days_since_start = (today - program_start).days
            current_week = max(1, (days_since_start // 7) + 1)
        except ValueError:
            current_week = 1
    else:
        current_week = 1

    # Find current phase
    phases = program.get("phases", [])
    current_phase = None
    for phase in phases:
        start_week = phase.get("start_week", 0)
        end_week = phase.get("end_week", 0)
        if start_week <= current_week <= end_week:
            current_phase = phase.get("name", "Unknown")
            break

    # Check if in break period
    breaks = program.get("breaks", [])
    in_break = False
    next_break = None

    for break_period in breaks:
        try:
            break_start = datetime.strptime(
                break_period.get("start", ""), "%Y-%m-%d"
            ).date()
            break_end = datetime.strptime(
                break_period.get("end", ""), "%Y-%m-%d"
            ).date()

            if break_start <= today <= break_end:
                in_break = True
                break

            # Track next break
            if break_start > today:
                if next_break is None or break_start < datetime.strptime(
                    next_break, "%Y-%m-%d"
                ).date():
                    next_break = break_period.get("start")
        except (ValueError, KeyError):
            continue

    # Count remaining sessions
    sessions = program.get("sessions", [])
    sessions_remaining = sum(
        1 for s in sessions
        if not s.get("completed", False)
    )

    return {
        "days_to_comp": days_to_comp,
        "weeks_to_comp": weeks_to_comp,
        "current_week": current_week,
        "current_phase": current_phase,
        "in_break": in_break,
        "next_break": next_break,
        "sessions_remaining": sessions_remaining,
    }


async def health_update_session(date_str: str, patch: dict) -> dict:
    """Update a session by date with the given patch.

    Validates date format and patch keys before applying.

    Args:
        date_str: ISO8601 date string (YYYY-MM-DD)
        patch: Dict with session fields to update

    Allowed patch keys:
        - completed: bool
        - session_rpe: float
        - body_weight_kg: float
        - session_notes: str
        - exercises: list

    Returns:
        Updated session dict (not full program)

    Raises:
        ValueError: If date format invalid, patch keys invalid, or session not found
        RuntimeError: If store not initialized or DynamoDB fails
    """
    # Validate date format
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        raise ValueError(f"Invalid date format: {date_str}. Expected YYYY-MM-DD.")

    # Validate patch keys
    allowed_keys = {"completed", "session_rpe", "body_weight_kg", "session_notes", "exercises"}
    unknown_keys = set(patch.keys()) - allowed_keys
    if unknown_keys:
        raise ValueError(f"Unknown patch keys: {unknown_keys}. Allowed: {allowed_keys}")

    store = _get_store()
    updated_program = await store.update_session(date_str, patch)

    # Find and return the updated session
    sessions = updated_program.get("sessions", [])
    for session in sessions:
        if session.get("date") == date_str:
            return session

    # Should not reach here if update_session worked correctly
    raise RuntimeError(f"Session update succeeded but session not found: {date_str}")


async def health_new_version(change_reason: str, patches: list[dict]) -> dict:
    """Create a new major version of the program.

    Args:
        change_reason: Human-readable reason for the version change
        patches: List of patches, each with "path" and "value" keys
                Example: {"path": "sessions[0].exercises[1].kg", "value": 180}

    Returns:
        {"new_version": int, "change_reason": str}

    Raises:
        ValueError: If patch format invalid
        RuntimeError: If store not initialized or DynamoDB fails
    """
    store = _get_store()
    updated_program = await store.new_version(patches, change_reason)

    version_label = updated_program.get("meta", {}).get("version_label", "unknown")

    return {
        "new_version": version_label,
        "change_reason": change_reason,
    }


def kg_to_lb(kg: float) -> dict:
    """Convert kilograms to pounds.

    Args:
        kg: Weight in kilograms

    Returns:
        {"kg": kg, "lb": rounded_pounds}

    Raises:
        ValueError: If kg <= 0
    """
    if kg <= 0:
        raise ValueError("kg must be positive")

    lb = round(kg * 2.20462, 1)
    return {"kg": kg, "lb": lb}


def lb_to_kg(lb: float) -> dict:
    """Convert pounds to kilograms.

    Args:
        lb: Weight in pounds

    Returns:
        {"lb": lb, "kg": rounded_kg}

    Raises:
        ValueError: If lb <= 0
    """
    if lb <= 0:
        raise ValueError("lb must be positive")

    kg = round(lb / 2.20462, 2)
    return {"lb": lb, "kg": kg}


def ipf_weight_classes(sex: str) -> dict:
    """Get IPF weight classes for the given sex.

    Static data - no network calls.

    Args:
        sex: "M" or "F"

    Returns:
        {
            "sex": "M",
            "classes_kg": [59, 66, 74, 83, 93, 105, 120, "120+"],
            "operator_class_kg": 83  # From program or null
        }

    Raises:
        ValueError: If sex not in ["M", "F"]
    """
    if sex not in ["M", "F"]:
        raise ValueError(f"Invalid sex: {sex}. Must be 'M' or 'F'.")

    CLASSES = {
        "M": [59, 66, 74, 83, 93, 105, 120, "120+"],
        "F": [47, 52, 57, 63, 69, 76, 84, "84+"],
    }

    # Try to get operator's weight class from program
    operator_class_kg = None
    if _store is not None:
        try:
            # This is sync but we're in a sync function
            # The cache should be warm after startup
            import asyncio
            loop = asyncio.get_running_loop()
            # Create a task to get the program
            future = asyncio.ensure_future(_store.get_program())
            try:
                program = loop.run_until_complete(future)
                operator_class_kg = program.get("meta", {}).get("weight_class_kg")
            except:
                # Cache might not be warm, that's okay
                pass
        except RuntimeError:
            # No running loop, try to get from cache directly
            if _store._cache is not None:
                operator_class_kg = _store._cache.get("meta", {}).get("weight_class_kg")

    return {
        "sex": sex,
        "classes_kg": CLASSES[sex],
        "operator_class_kg": operator_class_kg,
    }


def pct_of_max(max_kg: float, pct: float) -> dict:
    """Calculate percentage of max weight.

    Args:
        max_kg: Maximum weight in kg
        pct: Percentage (0-150, not 0-1)

    Returns:
        {
            "max_kg": 185.0,
            "pct": 85.0,
            "raw_kg": 157.25,
            "rounded_2_5_kg": 157.5,
            "lb": 347.2
        }

    Raises:
        ValueError: If max_kg <= 0 or pct not in (0, 150]
    """
    if max_kg <= 0:
        raise ValueError("max_kg must be positive")
    if not (0 < pct <= 150):
        raise ValueError("pct must be in range (0, 150]")

    raw_kg = max_kg * (pct / 100)
    rounded_2_5_kg = round(raw_kg / 2.5) * 2.5
    lb = round(raw_kg * 2.20462, 1)

    return {
        "max_kg": max_kg,
        "pct": pct,
        "raw_kg": round(raw_kg, 2),
        "rounded_2_5_kg": rounded_2_5_kg,
        "lb": lb,
    }


async def calculate_attempts(
    lift: str,
    opener_kg: float,
    j1_override: float | None = None,
    j2_override: float | None = None,
    last_felt: str | None = None,
) -> dict:
    """Calculate competition attempts based on program preferences.

    Args:
        lift: "squat", "bench", or "deadlift"
        opener_kg: First attempt weight in kg
        j1_override: Override jump 1 from program prefs (optional)
        j2_override: Override jump 2 from program prefs (optional)
        last_felt: "hard" to halve j2 (optional)

    Returns:
        {
            "lift": "squat",
            "attempt_1_kg": 160.0,
            "attempt_2_kg": 180.0,
            "attempt_3_kg": 200.0,
            "jumps_used": {"j1": 20, "j2": 20},
            "warnings": ["Attempt 3 exceeds current max..."]
        }

    Raises:
        ValueError: If lift not in valid list
    """
    valid_lifts = ["squat", "bench", "deadlift"]
    if lift not in valid_lifts:
        raise ValueError(f"Invalid lift: {lift}. Must be one of {valid_lifts}")

    store = _get_store()
    program = await store.get_program()

    # Get default jumps from program prefs
    operator_prefs = program.get("operator_prefs", {})
    attempt_jumps = operator_prefs.get("attempt_jumps", {})
    lift_jumps = attempt_jumps.get(lift, {"j1": 10, "j2": 10})

    j1 = j1_override if j1_override is not None else lift_jumps.get("j1", 10)
    j2 = j2_override if j2_override is not None else lift_jumps.get("j2", 10)

    # Adjust j2 if last felt hard
    if last_felt == "hard":
        j2 = round(j2 / 2 / 2.5) * 2.5  # Halve and round to nearest 2.5

    # Calculate attempts
    attempt_1 = opener_kg
    attempt_2 = round((attempt_1 + j1) / 2.5) * 2.5
    attempt_3 = round((attempt_2 + j2) / 2.5) * 2.5

    # Get current max for validation
    current_maxes = program.get("current_maxes", {})
    current_max = current_maxes.get(lift)

    warnings = []

    # Warn if opener < 70% of max
    if current_max:
        min_opener = current_max * 0.7
        if opener_kg < min_opener:
            warnings.append(
                f"Opener {opener_kg}kg is below 70% of current max ({current_max}kg). "
                f"Consider an opener of at least {round(min_opener / 2.5) * 2.5}kg."
            )

        # Warn if attempt 3 exceeds max
        if attempt_3 > current_max:
            warnings.append(
                f"Attempt 3 ({attempt_3}kg) exceeds current max of {current_max}kg — "
                "confirm this is a target PR."
            )

    return {
        "lift": lift,
        "attempt_1_kg": attempt_1,
        "attempt_2_kg": attempt_2,
        "attempt_3_kg": attempt_3,
        "jumps_used": {"j1": j1, "j2": j2},
        "warnings": warnings,
    }


async def health_get_meta() -> dict:
    """Get program metadata without the full program.

    Returns:
        Dict with comp_date, program_start, targets, version, weight_class,
        training_notes, change_log, and other meta fields.
    """
    store = _get_store()
    program = await store.get_program()
    return program.get("meta", {})


async def health_get_phases() -> list[dict]:
    """Get training phases (name, weeks, intent).

    Returns:
        List of phase dicts sorted by start_week.
    """
    store = _get_store()
    program = await store.get_program()
    return program.get("phases", [])


async def health_get_current_maxes() -> dict:
    """Get current competition maxes.

    Returns:
        {squat: kg, bench: kg, deadlift: kg}
    """
    store = _get_store()
    program = await store.get_program()
    return program.get("current_maxes", {})


async def health_get_goals() -> list[dict]:
    """Get explicit goals attached to the current program block."""
    store = _get_store()
    program = await store.get_program()
    return program.get("goals", []) or []


async def health_get_federation_library() -> dict:
    """Get the shared federation and qualification standards library."""
    return await _get_federation_store().get_library()


async def health_get_operator_prefs() -> dict:
    """Get operator preferences (attempt jumps, etc).

    Returns:
        Operator preferences dict including attempt_jumps per lift.
    """
    store = _get_store()
    program = await store.get_program()
    return program.get("operator_prefs", {})


async def health_get_breaks() -> list[dict]:
    """Get scheduled breaks/deload periods.

    Returns:
        List of {start, end} date strings.
    """
    store = _get_store()
    program = await store.get_program()
    return program.get("breaks", [])


async def days_until(target_date: str, label: str = "target") -> dict:
    """Calculate days until a target date.

    Args:
        target_date: ISO8601 date string (YYYY-MM-DD)
        label: Human label for the milestone (e.g., "comp", "deload start")

    Returns:
        {
            "label": "comp",
            "target_date": "2026-06-14",
            "today": "2026-03-07",
            "days_remaining": 99,
            "weeks_remaining": 14,
            "days_elapsed_since": null,
            "is_past": false
        }

    Raises:
        ValueError: If target_date format invalid
    """
    # Validate date format
    try:
        target = datetime.strptime(target_date, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(f"Invalid date format: {target_date}. Expected YYYY-MM-DD.")

    today = date.today()
    today_str = today.isoformat()

    delta = (target - today).days

    if delta > 0:
        # Future date
        return {
            "label": label,
            "target_date": target_date,
            "today": today_str,
            "days_remaining": delta,
            "weeks_remaining": delta // 7,
            "days_elapsed_since": None,
            "is_past": False,
        }
    else:
        # Past date
        return {
            "label": label,
            "target_date": target_date,
            "today": today_str,
            "days_remaining": 0,
            "weeks_remaining": 0,
            "days_elapsed_since": abs(delta),
            "is_past": True,
        }


async def health_rag_search(query: str, n_results: int = 4) -> list[dict]:
    """Search health documents using semantic search.

    Thin wrapper over HealthDocsRAG.query().

    Args:
        query: Search query
        n_results: Number of results to return (default 4)

    Returns:
        [{"text": str, "source": str, "score": float}, ...]

    Raises:
        RuntimeError: If RAG not initialized or search fails
    """
    if _rag is None:
        raise RuntimeError("Health RAG not initialized. Call init_tools() with rag parameter.")

    return await _rag.query(query, n_results=n_results)


# =============================================================================
# Granular Load Tools (Read-Only)
# =============================================================================

def _resolve_phase(session: dict, phases: list[dict]) -> dict:
    """Resolve the phase object for a session based on week_number.

    Args:
        session: Session dict with week_number
        phases: List of phase dicts from program

    Returns:
        Matching phase dict, or first phase if no match
    """
    week_number = session.get("week_number", 1)
    for phase in phases:
        start = phase.get("start_week", 0)
        end = phase.get("end_week", 99)
        if start <= week_number <= end:
            return phase
    return phases[0] if phases else {}


async def health_get_competition(date: str) -> dict:
    """Load a specific competition by date.

    Args:
        date: Competition date (YYYY-MM-DD)

    Returns:
        Full competition object including targets, between_comp_plan, comp_day_protocol

    Raises:
        ValueError: If competition not found
        ProgramNotFoundError: If no program exists
    """
    store = _get_store()
    program = await store.get_program()

    competitions = program.get("competitions", [])
    for comp in competitions:
        if comp.get("date") == date:
            return comp

    raise ValueError(f"Competition not found with date={date}")


async def health_list_competitions() -> list[dict]:
    """List all competitions with summary info.

    Returns:
        [{name, date, status, weight_class_kg, federation}, ...]
        Sorted by date ascending.
    """
    store = _get_store()
    program = await store.get_program()

    competitions = program.get("competitions", [])
    summaries = []
    for comp in competitions:
        summaries.append({
            "name": comp.get("name"),
            "date": comp.get("date"),
            "status": comp.get("status"),
            "weight_class_kg": comp.get("weight_class_kg"),
            "federation": comp.get("federation"),
        })

    # Sort by date ascending
    summaries.sort(key=lambda x: x.get("date", ""))
    return summaries


async def health_get_diet_notes(
    start_date: str | None = None,
    end_date: str | None = None
) -> list[dict]:
    """Get diet notes, optionally filtered by date range.

    Args:
        start_date: Optional start of range (YYYY-MM-DD)
        end_date: Optional end of range (YYYY-MM-DD)

    Returns:
        Array of {date, notes} sorted by date descending
    """
    store = _get_store()
    program = await store.get_program()

    diet_notes = program.get("diet_notes", [])

    # Filter by date range if specified
    if start_date or end_date:
        filtered = []
        for note in diet_notes:
            note_date = note.get("date", "")
            if start_date and note_date < start_date:
                continue
            if end_date and note_date > end_date:
                continue
            filtered.append(note)
        diet_notes = filtered

    # Sort by date descending (most recent first)
    diet_notes.sort(key=lambda x: x.get("date", ""), reverse=True)
    return diet_notes


async def health_get_session(date: str) -> dict:
    """Load a single session by date.

    Args:
        date: Session date (YYYY-MM-DD)

    Returns:
        Session object with exercises and resolved phase object

    Raises:
        ValueError: If session not found
    """
    store = _get_store()
    program = await store.get_program()

    phases = program.get("phases", [])
    sessions = program.get("sessions", [])

    for session in sessions:
        if session.get("date") == date:
            # Add resolved phase
            session_copy = dict(session)
            session_copy["phase"] = _resolve_phase(session, phases)
            return session_copy

    raise ValueError(f"Session not found with date={date}")


async def health_get_sessions_range(start_date: str, end_date: str) -> list[dict]:
    """Load sessions within a date range.

    Args:
        start_date: Start of range (YYYY-MM-DD)
        end_date: End of range (YYYY-MM-DD)

    Returns:
        Array of sessions in date order, each with resolved phase object
    """
    store = _get_store()
    program = await store.get_program()

    phases = program.get("phases", [])
    sessions = program.get("sessions", [])

    result = []
    for session in sessions:
        session_date = session.get("date", "")
        if start_date <= session_date <= end_date:
            session_copy = dict(session)
            session_copy["phase"] = _resolve_phase(session, phases)
            result.append(session_copy)

    # Sort by date ascending
    result.sort(key=lambda x: x.get("date", ""))
    return result


async def health_get_supplements() -> dict:
    """Load supplements and supplement phases.

    Returns:
        {supplements: [...], supplement_phases: [...]}
    """
    store = _get_store()
    program = await store.get_program()

    return {
        "supplements": program.get("supplements", []),
        "supplement_phases": program.get("supplement_phases", []),
    }


# =============================================================================
# Granular Edit Tools (Create Minor Version)
# =============================================================================

async def health_update_competition(date: str, patch: dict) -> dict:
    """Update a competition by date.

    Creates a new minor version of the program.

    Args:
        date: Competition date to update
        patch: Fields to update (targets, status, notes, between_comp_plan, etc.)

    Returns:
        Updated competition object

    Raises:
        ValueError: If competition not found
    """
    import copy

    store = _get_store()
    program = await store.get_program()
    new_program = copy.deepcopy(program)

    competitions = new_program.get("competitions", [])
    comp_idx = None
    for i, comp in enumerate(competitions):
        if comp.get("date") == date:
            comp_idx = i
            break

    if comp_idx is None:
        raise ValueError(f"Competition not found with date={date}")

    # Apply patch
    for key, value in patch.items():
        competitions[comp_idx][key] = value

    # Write new minor version
    await store._write_new_version(new_program, minor=True)

    return competitions[comp_idx]


async def health_snapshot_competition_projection(
    date: str,
    version: str = "current",
    allow_retrospective: bool = False,
) -> dict:
    """Snapshot projected maxes 7 days before competition day.

    Args:
        date: Snapshot date (YYYY-MM-DD). Competitions on date + 7 days are considered.
        version: Program version to update.
        allow_retrospective: Backfill completed competitions when the snapshot was missed.

    Returns:
        Summary dict with the updated competitions.
    """
    snapshot_date = datetime.strptime(date, "%Y-%m-%d").date()
    program, sk, _store = _load_program_version(version)
    program, updated = _snapshot_competitions_in_program(program, snapshot_date, allow_retrospective=allow_retrospective)
    if updated:
        _save_program_version(program, sk)
    return {
        "snapshot_date": snapshot_date.isoformat(),
        "updated": len(updated),
        "competitions": updated,
    }


async def health_complete_competition(
    date: str,
    results: dict,
    body_weight_kg: float,
    version: str = "current",
    allow_retrospective: bool = True,
    post_meet_report: Optional[dict] = None,
) -> dict:
    """Mark a competition as completed and compute PRR.

    Args:
        date: Competition date (YYYY-MM-DD)
        results: Best successful lift attempts / totals.
        body_weight_kg: Weigh-in body weight.
        version: Program version to update.
        allow_retrospective: Backfill a missing T-1 snapshot if needed.
        post_meet_report: Optional structured attempt/context report.

    Returns:
        Updated competition object.
    """
    program, sk, _store = _load_program_version(version)
    updated_comp = _complete_competition_in_program(
        program,
        date,
        results,
        body_weight_kg,
        allow_retrospective=allow_retrospective,
        post_meet_report=post_meet_report,
    )
    _save_program_version(program, sk)
    return updated_comp


async def health_update_diet_note(date: str, notes: str) -> dict:
    """Update or create a diet note for a specific date.

    Creates a new minor version of the program. Replaces existing content.

    Args:
        date: Date for the diet note (YYYY-MM-DD)
        notes: The diet notes content

    Returns:
        Updated diet note object {date, notes}
    """
    import copy

    store = _get_store()
    program = await store.get_program()
    new_program = copy.deepcopy(program)

    diet_notes = new_program.get("diet_notes", [])

    # Find existing or create new
    note_idx = None
    for i, note in enumerate(diet_notes):
        if note.get("date") == date:
            note_idx = i
            break

    new_note = {"date": date, "notes": notes}

    if note_idx is not None:
        diet_notes[note_idx] = new_note
    else:
        diet_notes.append(new_note)

    new_program["diet_notes"] = diet_notes

    # Write new minor version
    await store._write_new_version(new_program, minor=True)

    return new_note


async def health_update_supplements(patch: dict) -> dict:
    """Update supplements or supplement phases.

    Creates a new minor version of the program.

    Args:
        patch: {"supplements": [...]} or {"supplement_phases": [...]} or both

    Returns:
        Updated {supplements: [...], supplement_phases: [...]}
    """
    import copy

    store = _get_store()
    program = await store.get_program()
    new_program = copy.deepcopy(program)

    if "supplements" in patch:
        new_program["supplements"] = patch["supplements"]

    if "supplement_phases" in patch:
        new_program["supplement_phases"] = patch["supplement_phases"]

    # Write new minor version
    await store._write_new_version(new_program, minor=True)

    return {
        "supplements": new_program.get("supplements", []),
        "supplement_phases": new_program.get("supplement_phases", []),
    }


# =============================================================================
# Session CRUD
# =============================================================================

async def health_create_session(
    date: str,
    day: str,
    week_number: int,
    exercises: list[dict] | None = None,
    session_notes: str = "",
) -> dict:
    """Create a new training session.

    Args:
        date: Session date (YYYY-MM-DD)
        day: Day label e.g. "Monday"
        week_number: Training week number (integer)
        exercises: Optional list of exercise dicts {name, sets, reps, kg, rpe, notes}
        session_notes: Optional session notes

    Returns:
        The created session dict

    Raises:
        ValueError: If session already exists on that date
    """
    # Validate date format
    datetime.strptime(date, "%Y-%m-%d")

    store = _get_store()
    program = await store.get_program()
    table, active_pk, _ = _get_table_and_pk()
    program_sk = _resolve_program_sk(table, active_pk, "current")
    new_session = {
        "date": date,
        "day": day,
        "week": f"W{week_number}",
        "week_number": week_number,
        "block": "current",
        "status": "planned",
        "completed": False,
        "session_rpe": None,
        "body_weight_kg": None,
        "session_notes": session_notes,
        "planned_exercises": [],
        "exercises": exercises or [],
    }
    from session_store import SessionStore
    created = await SessionStore(
        table_name=os.environ.get("IF_SESSIONS_TABLE_NAME", "if-sessions"),
        pk=active_pk,
        region=os.environ.get("AWS_REGION", "ca-central-1"),
        source_table_name=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"),
    ).create_session(program_sk, new_session, program.get("phases", []))
    store.invalidate_cache()
    store._invalidate_analysis_cache()
    return created


async def health_delete_session(date: str) -> dict:
    """Delete a training session by date.

    Args:
        date: Session date (YYYY-MM-DD)

    Returns:
        {"deleted": date}

    Raises:
        ValueError: If session not found
    """
    store = _get_store()
    program = await store.get_program()
    table, active_pk, _ = _get_table_and_pk()
    program_sk = _resolve_program_sk(table, active_pk, "current")
    from session_store import SessionStore
    result = await SessionStore(
        table_name=os.environ.get("IF_SESSIONS_TABLE_NAME", "if-sessions"),
        pk=active_pk,
        region=os.environ.get("AWS_REGION", "ca-central-1"),
        source_table_name=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"),
    ).delete_session(program_sk, date)
    store.invalidate_cache()
    store._invalidate_analysis_cache()
    return result


async def health_reschedule_session(old_date: str, new_date: str) -> dict:
    """Move a session to a different date.

    Args:
        old_date: Current session date (YYYY-MM-DD)
        new_date: Target date (YYYY-MM-DD)

    Returns:
        The updated session dict

    Raises:
        ValueError: If old session not found or new date already occupied
    """
    datetime.strptime(old_date, "%Y-%m-%d")
    datetime.strptime(new_date, "%Y-%m-%d")

    store = _get_store()
    program = await store.get_program()
    table, active_pk, _ = _get_table_and_pk()
    program_sk = _resolve_program_sk(table, active_pk, "current")
    from session_store import SessionStore
    session_store = SessionStore(
        table_name=os.environ.get("IF_SESSIONS_TABLE_NAME", "if-sessions"),
        pk=active_pk,
        region=os.environ.get("AWS_REGION", "ca-central-1"),
        source_table_name=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"),
    )
    if await session_store.get_sessions_range(program_sk, new_date, new_date, program.get("phases", [])):
        raise ValueError(f"A session already exists on {new_date}")
    updated = await session_store.patch_session(
        program_sk,
        old_date,
        {"date": new_date},
        program.get("phases", []),
    )
    store.invalidate_cache()
    store._invalidate_analysis_cache()
    return updated


async def health_add_exercise(date: str, exercise: dict) -> dict:
    """Add an exercise to a session.

    Args:
        date: Session date (YYYY-MM-DD)
        exercise: Exercise dict with keys: name (required), sets, reps, kg, rpe, notes

    Returns:
        The updated session exercises list

    Raises:
        ValueError: If session not found or exercise missing name
    """
    if not exercise.get("name"):
        raise ValueError("exercise.name is required")

    store = _get_store()
    program = await store.get_program()
    table, active_pk, _ = _get_table_and_pk()
    program_sk = _resolve_program_sk(table, active_pk, "current")
    session = await health_get_session(date)
    exercises = list(session.get("exercises") or [])
    exercises.append(exercise)
    from session_store import SessionStore
    updated = await SessionStore(
        table_name=os.environ.get("IF_SESSIONS_TABLE_NAME", "if-sessions"),
        pk=active_pk,
        region=os.environ.get("AWS_REGION", "ca-central-1"),
        source_table_name=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"),
    ).patch_session(program_sk, date, {"exercises": exercises}, program.get("phases", []))
    store.invalidate_cache()
    store._invalidate_analysis_cache()
    return {"date": date, "exercises": updated.get("exercises", [])}


async def health_remove_exercise(date: str, exercise_index: int) -> dict:
    """Remove an exercise from a session by index.

    Args:
        date: Session date (YYYY-MM-DD)
        exercise_index: Zero-based index of the exercise to remove

    Returns:
        The updated session exercises list

    Raises:
        ValueError: If session not found or index out of range
    """
    store = _get_store()
    program = await store.get_program()
    table, active_pk, _ = _get_table_and_pk()
    program_sk = _resolve_program_sk(table, active_pk, "current")
    session = await health_get_session(date)
    exercises = list(session.get("exercises") or [])
    if exercise_index < 0 or exercise_index >= len(exercises):
        raise ValueError(f"Exercise index {exercise_index} out of range (0-{len(exercises)-1})")

    exercises.pop(exercise_index)

    from session_store import SessionStore
    await SessionStore(
        table_name=os.environ.get("IF_SESSIONS_TABLE_NAME", "if-sessions"),
        pk=active_pk,
        region=os.environ.get("AWS_REGION", "ca-central-1"),
        source_table_name=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"),
    ).patch_session(program_sk, date, {"exercises": exercises}, program.get("phases", []))
    store.invalidate_cache()
    store._invalidate_analysis_cache()
    return {"date": date, "exercises": exercises}


# =============================================================================
# Competition CRUD
# =============================================================================

async def health_create_competition(competition: dict) -> dict:
    """Create a new competition entry.

    Args:
        competition: Dict with required fields: name, date (YYYY-MM-DD), federation.
            Optional: federation_id, counts_toward_federation_ids, status
            (default "confirmed"), weight_class_kg, location, targets
            {squat_kg, bench_kg, deadlift_kg, total_kg}, notes.

    Returns:
        The created competition dict

    Raises:
        ValueError: If competition already exists on that date or missing required fields
    """
    import copy
    for field in ("name", "date", "federation"):
        if not competition.get(field):
            raise ValueError(f"competition.{field} is required")

    datetime.strptime(competition["date"], "%Y-%m-%d")

    store = _get_store()
    program = await store.get_program()
    new_program = copy.deepcopy(program)

    competitions = new_program.setdefault("competitions", [])
    if any(c.get("date") == competition["date"] for c in competitions):
        raise ValueError(f"Competition already exists on {competition['date']}")

    new_comp = {
        "name": competition["name"],
        "date": competition["date"],
        "federation": competition["federation"],
        "federation_id": competition.get("federation_id"),
        "counts_toward_federation_ids": _string_ids(competition.get("counts_toward_federation_ids")),
        "status": competition.get("status", "confirmed"),
        "weight_class_kg": competition.get("weight_class_kg"),
        "location": competition.get("location"),
        "targets": competition.get("targets", {}),
        "notes": competition.get("notes", ""),
    }
    competitions.append(new_comp)
    competitions.sort(key=lambda c: c.get("date", ""))

    await store._write_new_version(new_program, minor=True)
    return new_comp


async def health_delete_competition(date: str) -> dict:
    """Delete a competition by date.

    Args:
        date: Competition date (YYYY-MM-DD)

    Returns:
        {"deleted": date}

    Raises:
        ValueError: If competition not found
    """
    import copy
    store = _get_store()
    program = await store.get_program()
    new_program = copy.deepcopy(program)

    competitions = new_program.get("competitions", [])
    before = len(competitions)
    new_program["competitions"] = [c for c in competitions if c.get("date") != date]

    if len(new_program["competitions"]) == before:
        raise ValueError(f"Competition not found: {date}")

    await store._write_new_version(new_program, minor=True)
    return {"deleted": date}


# =============================================================================
# Diet Note Delete
# =============================================================================

async def health_delete_diet_note(date: str) -> dict:
    """Delete a diet note by date.

    Args:
        date: Diet note date (YYYY-MM-DD)

    Returns:
        {"deleted": date}

    Raises:
        ValueError: If diet note not found
    """
    import copy
    store = _get_store()
    program = await store.get_program()
    new_program = copy.deepcopy(program)

    notes = new_program.get("diet_notes", [])
    before = len(notes)
    new_program["diet_notes"] = [n for n in notes if n.get("date") != date]

    if len(new_program["diet_notes"]) == before:
        raise ValueError(f"Diet note not found: {date}")

    await store._write_new_version(new_program, minor=True)
    return {"deleted": date}


# =============================================================================
# Meta & Structure Updates
# =============================================================================

async def health_update_goals(goals: list[dict]) -> list[dict]:
    """Replace the explicit goals array on the current program block."""
    import copy

    if not isinstance(goals, list):
        raise ValueError("goals must be an array")

    cleaned_goals = [_sanitize_goal_record(goal) for goal in goals]

    goal_ids = [str(goal.get("id")) for goal in cleaned_goals]
    if len(goal_ids) != len(set(goal_ids)):
        raise ValueError("goals must have unique ids")

    store = _get_store()
    program = await store.get_program()
    new_program = copy.deepcopy(program)
    new_program["goals"] = cleaned_goals

    await store._write_new_version(new_program, minor=True)
    return cleaned_goals


async def health_update_federation_library(library: dict) -> dict:
    """Replace the shared federation library document."""
    payload = _build_federation_library_payload(library)
    return await _write_federation_library(payload)


async def health_update_meta(updates: dict) -> dict:
    """Update program metadata fields.

    Allowed fields: program_name, comp_date, target_squat_kg, target_bench_kg,
    target_dl_kg, target_total_kg, sex, weight_class_kg, current_body_weight_kg,
    federation, practicing_for, program_start.

    Args:
        updates: Dict of field -> new value

    Returns:
        Updated meta dict

    Raises:
        ValueError: If unknown fields are passed
    """
    import copy
    allowed = {
        "program_name", "comp_date", "target_squat_kg", "target_bench_kg",
        "target_dl_kg", "target_total_kg", "sex", "weight_class_kg",
        "current_body_weight_kg", "federation", "practicing_for", "program_start",
    }
    unknown = set(updates.keys()) - allowed
    if unknown:
        raise ValueError(f"Unknown meta fields: {unknown}. Allowed: {allowed}")

    store = _get_store()
    program = await store.get_program()
    new_program = copy.deepcopy(program)

    meta = new_program.setdefault("meta", {})
    for key, value in updates.items():
        meta[key] = value

    await store._write_new_version(new_program, minor=True)
    return meta


async def health_update_phases(phases: list[dict]) -> list[dict]:
    """Replace the full phases array.

    Each phase dict: name (required), start_week (int), end_week (int), intent (str).

    Args:
        phases: Complete list of phase dicts

    Returns:
        The updated phases list

    Raises:
        ValueError: If any phase is missing required fields
    """
    import copy
    for i, phase in enumerate(phases):
        if not phase.get("name"):
            raise ValueError(f"phases[{i}].name is required")

    store = _get_store()
    program = await store.get_program()
    new_program = copy.deepcopy(program)
    new_program["phases"] = phases

    await store._write_new_version(new_program, minor=True)
    return phases


async def health_update_current_maxes(
    squat_kg: float | None = None,
    bench_kg: float | None = None,
    deadlift_kg: float | None = None,
) -> dict:
    """Update current competition maxes.

    Args:
        squat_kg: New squat max in kg (omit to leave unchanged)
        bench_kg: New bench max in kg (omit to leave unchanged)
        deadlift_kg: New deadlift max in kg (omit to leave unchanged)

    Returns:
        Updated current_maxes dict

    Raises:
        ValueError: If no fields provided
    """
    import copy
    if squat_kg is None and bench_kg is None and deadlift_kg is None:
        raise ValueError("At least one max must be provided")

    store = _get_store()
    program = await store.get_program()
    new_program = copy.deepcopy(program)

    maxes = new_program.setdefault("current_maxes", {})
    if squat_kg is not None:
        maxes["squat"] = squat_kg
    if bench_kg is not None:
        maxes["bench"] = bench_kg
    if deadlift_kg is not None:
        maxes["deadlift"] = deadlift_kg

    await store._write_new_version(new_program, minor=True)
    return maxes


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


async def health_program_evaluation(refresh: bool = False, cache_only: bool = False) -> dict:
    """Generate a conservative full-block program evaluation.

    This tool is intentionally gated to the current block / full report and is
    cached on a weekly cadence so it does not re-run on every request.
    """
    import boto3

    from config import IF_HEALTH_TABLE_NAME, AWS_REGION
    from program_evaluation_ai import generate_program_evaluation_report

    store = _get_store()
    store.invalidate_cache()
    program = await store.get_program()
    federation_library = await _get_federation_store().get_library()
    active_pk = store.pk
    program_updated_at = str((program.get("meta") or {}).get("updated_at") or "")
    federation_library_updated_at = str(federation_library.get("updated_at") or "")
    sessions = [s for s in program.get("sessions", []) if (s.get("block") or "current") == "current"]

    completed_weeks = sorted({
        int(s.get("week_number"))
        for s in sessions
        if (s.get("completed") or s.get("status") in ("logged", "completed")) and s.get("week_number") is not None
    })
    if len(completed_weeks) < 4:
        return {
            "insufficient_data": True,
            "insufficient_data_reason": "At least 4 completed weeks are required for a useful full-block evaluation.",
            "cached": False,
            "generated_at": "",
            "window_start": "",
            "weeks": len(completed_weeks),
        }

    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    window_start = week_start.isoformat()
    cache_sk = f"program_eval#{window_start}"

    dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
    table = dynamodb.Table(IF_HEALTH_TABLE_NAME)

    if not refresh:
        cached = table.get_item(Key={"pk": active_pk, "sk": cache_sk}).get("Item")
        if cached and cached.get("report"):
            report = cached["report"]
            if (
                isinstance(report, dict)
                and str(cached.get("program_updated_at") or "") == program_updated_at
                and str(cached.get("federation_library_updated_at") or "") == federation_library_updated_at
            ):
                report["cached"] = True
                report["generated_at"] = cached.get("generated_at", "")
                report["window_start"] = window_start
                report["weeks"] = len(completed_weeks)
                return report

    if cache_only:
        return {
            "insufficient_data": True,
            "insufficient_data_reason": "No cached program evaluation exists. Generate it to run AI analysis.",
            "cache_miss": True,
            "cached": False,
            "generated_at": "",
            "window_start": window_start,
            "weeks": len(completed_weeks),
        }

    report = await generate_program_evaluation_report(program, federation_library=federation_library)
    generated_at = datetime.utcnow().isoformat() + "Z"
    report["cached"] = False
    report["generated_at"] = generated_at
    report["window_start"] = window_start
    report["weeks"] = len(completed_weeks)

    if not (report.get("insufficient_data") and str(report.get("insufficient_data_reason", "")).startswith("AI evaluation failed")):
        # DynamoDB does not support Python float — convert all floats to Decimal before writing
        dynamo_item = _floats_to_decimals({
            "pk": active_pk,
            "sk": cache_sk,
            "report": report,
            "generated_at": generated_at,
            "window_start": window_start,
            "weeks": len(completed_weeks),
            "program_updated_at": program_updated_at,
            "federation_library_updated_at": federation_library_updated_at,
        })
        table.put_item(Item=dynamo_item)

    return report

# =============================================================================
# Import & Template Tools
# =============================================================================

async def import_parse_file(base64_content: str, filename: str) -> dict:
    """Parse a spreadsheet file and stage it as a pending import."""
    import base64
    from import_classifier import file_hash, extract_xlsx, extract_csv, preclassify_rows
    from import_classify_ai import generate_classification_report
    from import_parse_ai import generate_import_parse_report
    from glossary_resolve_ai import generate_glossary_resolve_report

    file_bytes = base64.b64decode(base64_content)
    fhash = file_hash(file_bytes)
    
    # 1. Extraction
    if filename.lower().endswith(".xlsx"):
        rows, sheet_name = extract_xlsx(file_bytes)
    else:
        rows = extract_csv(file_bytes)
        sheet_name = "CSV"

    # 2. Classification
    classification = preclassify_rows(rows)
    if not classification:
        report = await generate_classification_report(rows)
        classification = report.get("classification", "ambiguous")

    # 3. AI Parse
    # Get athlete context for better parsing
    store = _get_store()
    try:
        program = await store.get_program()
        current_maxes = program.get("current_maxes", {})
        current_weeks = len(set(s.get("week_number") for s in program.get("sessions", []) if s.get("week_number")))
    except:
        current_maxes = {}
        current_weeks = 0

    athlete_context = {
        "current_maxes": current_maxes,
        "current_program_weeks": current_weeks
    }

    # Flatten rows to text for AI if it's too large, but usually we just send the JSON
    parse_result = await generate_import_parse_report(
        file_content=json.dumps(rows[:100], indent=2, default=str), # Limit rows for token safety
        file_name=filename,
        classification=classification,
        athlete_context=athlete_context
    )

    # 4. Glossary Resolution
    glossary_store = _get_glossary_store()
    glossary = await glossary_store.get_glossary()
    
    unique_names = list(set(
        ex.get("name") 
        for sess in parse_result.get("sessions", []) 
        for ex in sess.get("exercises", []) 
        if ex.get("name")
    ))
    
    # Fuzzy pre-match
    resolved = {}
    unresolved_names = []
    for name in unique_names:
        gid = await glossary_store.fuzzy_resolve(name, threshold=0.92)
        if gid:
            resolved[name] = gid
        else:
            unresolved_names.append(name)
            
    # AI resolution for the rest
    if unresolved_names:
        ai_res = await generate_glossary_resolve_report(unresolved_names, glossary)
        for res in ai_res.get("resolutions", []):
            if res.get("matched_id"):
                resolved[res["input"]] = res["matched_id"]

    # Map resolved IDs back into parse_result
    for sess in parse_result.get("sessions", []):
        for ex in sess.get("exercises", []):
            if ex.get("name") in resolved:
                ex["glossary_id"] = resolved[ex["name"]]

    # 5. Stage in DynamoDB
    import_store = _get_import_store()
    import_id = await import_store.stage_import({
        "import_type": "template" if classification == "template" else "session_import",
        "source_filename": filename,
        "source_file_hash": fhash,
        "ai_parse_result": parse_result,
    })

    return {
        "import_id": import_id,
        "classification": classification,
        "warnings": parse_result.get("warnings", []),
        "parse_notes": parse_result.get("parse_notes", "")
    }

async def import_apply(
    import_id: str, 
    merge_strategy: str = "append", 
    conflict_resolutions: list[dict] | None = None,
    start_date: str | None = None
) -> dict:
    """Apply a staged import to the program or template library."""
    import_store = _get_import_store()
    pending = await import_store.get_pending(import_id)
    if not pending:
        raise ValueError(f"Import not found: {import_id}")
        
    if pending.get("status") != "awaiting_review":
        raise ValueError(f"Import {import_id} has already been {pending.get('status')}")

    import_type = pending.get("import_type")
    parse_result = pending.get("ai_parse_result", {})

    if import_type == "template":
        template_store = _get_template_store()
        # Convert parse result to template format
        template = {
            "meta": {
                "name": f"Imported {pending.get('source_filename', 'template').split('.')[0]}",
                "description": parse_result.get("parse_notes", ""),
                "source_filename": pending.get("source_filename"),
                "source_file_hash": pending.get("source_file_hash"),
                "estimated_weeks": max([s.get("week_number", 0) for s in parse_result.get("sessions", [])] or [0]),
                "days_per_week": 4, # Guess or derive
                "archived": False
            },
            "phases": parse_result.get("phases", []),
            "sessions": parse_result.get("sessions", []),
            "required_maxes": list(set([
                ex.get("glossary_id") 
                for s in parse_result.get("sessions", []) 
                for ex in s.get("exercises", []) 
                if ex.get("glossary_id")
            ])),
            "glossary_resolution": {
                "resolved": [], # Fill based on resolution
                "unresolved": [],
                "auto_added": [],
                "resolution_status": "resolved"
            }
        }
        sk = await template_store.put_template(template)
        await import_store.mark_applied(import_id, datetime.now(timezone.utc).isoformat())
        return {"status": "applied", "target_sk": sk}
    else:
        # Session Import
        store = _get_store()
        program = await store.get_program()
        new_program = copy.deepcopy(program)
        
        # Merge logic based on merge_strategy
        staged_sessions = parse_result.get("sessions", [])
        if not staged_sessions:
            raise ValueError("No sessions found in staged import")
            
        existing_sessions = new_program.get("sessions", [])
        
        # Mapping of existing sessions by date
        existing_map = {s["date"]: s for s in existing_sessions}
        
        # Resolution map
        resolutions = {r["session_date"]: r["action"] for r in (conflict_resolutions or [])}
        
        applied_count = 0
        skipped_count = 0
        
        for staged in staged_sessions:
            s_date = staged.get("date")
            if not s_date:
                continue
                
            if s_date in existing_map:
                action = resolutions.get(s_date, merge_strategy)
                if action == "skip":
                    skipped_count += 1
                    continue
                elif action == "overwrite" or action == "replace_planned":
                    # Replace
                    existing_map[s_date].update(staged)
                    applied_count += 1
                elif action == "merge" or action == "append":
                    # Merge exercises
                    existing_map[s_date].setdefault("exercises", []).extend(staged.get("exercises", []))
                    existing_map[s_date].setdefault("planned_exercises", []).extend(staged.get("planned_exercises", []))
                    applied_count += 1
            else:
                # New session
                existing_sessions.append(staged)
                existing_map[s_date] = staged
                applied_count += 1
        
        # Re-sort sessions
        new_program["sessions"] = sorted(existing_sessions, key=lambda s: s.get("date", ""))
        
        # Write new version
        await store._write_new_version(new_program, minor=False)
        await import_store.mark_applied(import_id, datetime.now(timezone.utc).isoformat())
        
        return {
            "status": "applied", 
            "applied_count": applied_count, 
            "skipped_count": skipped_count,
            "new_version": new_program["meta"].get("version_label")
        }


async def import_reject(import_id: str, reason: str | None = None) -> dict:
    import_store = _get_import_store()
    await import_store.mark_rejected(import_id, reason)
    return {"status": "rejected", "import_id": import_id}

async def import_list_pending(import_type: str | None = None) -> list[dict]:
    import_store = _get_import_store()
    return await import_store.list_pending(import_type)

async def import_get_pending(import_id: str) -> dict:
    """Get a single pending import by ID."""
    import_store = _get_import_store()
    pending = await import_store.get_pending(import_id)
    if not pending:
        raise ValueError(f"Import not found: {import_id}")
    return pending

async def template_list(include_archived: bool = False) -> list[dict]:
    template_store = _get_template_store()
    return await template_store.list_templates(include_archived)

async def template_get(sk: str) -> dict:
    template_store = _get_template_store()
    tpl = await template_store.get_template(sk)
    if not tpl:
        raise ValueError(f"Template not found: {sk}")
    return tpl

async def template_apply(
    sk: str, 
    target: str = "new_block", 
    start_date: str | None = None, 
    week_start_day: str = "Monday"
) -> dict:
    """Run max resolution gate and return missing or preview."""
    from template_apply import check_max_resolution_gate, concretize
    
    template_store = _get_template_store()
    template = await template_store.get_template(sk)
    
    store = _get_store()
    program = await store.get_program()
    current_maxes = program.get("current_maxes", {})
    
    glossary_store = _get_glossary_store()
    glossary = await glossary_store.get_glossary()
    
    missing = check_max_resolution_gate(template, current_maxes, glossary)
    if missing:
        return {"status": "gate_blocked", "missing_exercises": missing}
        
    # Preview concretization
    from datetime import date
    s_date = date.fromisoformat(start_date) if start_date else date.today()
    
    sessions = concretize(template, current_maxes, glossary, s_date, week_start_day)
    return {"status": "ready", "preview_sessions": sessions[:5]} # Return first 5 for preview

async def template_apply_confirm(
    sk: str, 
    backfilled_maxes: dict | None = None,
    start_date: str | None = None,
    week_start_day: str = "Monday"
) -> dict:
    """Concretize and write new program version."""
    from template_apply import concretize
    from datetime import date
    
    template_store = _get_template_store()
    template = await template_store.get_template(sk)
    
    store = _get_store()
    program = await store.get_program()
    current_maxes = dict(program.get("current_maxes", {}))
    if backfilled_maxes:
        current_maxes.update(backfilled_maxes)
        
    glossary_store = _get_glossary_store()
    glossary = await glossary_store.get_glossary()
    
    s_date = date.fromisoformat(start_date) if start_date else date.today()
    sessions = concretize(template, current_maxes, glossary, s_date, week_start_day)
    
    # Create new program version
    # Stripping existing sessions if it's a new block
    new_program = copy.deepcopy(program)
    new_program["sessions"] = sessions
    new_program["meta"]["template_lineage"] = {
        "applied_template_sk": sk,
        "applied_at": datetime.now(timezone.utc).isoformat(),
        "week_start_day": week_start_day,
        "start_date": s_date.isoformat()
    }
    
    await store._write_new_version(new_program, minor=False)
    return {"status": "applied", "program_version": new_program["meta"]["version_label"]}

async def template_evaluate(sk: str) -> dict:
    from template_evaluate_ai import generate_template_evaluate_report
    
    template_store = _get_template_store()
    template = await template_store.get_template(sk)
    
    # Get athlete context
    store = _get_store()
    program = await store.get_program()
    # Mocking advanced metrics for now
    athlete_context = {
        "current_maxes": program.get("current_maxes", {}),
        "dots_score": 350,
        "weeks_to_comp": 12
    }
    
    report = await generate_template_evaluate_report(template, athlete_context)
    
    # Store report on template
    template["meta"]["ai_evaluation"] = report
    # We need a way to update template meta without changing SK
    # For now, just return it
    return report

async def template_create_from_block(name: str, program_sk: str | None = None) -> dict:
    from template_convert import convert_block_to_template
    
    store = _get_store()
    if program_sk:
        # Load specific version - need ProgramStore to support this
        program = await store.get_program() # Fallback to current
    else:
        program = await store.get_program()
        
    # Get e1RM map for conversion
    e1rm_map = program.get("current_maxes", {})
    
    template = convert_block_to_template(program, e1rm_map)
    template["meta"]["name"] = name
    
    template_store = _get_template_store()
    sk = await template_store.put_template(template)
    return {"status": "created", "sk": sk}

async def template_copy(sk: str, new_name: str) -> dict:
    template_store = _get_template_store()
    new_sk = await template_store.copy_template(sk, new_name)
    return {"status": "copied", "new_sk": new_sk}

async def template_create_blank(name: str, description: str, estimated_weeks: int, days_per_week: int) -> dict:
    template = {
        "meta": {
            "name": name,
            "description": description,
            "estimated_weeks": estimated_weeks,
            "days_per_week": days_per_week,
            "archived": False,
        },
        "phases": [],
        "sessions": [],
        "glossary_resolution": {
            "resolved": [],
            "unresolved": [],
            "auto_added": [],
            "resolution_status": "resolved",
        },
        "required_maxes": [],
    }
    template_store = _get_template_store()
    sk = await template_store.put_template(template)
    return {"status": "created", "sk": sk}

async def template_update(sk: str, template: dict) -> dict:
    template = copy.deepcopy(template)
    sessions = template.get("sessions", [])
    resolved = set()
    unresolved = set()
    for session in sessions:
        for exercise in session.get("exercises", []):
            gid = exercise.get("glossary_id")
            if gid:
                resolved.add(gid)
            else:
                name = exercise.get("name", "")
                if name:
                    unresolved.add(name)

    if unresolved:
        resolution_status = "partial" if resolved else "unresolved"
    else:
        resolution_status = "resolved"

    template["glossary_resolution"] = {
        "resolved": sorted(resolved),
        "unresolved": sorted(unresolved),
        "auto_added": [],
        "resolution_status": resolution_status,
    }
    template["required_maxes"] = sorted(resolved)

    template_store = _get_template_store()
    await template_store.update_template(sk, template)
    return {"status": "updated", "sk": sk}

async def template_archive(sk: str) -> dict:
    template_store = _get_template_store()
    await template_store.archive_template(sk)
    return {"status": "archived", "sk": sk}

async def template_unarchive(sk: str) -> dict:
    template_store = _get_template_store()
    await template_store.unarchive_template(sk)
    return {"status": "unarchived", "sk": sk}

async def program_archive(sk: str) -> dict:
    store = _get_store()
    await store.archive(sk)
    return {"status": "archived", "sk": sk}

async def program_unarchive(sk: str) -> dict:
    store = _get_store()
    await store.unarchive(sk)
    return {"status": "unarchived", "sk": sk}

async def glossary_add(exercise: dict) -> dict:
    glossary_store = _get_glossary_store()
    exercise.setdefault("tertiary_muscles", [])
    eid = await glossary_store.add_exercise(exercise)
    return {"status": "added", "id": eid}

async def glossary_update(exercise_id: str, fields: dict) -> dict:
    glossary_store = _get_glossary_store()
    if "tertiary_muscles" in fields and fields["tertiary_muscles"] is None:
        fields["tertiary_muscles"] = []
    await glossary_store.update_exercise(exercise_id, fields)
    return {"status": "updated", "id": exercise_id}

async def glossary_set_e1rm(exercise_id: str, value_kg: float, method: str = "manual") -> dict:
    glossary_store = _get_glossary_store()
    await glossary_store.set_e1rm(exercise_id, value_kg, method=method)
    return {"status": "e1rm_set", "id": exercise_id, "value_kg": value_kg}

async def glossary_estimate_e1rm(exercise_id: str) -> dict:
    from e1rm_backfill_ai import generate_e1rm_backfill_report
    
    glossary_store = _get_glossary_store()
    glossary = await glossary_store.get_glossary()
    ex = next((e for e in glossary if e["id"] == exercise_id), None)
    if not ex:
        raise ValueError(f"Exercise not found: {exercise_id}")
        
    store = _get_store()
    program = await store.get_program()
    current_maxes = program.get("current_maxes", {})
    lift_profiles = program.get("lift_profiles", [])
    
    past_instances = {}
    for s in program.get("sessions", []):
        if not (s.get("completed") or s.get("status") in ("logged", "completed")):
            continue
        for ex_item in s.get("exercises", []):
            name = ex_item.get("name")
            if not name:
                continue
            if name not in past_instances:
                past_instances[name] = []
            past_instances[name].append({
                "date": s.get("date"),
                "sets": ex_item.get("sets"),
                "reps": ex_item.get("reps"),
                "kg": ex_item.get("kg"),
                "rpe": ex_item.get("rpe", ex_item.get("rpe_target")),
                "notes": ex_item.get("notes"),
            })
    
    report = await generate_e1rm_backfill_report(
        [ex["name"]], 
        current_maxes,
        lift_profiles=lift_profiles,
        past_instances=past_instances
    )
    estimates = report.get("estimates", [])
    if not estimates:
        return {"status": "error", "message": "AI failed to generate estimate"}
        
    est = estimates[0]
    await glossary_store.set_e1rm(
        exercise_id, 
        est["e1rm_kg"], 
        method="ai_backfill", 
        basis=est["basis"], 
        confidence="low", 
        manually_overridden=False
    )
    return {"status": "estimated", "id": exercise_id, "estimate": est}

async def glossary_estimate_fatigue(exercise_id: str) -> dict:
    from fatigue_ai import estimate_fatigue_profile
    
    glossary_store = _get_glossary_store()
    glossary = await glossary_store.get_glossary()
    ex = next((e for e in glossary if e["id"] == exercise_id), None)
    if not ex:
        raise ValueError(f"Exercise not found: {exercise_id}")
        
    store = _get_store()
    program = await store.get_program()
    
    profile = await estimate_fatigue_profile(
        ex,
        program_meta=program.get("meta", {}),
        lift_profiles=program.get("lift_profiles", [])
    )
    
    await glossary_store.update_exercise(exercise_id, {
        "fatigue_profile": {
            "axial": profile.get("axial"),
            "neural": profile.get("neural"),
            "peripheral": profile.get("peripheral"),
            "systemic": profile.get("systemic"),
        },
        "fatigue_profile_source": "ai_estimated",
        "fatigue_profile_reasoning": profile.get("reasoning"),
    })
    return {
        "status": "fatigue_estimated",
        "id": exercise_id,
        "profile": profile,
        "fatigue_profile": {
            "axial": profile.get("axial"),
            "neural": profile.get("neural"),
            "peripheral": profile.get("peripheral"),
            "systemic": profile.get("systemic"),
        },
        "reasoning": profile.get("reasoning"),
    }

async def glossary_estimate_muscles(exercise_id: str) -> dict:
    from muscle_group_ai import estimate_muscle_groups

    glossary_store = _get_glossary_store()
    glossary = await glossary_store.get_glossary()
    ex = next((e for e in glossary if e["id"] == exercise_id), None)
    if not ex:
        raise ValueError(f"Exercise not found: {exercise_id}")

    store = _get_store()
    program = await store.get_program()

    estimate = await estimate_muscle_groups(
        ex,
        program_meta=program.get("meta", {}),
        lift_profiles=program.get("lift_profiles", []),
    )

    await glossary_store.update_exercise(exercise_id, {
        "primary_muscles": estimate.get("primary_muscles", []),
        "secondary_muscles": estimate.get("secondary_muscles", []),
        "tertiary_muscles": estimate.get("tertiary_muscles", []),
    })

    return {
        "status": "muscles_estimated",
        "id": exercise_id,
        "primary_muscles": estimate.get("primary_muscles", []),
        "secondary_muscles": estimate.get("secondary_muscles", []),
        "tertiary_muscles": estimate.get("tertiary_muscles", []),
        "reasoning": estimate.get("reasoning", ""),
    }
