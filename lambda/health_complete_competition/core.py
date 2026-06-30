from __future__ import annotations

import copy
import logging
import os
from datetime import date, datetime, timedelta
from typing import Any, Optional

logger = logging.getLogger(__name__)

_store: Optional["ProgramStore"] = None  # type: ignore[name-defined]


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
    from .analytics import meet_projection

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
    from .analytics import compute_prr
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
