from __future__ import annotations
import logging
import uuid
from datetime import datetime, timezone
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