from __future__ import annotations

import asyncio
import copy
import logging
import os
import re
import uuid
from datetime import date, datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

_store: Optional["ProgramStore"] = None  # type: ignore[name-defined]
_template_store: Optional[Any] = None


def _get_store():
    """Lazily create and return the ProgramStore singleton."""
    global _store
    if _store is None:
        from program_store import ProgramStore as _PS
        _store = _PS(
            table_name=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"),
            pk=os.environ.get("HEALTH_PROGRAM_PK", "operator"),
            region=os.environ.get("AWS_REGION", "ca-central-1"),
        )
        logger.info("[HealthTools] ProgramStore initialised from env vars")
    return _store


def _store_for(pk: str | None):
    """Return the ProgramStore singleton, retargeted to pk when provided."""
    store = _get_store()
    if pk:
        store.pk = pk
    return store


def _get_template_store():
    global _template_store
    if _template_store is None:
        from template_store import TemplateStore
        _template_store = TemplateStore(
            table_name=os.environ.get("IF_TEMPLATES_TABLE_NAME", "if-health-templates"),
            pk=os.environ.get("IF_TEMPLATES_LIBRARY_PK", "template_library"),
            region=os.environ.get("AWS_REGION", "ca-central-1"),
        )
    return _template_store


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


WEEK_START_DAYS = {
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
}

def _valid_iso_date(value: str) -> bool:
    if not isinstance(value, str) or not re.match(r"^\d{4}-\d{2}-\d{2}$", value):
        return False
    try:
        return date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False

def _setup_current_program_sk(store) -> str | None:
    pointer = store.table.get_item(Key={"pk": store.pk, "sk": store.POINTER_SK}).get("Item")
    if pointer:
        ref_sk = pointer.get("ref_sk") or "program#v001"
        program = store.table.get_item(Key={"pk": store.pk, "sk": str(ref_sk)}).get("Item")
        return str(ref_sk) if program else None

    try:
        from boto3.dynamodb.conditions import Key
        result = store.table.query(
            KeyConditionExpression=Key("pk").eq(store.pk) & Key("sk").begins_with(store.PROGRAM_SK_PREFIX),
            Limit=1,
        )
        items = result.get("Items", [])
        return str(items[0]["sk"]) if items else None
    except Exception:
        program = store.table.get_item(Key={"pk": store.pk, "sk": "program#v001"}).get("Item")
        return "program#v001" if program else None

async def health_setup_status(args: dict | None = None) -> dict:
    """Return first-class setup state for the active health data partition."""
    pk = args.get("pk") if isinstance(args, dict) else None
    store = _store_for(pk)
    current_sk = await asyncio.get_running_loop().run_in_executor(
        None,
        lambda: _setup_current_program_sk(store),
    )
    has_current = bool(current_sk)
    return {
        "mapped_pk": store.pk,
        "hasCurrentProgram": has_current,
        "needsSetup": not has_current,
        "currentProgramSk": current_sk,
    }

def _setup_last_comp() -> dict:
    return {
        "date": "",
        "body_weight_kg": 0,
        "body_weight_lb": 0,
        "weight_class_kg": 0,
        "results": {
            "squat_kg": 0,
            "bench_kg": 0,
            "deadlift_kg": 0,
            "total_kg": 0,
        },
        "past_comp_day_protocol": {
            "caffeine_total_mg": 0,
            "caffeine_sequence": [],
            "carbs": "",
            "l_theanine": "",
            "outcome": "",
            "notes": "",
        },
    }

def _setup_goal() -> dict:
    return {
        "id": str(uuid.uuid4()),
        "title": "Lift 1 lb",
        "goal_type": "coach_defined",
        "priority": "optional",
        "target_total_kg": 0.45,
        "strategy_mode": "train_through",
        "risk_tolerance": "low",
    }

def _setup_phases(template: dict | None = None) -> list[dict]:
    if template:
        phases = []
        for phase in template.get("phases") or []:
            if not isinstance(phase, dict):
                continue
            phases.append({
                "name": phase.get("name") or "Base",
                "intent": phase.get("intent") or "",
                "start_week": int(phase.get("week_start") or phase.get("start_week") or 1),
                "end_week": int(phase.get("week_end") or phase.get("end_week") or 1),
                **({"target_rpe_min": phase.get("target_rpe_min")} if phase.get("target_rpe_min") is not None else {}),
                **({"target_rpe_max": phase.get("target_rpe_max")} if phase.get("target_rpe_max") is not None else {}),
                "block": "current",
            })
        if phases:
            return phases

    return [{
        "name": "Base",
        "intent": "Initial setup block",
        "start_week": 1,
        "end_week": 4,
        "block": "current",
    }]

def _positive_maxes(maxes: dict | None) -> dict[str, float]:
    if not isinstance(maxes, dict):
        return {}
    out: dict[str, float] = {}
    for key, value in maxes.items():
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if number > 0:
            out[str(key)] = number
    return out

def _setup_template(sk: str) -> dict | None:
    active_pk = _get_store().pk
    template_store = _get_template_store()
    return template_store.get_template_sync(sk, actor_pk=active_pk)

def _setup_missing_maxes(template: dict, maxes: dict[str, float]) -> list[str]:
    missing = []
    for exercise_id in template.get("required_maxes") or []:
        if maxes.get(str(exercise_id)) is None:
            missing.append(str(exercise_id))
    return missing

def _setup_concretize_template(
    template: dict,
    maxes: dict[str, float],
    start_date: str,
    week_start_day: str,
) -> list[dict]:
    from .template_apply import concretize

    sessions = concretize(
        template,
        maxes,
        [],
        date.fromisoformat(start_date),
        week_start_day,
    )
    for session in sessions:
        session["id"] = str(uuid.uuid4())
        session["block"] = "current"
        session.setdefault("session_rpe", None)
        session.setdefault("body_weight_kg", None)
        session.setdefault("session_notes", "")
        session.setdefault("planned_exercises", [])
        session.setdefault("exercises", [])
        session.setdefault("status", "planned")
        session.setdefault("completed", False)
    return sessions

def _setup_program(
    pk: str,
    mode: str,
    program_name: str | None,
    start_date: str,
    week_start_day: str,
    maxes: dict[str, float],
    template: dict | None = None,
    template_sk: str | None = None,
) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    squat = maxes.get("squat", 0)
    bench = maxes.get("bench", 0)
    deadlift = maxes.get("deadlift", 0)
    total = squat + bench + deadlift

    program = {
        "pk": pk,
        "sk": "program#v001",
        "meta": {
            "program_name": (program_name or "").strip() or "Getting Started",
            "program_start": start_date,
            "comp_date": "",
            "federation": "",
            "practicing_for": "",
            "version_label": "v001",
            "weight_class_kg": 0,
            "weight_class_confirm_by": "",
            "current_body_weight_kg": 0,
            "current_body_weight_lb": 0,
            "target_squat_kg": squat,
            "target_bench_kg": bench,
            "target_dl_kg": deadlift,
            "target_total_kg": total if total > 0 else 0.45,
            "attempt_pct": {"opener": 0.9, "second": 0.955, "third": 1.0},
            "training_notes": [],
            "change_log": [{
                "action": "initialized",
                "date": now,
                "note": "Initialized from starter template" if mode == "template" else "Initialized from onboarding",
            }],
            "block_notes": [],
            "updated_at": now,
            "last_comp": _setup_last_comp(),
            "manual_maxes": {
                "squat": squat,
                "bench": bench,
                "deadlift": deadlift,
            },
            "block_start_maxes": {
                "current": {
                    "squat_kg": squat or None,
                    "bench_kg": bench or None,
                    "deadlift_kg": deadlift or None,
                    "total_kg": total or None,
                    "source": "manual",
                    "updated_at": now,
                }
            },
            "program_week_start_day": week_start_day,
            "block_week_start_days": {"current": week_start_day},
        },
        "phases": _setup_phases(template),
        "sessions": _setup_concretize_template(template, maxes, start_date, week_start_day) if template else [],
        "competitions": [],
        "goals": [_setup_goal()],
        "diet_notes": [],
        "supplements": [],
        "supplement_phases": [],
        "lift_profiles": [],
        "current_maxes": {
            "squat": squat or None,
            "bench": bench or None,
            "deadlift": deadlift or None,
            "method": "manual",
        },
    }
    if template and template_sk:
        program["meta"]["template_lineage"] = {
            "applied_template_sk": template_sk,
            "applied_at": now,
            "week_start_day": week_start_day,
            "start_date": start_date,
        }
    return program

def _write_initial_program_sync(store, program: dict) -> None:
    program_item = copy.deepcopy(program)
    sessions = program_item.pop("sessions", [])
    store.table.put_item(
        Item=_floats_to_decimals(program_item),
        ConditionExpression="attribute_not_exists(pk) AND attribute_not_exists(sk)",
    )
    if isinstance(sessions, list) and sessions:
        store._get_session_store().replace_program_sessions_sync(
            "program#v001",
            sessions,
            program.get("phases", []) if isinstance(program.get("phases"), list) else [],
        )
    store.table.put_item(
        Item={
            "pk": store.pk,
            "sk": store.POINTER_SK,
            "version": 1,
            "ref_sk": "program#v001",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        ConditionExpression="attribute_not_exists(pk) AND attribute_not_exists(sk)",
    )
    store.invalidate_cache()

async def health_setup_initialize(
    args: dict | None = None,
    mode: str | None = None,
    start_date: str | None = None,
    week_start_day: str | None = None,
    program_name: str | None = None,
    template_sk: str | None = None,
    maxes: dict | None = None,
) -> dict:
    """Initialize a no-data user's first training block for the active partition."""
    if isinstance(args, dict):
        if mode is None:
            mode = args.get("mode")
        if start_date is None:
            start_date = args.get("start_date")
        if week_start_day is None:
            week_start_day = args.get("week_start_day")
        if program_name is None:
            program_name = args.get("program_name")
        if template_sk is None:
            template_sk = args.get("template_sk")
        if maxes is None:
            maxes = args.get("maxes")
    pk = args.get("pk") if isinstance(args, dict) else None
    if mode not in {"blank", "manual_sessions", "template"}:
        raise ValueError("INVALID_SETUP_MODE: mode must be blank, manual_sessions, or template")
    if not _valid_iso_date(start_date):
        raise ValueError("INVALID_START_DATE: start_date must be YYYY-MM-DD")
    if week_start_day not in WEEK_START_DAYS:
        raise ValueError("INVALID_WEEK_START_DAY: week_start_day must be a weekday name")

    store = _store_for(pk)
    status = await health_setup_status(args)
    if status["hasCurrentProgram"]:
        raise ValueError("ALREADY_INITIALIZED: Current program already exists")

    positive_maxes = _positive_maxes(maxes)
    template = None
    if mode == "template":
        if not template_sk:
            raise ValueError("TEMPLATE_REQUIRED: template_sk is required for template setup")
        template = _setup_template(template_sk)
        if not template:
            raise ValueError("TEMPLATE_NOT_FOUND: Template not found")
        missing = _setup_missing_maxes(template, positive_maxes)
        if missing:
            return {
                "status": "gate_blocked",
                "missingMaxes": missing,
                "templateSk": template_sk,
                "startDate": start_date,
                "weekStartDay": week_start_day,
            }

    program = _setup_program(
        store.pk,
        mode,
        program_name,
        start_date,
        week_start_day,
        positive_maxes,
        template,
        template_sk,
    )

    try:
        await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: _write_initial_program_sync(store, program),
        )
    except Exception as exc:
        if exc.__class__.__name__ == "ConditionalCheckFailedException":
            raise ValueError("ALREADY_INITIALIZED: Current program already exists") from exc
        raise

    return {
        "status": "initialized",
        "mode": mode,
        "programSk": "program#v001",
        "sessionCount": len(program.get("sessions") or []),
    }