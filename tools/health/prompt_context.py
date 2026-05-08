"""Shared context builders for health AI prompts.

These helpers turn the current program state into compact, structured
prompt sections for correlation / block evaluation models.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from analytics import calculate_dots


def _num(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _parse_date(value: str | None) -> Optional[date]:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _safe_dots(total_kg: float, bodyweight_kg: float, sex: str) -> float | None:
    if total_kg <= 0 or bodyweight_kg <= 0:
        return None
    try:
        return calculate_dots(total_kg, bodyweight_kg, sex)
    except Exception:
        return None


def _serialize_wellness(wellness: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(wellness, dict):
        return None
    values = {key: wellness.get(key) for key in ("sleep", "soreness", "mood", "stress", "energy", "recorded_at")}
    if all(values.get(key) is None for key in ("sleep", "soreness", "mood", "stress", "energy")):
        return None
    return values


def summarize_program_meta(meta: dict[str, Any]) -> dict[str, Any]:
    last_comp = meta.get("last_comp") or {}
    last_results = last_comp.get("results") or {}
    return {
        "program_name": meta.get("program_name"),
        "program_start": meta.get("program_start"),
        "comp_date": meta.get("comp_date"),
        "federation": meta.get("federation"),
        "practicing_for": meta.get("practicing_for"),
        "version_label": meta.get("version_label"),
        "sex": meta.get("sex"),
        "weight_class_kg": meta.get("weight_class_kg"),
        "current_body_weight_kg": meta.get("current_body_weight_kg"),
        "current_body_weight_lb": meta.get("current_body_weight_lb"),
        "target_total_kg": meta.get("target_total_kg"),
        "target_squat_kg": meta.get("target_squat_kg"),
        "target_bench_kg": meta.get("target_bench_kg"),
        "target_dl_kg": meta.get("target_dl_kg"),
        "height_cm": meta.get("height_cm"),
        "arm_wingspan_cm": meta.get("arm_wingspan_cm"),
        "leg_length_cm": meta.get("leg_length_cm"),
        "attempt_pct": meta.get("attempt_pct"),
        "last_comp": {
            "date": last_comp.get("date"),
            "body_weight_kg": last_comp.get("body_weight_kg"),
            "weight_class_kg": last_comp.get("weight_class_kg"),
            "results": last_results or None,
        } if last_comp else None,
    }


def summarize_lift_profiles(lift_profiles: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not lift_profiles:
        return []
    ordered: list[dict[str, Any]] = []
    for lift in ("squat", "bench", "deadlift"):
        profile = next((p for p in lift_profiles if p.get("lift") == lift), None)
        if not profile:
            continue
        ordered.append({
            "lift": profile.get("lift"),
            "style_notes": profile.get("style_notes") or "",
            "sticking_points": profile.get("sticking_points") or "",
            "primary_muscle": profile.get("primary_muscle") or "",
            "volume_tolerance": profile.get("volume_tolerance") or "moderate",
            "stimulus_coefficient": profile.get("stimulus_coefficient", 1.0),
        })
    return ordered


def summarize_phases(phases: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not phases:
        return []
    ordered = sorted(phases, key=lambda p: int(p.get("start_week", 0) or 0))
    return [
        {
            "name": phase.get("name"),
            "intent": phase.get("intent", ""),
            "start_week": phase.get("start_week"),
            "end_week": phase.get("end_week"),
            "target_rpe_min": phase.get("target_rpe_min"),
            "target_rpe_max": phase.get("target_rpe_max"),
            "days_per_week": phase.get("days_per_week"),
            "notes": phase.get("notes", ""),
        }
        for phase in ordered
    ]


def summarize_measurements(meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "height_cm": meta.get("height_cm"),
        "arm_wingspan_cm": meta.get("arm_wingspan_cm"),
        "leg_length_cm": meta.get("leg_length_cm"),
        "current_body_weight_kg": meta.get("current_body_weight_kg"),
        "weight_class_kg": meta.get("weight_class_kg"),
    }


def _positive_num(value: Any) -> float | None:
    num = _num(value)
    return round(num, 1) if num > 0 else None


def _goal_priority_rank(priority: str | None) -> int:
    order = {"primary": 0, "secondary": 1, "optional": 2}
    return order.get(str(priority or "optional"), 99)


def _goal_type_rank(goal_type: str | None) -> int:
    order = {
        "qualify_for_federation": 0,
        "hit_total": 1,
        "peak_for_meet": 2,
        "make_podium": 3,
        "rank_percentile": 4,
        "improve_dots": 5,
        "maintain_weight_class": 6,
        "conservative_pr": 7,
        "train_through": 8,
        "coach_defined": 9,
    }
    return order.get(str(goal_type or "coach_defined"), 99)


def _string_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    deduped: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in deduped:
            deduped.append(text)
    return deduped


def _federation_brief(federation: dict[str, Any] | None) -> dict[str, Any] | None:
    if not federation:
        return None
    return {
        "id": federation.get("id"),
        "name": federation.get("name"),
        "abbreviation": federation.get("abbreviation"),
    }


def _resolve_competition_host_federation(
    comp: dict[str, Any] | None,
    federations_by_id: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    if not isinstance(comp, dict):
        return None
    federations = federations_by_id or {}
    federation_id = str(comp.get("federation_id") or "").strip()
    if federation_id and federation_id in federations:
        return federations[federation_id]
    label = str(comp.get("federation") or "").strip().lower()
    if not label:
        return None
    for federation in federations.values():
        names = {
            str(federation.get("name") or "").strip().lower(),
            str(federation.get("abbreviation") or "").strip().lower(),
        }
        if label in names:
            return federation
    return None


def _competition_eligible_federation_ids(
    comp: dict[str, Any] | None,
    federations_by_id: dict[str, dict[str, Any]] | None = None,
) -> list[str]:
    if not isinstance(comp, dict):
        return []
    ids: list[str] = []
    host_federation = _resolve_competition_host_federation(comp, federations_by_id)
    host_federation_id = str((host_federation or {}).get("id") or comp.get("federation_id") or "").strip()
    if host_federation_id:
        ids.append(host_federation_id)
    for federation_id in _string_list(comp.get("counts_toward_federation_ids")):
        if federation_id not in ids:
            ids.append(federation_id)
    return ids


def _weight_class_alignment(
    competition_weight_class_kg: float | None,
    target_weight_class_kg: float | None,
    acceptable_weight_classes_kg: list[float] | None,
) -> str:
    acceptable = [_positive_num(value) for value in (acceptable_weight_classes_kg or [])]
    acceptable = [value for value in acceptable if value is not None]
    if competition_weight_class_kg is None:
        return "unknown"
    if target_weight_class_kg is None and not acceptable:
        return "unknown"
    if target_weight_class_kg is not None and competition_weight_class_kg == target_weight_class_kg:
        return "target"
    if competition_weight_class_kg in acceptable:
        return "acceptable"
    return "mismatch"


def _group_goals_by_competition(goals: list[dict[str, Any]] | None) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for goal in goals or []:
        comp_dates = _goal_target_competition_dates(goal)
        if not comp_dates:
            linked_date = str((goal.get("linked_competition") or {}).get("date") or "").strip()
            comp_dates = [linked_date] if linked_date else []
        for comp_date in comp_dates:
            grouped.setdefault(comp_date, []).append(goal)
    for comp_date in grouped:
        grouped[comp_date].sort(key=_goal_sort_key)
    return grouped


def _competition_strategy_pressure(goals_for_competition: list[dict[str, Any]] | None) -> str:
    if not goals_for_competition:
        return "aggressive"
    highest_rank = min(_goal_priority_rank(str(goal.get("priority"))) for goal in goals_for_competition)
    top_priority_goals = [
        goal for goal in goals_for_competition
        if _goal_priority_rank(str(goal.get("priority"))) == highest_rank
    ]
    strategies = {str(goal.get("strategy_mode") or "") for goal in top_priority_goals}
    if strategies.intersection({"max_total", "qualify", "podium"}):
        return "aggressive"
    if strategies.intersection({"minimum_total", "train_through", "conservative_pr"}):
        return "controlled"
    return "aggressive"


def _build_federation_maps(federation_library: dict[str, Any] | None) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    library = federation_library or {}
    federations = {
        str(item.get("id")): item
        for item in (library.get("federations") or [])
        if isinstance(item, dict) and item.get("id")
    }
    standards = {
        str(item.get("id")): item
        for item in (library.get("qualification_standards") or [])
        if isinstance(item, dict) and item.get("id")
    }
    return federations, standards


def _competition_goal_priorities(goals: list[dict[str, Any]] | None) -> dict[str, str]:
    priorities: dict[str, str] = {}
    for goal in goals or []:
        priority = str(goal.get("priority") or "optional")
        for comp_date in _goal_target_competition_dates(goal):
            existing = priorities.get(comp_date)
            if existing is None or _goal_priority_rank(priority) < _goal_priority_rank(existing):
                priorities[comp_date] = priority
    return priorities


def _goal_required_total(goal: dict[str, Any] | None) -> float | None:
    if not isinstance(goal, dict):
        return None
    required_total = _positive_num(goal.get("required_total_kg"))
    if required_total is not None:
        return required_total
    target_total = _positive_num(goal.get("target_total_kg"))
    if target_total is not None:
        return target_total
    return _positive_num((goal.get("linked_standard") or {}).get("required_total_kg"))


def _goal_success_metric(goal: dict[str, Any], target_total: float | None) -> dict[str, Any]:
    goal_type = str(goal.get("goal_type") or "")
    target_dots = _positive_num(goal.get("target_dots"))
    target_ipf_gl = _positive_num(goal.get("target_ipf_gl"))
    linked_standard_total = _positive_num((goal.get("linked_standard") or {}).get("required_total_kg"))
    if goal_type == "hit_total":
        return {
            "metric": "total_kg",
            "target_total_kg": target_total,
            "uses_qualification_standard": False,
            "instruction": "Judge this goal by target_total_kg only; qualifying standards are context, not the success bar.",
        }
    if goal_type == "improve_dots":
        return {
            "metric": "dots",
            "target_dots": target_dots,
            "uses_qualification_standard": False,
            "instruction": "Judge this goal by target_dots only.",
        }
    if goal_type == "qualify_for_federation":
        return {
            "metric": "qualification_total_kg",
            "target_total_kg": target_total,
            "linked_standard_total_kg": linked_standard_total,
            "uses_qualification_standard": True,
            "instruction": "Judge this goal by the goal-owned qualifying standard or explicit target_total_kg.",
        }
    if target_ipf_gl is not None:
        return {
            "metric": "ipf_gl",
            "target_ipf_gl": target_ipf_gl,
            "uses_qualification_standard": False,
            "instruction": "Judge this goal by target_ipf_gl only.",
        }
    return {
        "metric": "goal_type",
        "target_total_kg": target_total,
        "target_dots": target_dots,
        "target_ipf_gl": target_ipf_gl,
        "uses_qualification_standard": goal_type == "qualify_for_federation",
        "instruction": "Judge success by the explicit fields attached to this goal type.",
    }


def _goal_sort_key(goal: dict[str, Any]) -> tuple[int, int, float, str]:
    required_total = _goal_required_total(goal)
    return (
        _goal_priority_rank(str(goal.get("priority"))),
        _goal_type_rank(str(goal.get("goal_type"))),
        -(required_total or 0.0),
        str(goal.get("title") or ""),
    )


def _group_goals_by_eligible_opportunity(goals: list[dict[str, Any]] | None) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for goal in goals or []:
        for opportunity in goal.get("eligible_opportunities") or []:
            comp_date = str(opportunity.get("date") or "").strip()
            if not comp_date:
                continue
            grouped.setdefault(comp_date, []).append(goal)
    for comp_date in grouped:
        grouped[comp_date].sort(key=_goal_sort_key)
    return grouped


def _goal_target_competition_dates(goal: dict[str, Any] | None) -> list[str]:
    if not isinstance(goal, dict):
        return []
    return _string_list(list(goal.get("target_competition_dates") or []) + [goal.get("target_competition_date")])


def _goal_target_standard_ids(goal: dict[str, Any] | None) -> list[str]:
    if not isinstance(goal, dict):
        return []
    return _string_list(list(goal.get("target_standard_ids") or []) + [goal.get("target_standard_id")])


def _goal_linked_standards(goal: dict[str, Any], standards_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    linked: list[dict[str, Any]] = []
    for standard_id in _goal_target_standard_ids(goal):
        standard = standards_by_id.get(standard_id)
        if standard is not None:
            linked.append(standard)
    return linked


def _goal_primary_standard(goal: dict[str, Any], standards_by_id: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    standards = _goal_linked_standards(goal, standards_by_id)
    if not standards:
        return None
    target_federation_id = str(goal.get("target_federation_id") or "").strip()
    candidates = [
        standard for standard in standards
        if target_federation_id and str(standard.get("federation_id") or "") == target_federation_id
    ] or standards
    candidates.sort(key=lambda standard: -(_positive_num(standard.get("required_total_kg")) or 0.0))
    return candidates[0]


def summarize_goals(
    program: dict[str, Any],
    federation_library: dict[str, Any] | None = None,
    reference_date: date | None = None,
) -> dict[str, Any]:
    reference_date = reference_date or date.today()
    goals = sorted(
        program.get("goals") or [],
        key=lambda goal: (
            _goal_priority_rank(str(goal.get("priority"))),
            str((_goal_target_competition_dates(goal) or [goal.get("target_date") or ""])[0]),
            str(goal.get("title") or ""),
        ),
    )
    competition_list = [
        comp
        for comp in (program.get("competitions") or [])
        if isinstance(comp, dict) and comp.get("date")
    ]
    competitions = {
        str(comp.get("date")): comp
        for comp in competition_list
    }
    federations_by_id, standards_by_id = _build_federation_maps(federation_library)

    rows: list[dict[str, Any]] = []
    for goal in goals:
        target_competition_dates = _goal_target_competition_dates(goal)
        linked_standards = _goal_linked_standards(goal, standards_by_id)
        primary_standard = _goal_primary_standard(goal, standards_by_id)
        primary_competition = competitions.get(target_competition_dates[0]) if target_competition_dates else None
        target_date = goal.get("target_date") or (target_competition_dates[0] if target_competition_dates else None) or (primary_competition or {}).get("date")
        target_date_obj = _parse_date(target_date)
        target_total = _positive_num(goal.get("target_total_kg"))
        if target_total is None and primary_standard:
            target_total = _positive_num(primary_standard.get("required_total_kg"))
        target_weight_class = _positive_num(goal.get("target_weight_class_kg"))
        if target_weight_class is None and primary_standard:
            target_weight_class = _positive_num(primary_standard.get("weight_class_kg"))
        acceptable_weight_classes = [
            value
            for value in (_positive_num(item) for item in list(goal.get("acceptable_weight_classes_kg") or []))
            if value is not None
        ]
        federation = federations_by_id.get(str(goal.get("target_federation_id") or "")) or (
            federations_by_id.get(str(primary_standard.get("federation_id"))) if primary_standard else None
        )
        target_federation_id = str((federation or {}).get("id") or "")
        if not target_federation_id:
            target_federation_id = str((primary_standard or {}).get("federation_id") or "")
        eligible_opportunities: list[dict[str, Any]] = []
        for eligible_comp in sorted(competition_list, key=lambda item: str(item.get("date") or "")):
            eligible_federation_ids = _competition_eligible_federation_ids(eligible_comp, federations_by_id)
            matching_standards = [
                standard
                for standard in linked_standards
                if str(standard.get("federation_id") or "") in eligible_federation_ids
            ]
            preferred_matching_standards = [
                standard
                for standard in matching_standards
                if target_federation_id and str(standard.get("federation_id") or "") == target_federation_id
            ] or matching_standards
            federation_eligible = bool(preferred_matching_standards) if linked_standards else (target_federation_id in eligible_federation_ids if target_federation_id else None)
            eligible_weight_class = _positive_num(eligible_comp.get("weight_class_kg"))
            weight_class_alignment = _weight_class_alignment(
                eligible_weight_class,
                target_weight_class,
                acceptable_weight_classes,
            )
            if federation_eligible is False:
                continue
            if weight_class_alignment == "mismatch":
                continue
            eligible_opportunities.append(
                {
                    "name": eligible_comp.get("name"),
                    "date": eligible_comp.get("date"),
                    "status": eligible_comp.get("status"),
                    "host_federation_label": eligible_comp.get("federation"),
                    "host_federation": _federation_brief(_resolve_competition_host_federation(eligible_comp, federations_by_id)),
                    "goal_federation_eligible": federation_eligible,
                    "weight_class_alignment": weight_class_alignment,
                    "weight_class_kg": eligible_weight_class,
                    "matching_standard_ids": [str(standard.get("id")) for standard in preferred_matching_standards if standard.get("id")],
                    "matching_required_total_kg": max(
                        (_positive_num(standard.get("required_total_kg")) or 0.0)
                        for standard in preferred_matching_standards
                    ) if preferred_matching_standards else None,
                    "notes": eligible_comp.get("notes") or "",
                    "explicit_target": str(eligible_comp.get("date") or "") in target_competition_dates,
                }
            )
        linked_competitions = [
            {
                "name": competition.get("name"),
                "date": competition.get("date"),
                "status": competition.get("status"),
                "host_federation_label": competition.get("federation"),
                "host_federation": _federation_brief(_resolve_competition_host_federation(competition, federations_by_id)),
                "eligible_federations": [
                    _federation_brief(federations_by_id.get(federation_id))
                    for federation_id in _competition_eligible_federation_ids(competition, federations_by_id)
                    if _federation_brief(federations_by_id.get(federation_id)) is not None
                ],
                "goal_federation_eligible": next(
                    (
                        opportunity.get("goal_federation_eligible")
                        for opportunity in eligible_opportunities
                        if str(opportunity.get("date") or "") == str(competition.get("date") or "")
                    ),
                    None,
                ),
                "competition_weight_class_kg": _positive_num(competition.get("weight_class_kg")),
                "weight_class_alignment": next(
                    (
                        opportunity.get("weight_class_alignment")
                        for opportunity in eligible_opportunities
                        if str(opportunity.get("date") or "") == str(competition.get("date") or "")
                    ),
                    "unknown",
                ),
                "matching_standard_ids": next(
                    (
                        opportunity.get("matching_standard_ids")
                        for opportunity in eligible_opportunities
                        if str(opportunity.get("date") or "") == str(competition.get("date") or "")
                    ),
                    [],
                ),
                "matching_required_total_kg": next(
                    (
                        opportunity.get("matching_required_total_kg")
                        for opportunity in eligible_opportunities
                        if str(opportunity.get("date") or "") == str(competition.get("date") or "")
                    ),
                    None,
                ),
                "notes": competition.get("notes") or "",
            }
            for target_date in target_competition_dates
            if (competition := competitions.get(target_date)) is not None
        ]
        rows.append(
            {
                "id": goal.get("id"),
                "title": goal.get("title"),
                "goal_type": goal.get("goal_type"),
                "priority": goal.get("priority"),
                "strategy_mode": goal.get("strategy_mode"),
                "risk_tolerance": goal.get("risk_tolerance"),
                "target_competition_dates": target_competition_dates,
                "target_competition_date": target_competition_dates[0] if target_competition_dates else goal.get("target_competition_date"),
                "target_standard_ids": [str(standard.get("id")) for standard in linked_standards if standard.get("id")],
                "target_standard_id": str((primary_standard or {}).get("id") or goal.get("target_standard_id") or "") or None,
                "target_date": target_date,
                "weeks_to_target": round(((target_date_obj - reference_date).days / 7.0), 1) if target_date_obj else None,
                "target_total_kg": target_total,
                "required_total_kg": target_total,
                "target_dots": _positive_num(goal.get("target_dots")),
                "target_ipf_gl": _positive_num(goal.get("target_ipf_gl")),
                "success_metric": _goal_success_metric(goal, target_total),
                "target_weight_class_kg": target_weight_class,
                "acceptable_weight_classes_kg": acceptable_weight_classes,
                "max_acceptable_bodyweight_loss_pct": _positive_num(goal.get("max_acceptable_bodyweight_loss_pct")),
                "max_acceptable_water_cut_pct": _positive_num(goal.get("max_acceptable_water_cut_pct")),
                "linked_competition": linked_competitions[0] if linked_competitions else None,
                "linked_competitions": linked_competitions,
                "target_federation": _federation_brief(federation),
                "linked_standard": (
                    {
                        "id": primary_standard.get("id"),
                        "season_year": primary_standard.get("season_year"),
                        "sex": primary_standard.get("sex"),
                        "equipment": primary_standard.get("equipment"),
                        "event": primary_standard.get("event"),
                        "age_class": primary_standard.get("age_class"),
                        "division": primary_standard.get("division"),
                        "weight_class_kg": _positive_num(primary_standard.get("weight_class_kg")),
                        "required_total_kg": _positive_num(primary_standard.get("required_total_kg")),
                        "qualifying_start_date": primary_standard.get("qualifying_start_date"),
                        "qualifying_end_date": primary_standard.get("qualifying_end_date"),
                    }
                    if primary_standard
                    else None
                ),
                "linked_standards": [
                    {
                        "id": standard.get("id"),
                        "federation_id": standard.get("federation_id"),
                        "season_year": standard.get("season_year"),
                        "sex": standard.get("sex"),
                        "equipment": standard.get("equipment"),
                        "event": standard.get("event"),
                        "age_class": standard.get("age_class"),
                        "division": standard.get("division"),
                        "weight_class_kg": _positive_num(standard.get("weight_class_kg")),
                        "required_total_kg": _positive_num(standard.get("required_total_kg")),
                        "qualifying_start_date": standard.get("qualifying_start_date"),
                        "qualifying_end_date": standard.get("qualifying_end_date"),
                    }
                    for standard in linked_standards
                ],
                "eligible_opportunities": eligible_opportunities,
                "remaining_eligible_opportunities": len(
                    [
                        opportunity
                        for opportunity in eligible_opportunities
                        if (opp_date := _parse_date(opportunity.get("date"))) is not None and opp_date >= reference_date
                    ]
                ),
                "notes": goal.get("notes") or "",
            }
        )

    competition_goal_priorities = _competition_goal_priorities(goals)
    return {
        "goals": rows,
        "primary_goals": [row for row in rows if row.get("priority") == "primary"],
        "competition_goal_priorities": competition_goal_priorities,
    }


def summarize_competitions(
    program: dict[str, Any],
    reference_date: date | None = None,
    federation_library: dict[str, Any] | None = None,
    competition_goal_priorities: dict[str, str] | None = None,
) -> dict[str, Any]:
    meta = program.get("meta", {})
    competitions = sorted(program.get("competitions", []), key=lambda c: c.get("date", ""))
    reference_date = reference_date or date.today()
    sex = str(meta.get("sex", "male")).lower()
    fallback_bw = _num(meta.get("current_body_weight_kg", meta.get("bodyweight_kg", 0)))
    federations_by_id, _ = _build_federation_maps(federation_library)
    goal_summary = summarize_goals(program, federation_library=federation_library, reference_date=reference_date)
    goal_priorities = competition_goal_priorities or goal_summary.get("competition_goal_priorities") or {}
    goals_by_competition = _group_goals_by_competition(goal_summary.get("goals"))
    goals_by_opportunity = _group_goals_by_eligible_opportunity(goal_summary.get("goals"))

    rows: list[dict[str, Any]] = []
    for idx, comp in enumerate(competitions):
        comp_date = _parse_date(comp.get("date"))
        weeks_to_comp = round(((comp_date - reference_date).days / 7.0), 1) if comp_date else None
        bodyweight = _num(comp.get("body_weight_kg")) or fallback_bw
        results = comp.get("results") or {}
        targets = comp.get("targets") or {}
        host_federation = _resolve_competition_host_federation(comp, federations_by_id)
        eligible_federation_ids = _competition_eligible_federation_ids(comp, federations_by_id)
        eligible_federations = [
            federation_brief
            for federation_id in eligible_federation_ids
            if (federation_brief := _federation_brief(federations_by_id.get(federation_id))) is not None
        ]
        previous_date = _parse_date(competitions[idx - 1].get("date")) if idx > 0 else None
        next_date = _parse_date(competitions[idx + 1].get("date")) if idx + 1 < len(competitions) else None
        goal_priority = goal_priorities.get(str(comp.get("date") or ""))
        linked_goals = goals_by_competition.get(str(comp.get("date") or ""), [])
        opportunity_goals = goals_by_opportunity.get(str(comp.get("date") or ""), [])

        def _goal_payload(goal: dict[str, Any], explicit_target: bool) -> dict[str, Any]:
            linked_match = next(
                (
                    linked_comp
                    for linked_comp in goal.get("linked_competitions") or []
                    if str(linked_comp.get("date") or "") == str(comp.get("date") or "")
                ),
                None,
            )
            opportunity_match = next(
                (
                    opportunity
                    for opportunity in goal.get("eligible_opportunities") or []
                    if str(opportunity.get("date") or "") == str(comp.get("date") or "")
                ),
                None,
            )
            match = linked_match or opportunity_match or {}
            return {
                "id": goal.get("id"),
                "title": goal.get("title"),
                "goal_type": goal.get("goal_type"),
                "priority": goal.get("priority"),
                "strategy_mode": goal.get("strategy_mode"),
                "target_total_kg": goal.get("target_total_kg"),
                "required_total_kg": goal.get("required_total_kg"),
                "success_metric": goal.get("success_metric"),
                "target_weight_class_kg": goal.get("target_weight_class_kg"),
                "acceptable_weight_classes_kg": goal.get("acceptable_weight_classes_kg"),
                "target_federation": goal.get("target_federation"),
                "linked_standard": goal.get("linked_standard"),
                "linked_standards": goal.get("linked_standards"),
                "goal_federation_eligible": match.get("goal_federation_eligible"),
                "weight_class_alignment": match.get("weight_class_alignment"),
                "matching_standard_ids": match.get("matching_standard_ids", []),
                "matching_required_total_kg": match.get("matching_required_total_kg"),
                "remaining_eligible_opportunities": goal.get("remaining_eligible_opportunities"),
                "explicit_target": explicit_target,
                "notes": goal.get("notes") or "",
            }

        candidate_goals: dict[str, dict[str, Any]] = {}
        for goal in opportunity_goals:
            goal_id = str(goal.get("id") or goal.get("title") or "")
            if goal_id:
                candidate_goals[goal_id] = _goal_payload(goal, explicit_target=False)
        for goal in linked_goals:
            goal_id = str(goal.get("id") or goal.get("title") or "")
            if goal_id:
                candidate_goals[goal_id] = _goal_payload(goal, explicit_target=True)

        competition_goals = sorted(candidate_goals.values(), key=_goal_sort_key)
        governing_goal = competition_goals[0] if competition_goals else None
        role = "primary" if goal_priority == "primary" else ("practice" if competition_goals or idx < len(competitions) - 1 else "primary")
        row: dict[str, Any] = {
            "name": comp.get("name"),
            "date": comp.get("date"),
            "status": comp.get("status"),
            "role": role,
            "goal_priority": goal_priority,
            "weeks_to_comp": weeks_to_comp,
            "federation": comp.get("federation"),
            "federation_id": comp.get("federation_id"),
            "linked_federation": _federation_brief(host_federation),
            "eligible_federation_ids": eligible_federation_ids,
            "eligible_federations": eligible_federations,
            "counts_toward_federations": eligible_federations[1:] if len(eligible_federations) > 1 else [],
            "weight_class_kg": comp.get("weight_class_kg"),
            "bodyweight_kg": bodyweight if bodyweight > 0 else None,
            "hotel_required": bool(comp.get("hotel_required")),
            "notes": comp.get("notes") or "",
            "post_meet_report": comp.get("post_meet_report"),
            "linked_goals": [_goal_payload(goal, explicit_target=True) for goal in linked_goals],
            "eligible_goals": competition_goals,
            "governing_goal": governing_goal,
            "primary_strategy_mode": (governing_goal or {}).get("strategy_mode"),
            "required_total_kg": (governing_goal or {}).get("required_total_kg"),
            "weeks_since_previous_comp": round(((comp_date - previous_date).days / 7.0), 1) if comp_date and previous_date else None,
            "weeks_until_next_comp": round(((next_date - comp_date).days / 7.0), 1) if comp_date and next_date else None,
            "actual_total_kg": None,
            "actual_dots": None,
            "target_total_kg": None,
            "target_dots": None,
        }
        if results:
            total = _num(results.get("total_kg"))
            if total > 0:
                row["actual_total_kg"] = round(total, 1)
                row["actual_dots"] = _safe_dots(total, bodyweight, sex)
        if targets:
            total = _num(targets.get("total_kg"))
            if total > 0:
                row["target_total_kg"] = round(total, 1)
                row["target_dots"] = _safe_dots(total, bodyweight, sex)
        rows.append(row)

    primary_comp = next((row for row in rows if row.get("goal_priority") == "primary"), None) or (rows[-1] if rows else None)
    return {
        "primary_competition": primary_comp,
        "competitions": rows,
    }


def summarize_meet_interference(
    program: dict[str, Any],
    reference_date: date | None = None,
    competition_goal_priorities: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    reference_date = reference_date or date.today()
    goal_summary = summarize_goals(program, reference_date=reference_date)
    goal_priorities = competition_goal_priorities or goal_summary.get("competition_goal_priorities") or {}
    goals_by_competition = _group_goals_by_competition(goal_summary.get("goals"))
    upcoming = [
        comp
        for comp in sorted(program.get("competitions", []), key=lambda c: c.get("date", ""))
        if comp.get("status") in ("confirmed", "optional")
        and (comp_date := _parse_date(comp.get("date"))) is not None
        and comp_date >= reference_date
    ]

    rows: list[dict[str, Any]] = []
    for idx, comp in enumerate(upcoming):
        comp_date = _parse_date(comp.get("date"))
        if comp_date is None:
            continue
        later = upcoming[idx + 1:]
        if not later:
            continue
        current_priority = goal_priorities.get(str(comp.get("date") or ""), "optional")
        next_target = next(
            (
                candidate
                for candidate in later
                if _goal_priority_rank(goal_priorities.get(str(candidate.get("date") or ""), "optional")) < _goal_priority_rank(current_priority)
            ),
            later[0],
        )
        next_date = _parse_date(next_target.get("date"))
        if next_date is None:
            continue

        gap_weeks = round(((next_date - comp_date).days / 7.0), 1)
        flags: list[str] = []
        score = 0
        if gap_weeks < 4:
            flags.append("less than 4 weeks between meets")
            score += 2
        elif gap_weeks < 8:
            flags.append("less than 8 weeks between meets")
            score += 1
        if comp.get("hotel_required") or next_target.get("hotel_required"):
            flags.append("travel or hotel load present")
            score += 1
        if _competition_strategy_pressure(goals_by_competition.get(str(comp.get("date") or ""), [])) == "aggressive":
            flags.append("earlier meet still looks like a meaningful attempt")
            score += 1
        if comp.get("weight_class_kg") and next_target.get("weight_class_kg") and comp.get("weight_class_kg") != next_target.get("weight_class_kg"):
            flags.append("weight-class targets differ between meets")
            score += 1

        risk_level = "high" if score >= 3 else "medium" if score >= 1 else "low"
        rows.append(
            {
                "competition": comp.get("name"),
                "competition_date": comp.get("date"),
                "next_priority_competition": next_target.get("name"),
                "next_priority_competition_date": next_target.get("date"),
                "weeks_between_meets": gap_weeks,
                "risk_level": risk_level,
                "risk_flags": flags,
                "summary": (
                    f"{comp.get('name')} sits {gap_weeks:.1f} weeks before {next_target.get('name')} "
                    f"with {', '.join(flags) if flags else 'minimal overlap risk'}."
                ),
            }
        )

    return rows


def summarize_bodyweight_trend(
    sessions: list[dict[str, Any]],
    reference_date: date | None = None,
    window_start: date | None = None,
) -> dict[str, Any]:
    reference_date = reference_date or date.today()
    points = []
    for session in sessions:
        if not (session.get("completed") or session.get("status") in ("logged", "completed")):
            continue
        bw = session.get("body_weight_kg")
        if bw is None:
            continue
        d = _parse_date(session.get("date"))
        if d is None:
            continue
        if window_start and d < window_start:
            continue
        points.append({"date": d.isoformat(), "kg": round(_num(bw), 1)})

    points.sort(key=lambda p: p["date"])
    if len(points) < 2:
        return {"points": points, "latest": None, "change": None, "direction": "unclear"}

    latest = points[-1]["kg"]
    oldest = points[0]["kg"]
    change = round(latest - oldest, 1)
    if change > 0.25:
        direction = "gain"
    elif change < -0.25:
        direction = "loss"
    else:
        direction = "stable"

    return {
        "points": points[-8:],
        "latest": latest,
        "oldest": oldest,
        "change": change,
        "direction": direction,
        "entries": len(points),
    }


def summarize_diet_context(
    program: dict[str, Any],
    reference_date: date | None = None,
    window_start: date | None = None,
    bodyweight_trend: dict[str, Any] | None = None,
) -> dict[str, Any]:
    reference_date = reference_date or date.today()
    diet_notes = program.get("diet_notes", [])
    if window_start:
        diet_notes = [n for n in diet_notes if (d := _parse_date(n.get("date"))) and d >= window_start]

    if not diet_notes:
        return {"status": "unclear", "reason": "No diet notes available"}

    calories = [float(n["avg_daily_calories"]) for n in diet_notes if n.get("avg_daily_calories") is not None]
    protein = [float(n["avg_protein_g"]) for n in diet_notes if n.get("avg_protein_g") is not None]
    carbs = [float(n["avg_carb_g"]) for n in diet_notes if n.get("avg_carb_g") is not None]
    fat = [float(n["avg_fat_g"]) for n in diet_notes if n.get("avg_fat_g") is not None]
    sleep = [float(n["avg_sleep_hours"]) for n in diet_notes if n.get("avg_sleep_hours") is not None]
    consistent = sum(1 for n in diet_notes if n.get("consistent"))

    latest = diet_notes[-1]
    prev = diet_notes[-2] if len(diet_notes) > 1 else None
    latest_calories = latest.get("avg_daily_calories")
    prev_calories = prev.get("avg_daily_calories") if prev else None
    change = None
    if latest_calories is not None and prev_calories is not None:
        change = round(float(latest_calories) - float(prev_calories), 1)

    status = "unclear"
    reasoning = "Insufficient data for an exact calorie status."
    if latest_calories is not None:
        if change is not None and change <= -150:
            status = "deficit"
            reasoning = "Calorie intake trended down relative to the prior note window."
        elif change is not None and change >= 150:
            status = "surplus"
            reasoning = "Calorie intake trended up relative to the prior note window."
        elif bodyweight_trend and bodyweight_trend.get("direction") == "loss":
            status = "deficit"
            reasoning = "Body weight is drifting down, which is consistent with a deficit."
        elif bodyweight_trend and bodyweight_trend.get("direction") == "gain":
            status = "surplus"
            reasoning = "Body weight is drifting up, which is consistent with a surplus."
        else:
            status = "maintenance"
            reasoning = "No strong calorie or bodyweight signal suggests a large surplus/deficit."

    return {
        "status": status,
        "reasoning": reasoning,
        "latest_avg_calories": latest_calories,
        "previous_avg_calories": prev_calories,
        "calories_change": change,
        "avg_calories": round(sum(calories) / len(calories), 0) if calories else None,
        "avg_protein_g": round(sum(protein) / len(protein), 0) if protein else None,
        "avg_carb_g": round(sum(carbs) / len(carbs), 0) if carbs else None,
        "avg_fat_g": round(sum(fat) / len(fat), 0) if fat else None,
        "avg_sleep_hours": round(sum(sleep) / len(sleep), 1) if sleep else None,
        "consistency_pct": round((consistent / len(diet_notes)) * 100, 1) if diet_notes else None,
        "entries": len(diet_notes),
    }


def _serialize_planned_exercise_for_prompt(ex: dict[str, Any]) -> dict[str, Any]:
    kg = ex.get("kg") or 0
    rpe = ex.get("rpe_target") or ex.get("rpe")
    load_source = ex.get("load_source")

    if load_source == "rpe" or (kg == 0 and rpe is not None):
        return {
            "name": ex["name"],
            "sets": ex.get("sets"),
            "reps": ex.get("reps"),
            "load": f"@RPE {rpe}",
            "load_type": "rpe",
            "rpe_target": rpe,
        }
    if load_source == "unresolvable" or (kg == 0 and rpe is None):
        return {
            "name": ex["name"],
            "sets": ex.get("sets"),
            "reps": ex.get("reps"),
            "load": "unspecified",
            "load_type": "unspecified",
        }
    return {
        "name": ex["name"],
        "sets": ex.get("sets"),
        "reps": ex.get("reps"),
        "load": f"{kg}kg",
        "load_type": "absolute",
        "kg": kg,
        "rpe_target": rpe,
    }


def summarize_planned_sessions(
    sessions: list[dict[str, Any]],
    limit: int | None = None,
) -> list[dict[str, Any]]:
    planned = [s for s in sessions if not (s.get("completed") or s.get("status") in ("logged", "completed")) and (s.get("status") in (None, "planned", "skipped") or not s.get("status"))]
    planned.sort(key=lambda s: s.get("date", ""))
    if limit is not None:
        planned = planned[:limit]

    rows: list[dict[str, Any]] = []
    for session in planned:
        exercises = session.get("planned_exercises") or session.get("exercises") or []
        serialized_exercises = [_serialize_planned_exercise_for_prompt(ex) for ex in exercises if ex.get("name")]
        rows.append({
            "date": session.get("date"),
            "day": session.get("day"),
            "week_number": session.get("week_number"),
            "phase": (session.get("phase") or {}).get("name") if isinstance(session.get("phase"), dict) else session.get("phase_name") or session.get("phase"),
            "status": session.get("status") or "planned",
            "exercises": serialized_exercises,
            "session_notes": session.get("session_notes") or "",
            "wellness": _serialize_wellness(session.get("wellness")),
        })
    return rows


def summarize_completed_sessions(
    sessions: list[dict[str, Any]],
    limit: int | None = None,
) -> list[dict[str, Any]]:
    completed = [s for s in sessions if s.get("completed") or s.get("status") in ("logged", "completed")]
    completed.sort(key=lambda s: s.get("date", ""))
    if limit is not None:
        completed = completed[:limit]

    rows: list[dict[str, Any]] = []
    for session in completed:
        exercises = session.get("exercises") or []
        rows.append({
            "date": session.get("date"),
            "day": session.get("day"),
            "week_number": session.get("week_number"),
            "phase": (session.get("phase") or {}).get("name") if isinstance(session.get("phase"), dict) else session.get("phase_name") or session.get("phase"),
            "status": session.get("status") or "completed",
            "session_rpe": session.get("session_rpe"),
            "body_weight_kg": session.get("body_weight_kg"),
            "notes": session.get("session_notes") or "",
            "wellness": _serialize_wellness(session.get("wellness")),
            "exercises": [
                {
                    "name": ex.get("name"),
                    "sets": ex.get("sets"),
                    "reps": ex.get("reps"),
                    "kg": ex.get("kg"),
                    "rpe": ex.get("rpe"),
                    "failed": ex.get("failed", False),
                    "failed_sets": ex.get("failed_sets"),
                    "failed_set_reasons": ex.get("failed_set_reasons"),
                }
                for ex in exercises
                if ex.get("name")
            ],
        })
    return rows


def summarize_supplements(program: dict[str, Any]) -> dict[str, Any]:
    supplements = [
        {
            "name": supp.get("name"),
            "dose": supp.get("dose"),
        }
        for supp in program.get("supplements", [])
        if supp.get("name")
    ]

    phases: list[dict[str, Any]] = []
    for phase in program.get("supplement_phases", []):
        phases.append({
            "phase": phase.get("phase"),
            "phase_name": phase.get("phase_name"),
            "notes": phase.get("notes", ""),
            "block": phase.get("block"),
            "start_week": phase.get("start_week"),
            "end_week": phase.get("end_week"),
            "items": [
                {
                    "name": item.get("name"),
                    "dose": item.get("dose"),
                    "notes": item.get("notes", ""),
                }
                for item in (phase.get("items") or [])
                if item.get("name")
            ],
            "peak_week_protocol": phase.get("peak_week_protocol") or {},
        })

    return {
        "supplements": supplements,
        "supplement_phases": phases,
    }


def summarize_exercise_roi(
    program: dict[str, Any],
    sessions: list[dict[str, Any]] | None = None,
    top_n: int = 10,
) -> list[dict[str, Any]]:
    """Return top-N accessory exercises ranked by |pearson_r| between weekly
    volume and average intensity (via `volume_intensity_correlation`).

    Each row contains the exercise name, pearson_r, and a short numeric
    fingerprint of the volume/intensity series so the LLM can sanity-check
    the signal. Accessories only — the three big competition lifts are
    excluded because they're analyzed separately.
    """
    from analytics import volume_intensity_correlation

    sessions = sessions if sessions is not None else program.get("sessions", [])
    program_start = program.get("meta", {}).get("program_start", "") or ""
    big_lifts = frozenset(["squat", "bench", "bench press", "deadlift"])

    exercise_names: set[str] = set()
    for s in sessions:
        if not (s.get("completed") or s.get("status") in ("logged", "completed")):
            continue
        for ex in s.get("exercises", []):
            name = (ex.get("name") or "").strip()
            if not name:
                continue
            if name.lower() in big_lifts:
                continue
            exercise_names.add(name)

    rows: list[dict[str, Any]] = []
    for name in exercise_names:
        result = volume_intensity_correlation(sessions, name, program_start)
        r = result.get("pearson_r")
        if r is None:
            continue
        rows.append({
            "exercise": name,
            "pearson_r": r,
            "weeks_observed": len(result.get("volume_series") or []),
            "volume_series": result.get("volume_series") or [],
            "intensity_series": result.get("intensity_series") or [],
        })

    rows.sort(key=lambda row: abs(float(row["pearson_r"] or 0.0)), reverse=True)
    return rows[:top_n]


FORMULA_REFERENCE = """\
HOW THE ANALYSIS PAGE METRICS ARE CALCULATED

- Estimated 1RM: conservative RPE-table estimate for qualifying sets, or 90th percentile of
  qualifying session e1RMs when no comp result is available. Current maxes are therefore
  estimated 1 rep maxes, not true tested maxes.
- Progression rate: Theil-Sen slope of e1RM over effective training weeks, with deload and break
  weeks excluded. Fit quality is normalized MAD; Kendall tau is reported alongside the slope.
- RPE drift: Theil-Sen slope on raw or phase-residual RPE. Uses the same fit-quality reporting.
- Fatigue model: axial and peripheral scale nonlinearly with load, neural uses an intensity gate
  plus sqrt(load), systemic adds a modest absolute-load and intensity term.
- Fatigue index: Window-aware composite score derived from failure_stress, acute_spike_stress, rpe_stress, chronic_load_stress, overload_streak, intensity_density_stress, and monotony_stress.
  Values >= 0.65 indicate Very High risk. >= 0.45 indicate High risk.
- INOL: reps / (100 × sqrt((1 - min(intensity ratio, 0.995))^2 + 0.02^2)) aggregated per lift per week,
  then multiplied by the lift profile stimulus coefficient. Defaults are per-lift, with optional overrides.
- ACWR: daily EWMA acute workload divided by daily EWMA chronic workload, with a weighted composite
  and phase-aware planned-overreach labeling.
- Relative intensity distribution: sets bucketed by load ratio vs estimated 1RM.
- Specificity ratio: SBD sets divided by total sets, plus a broader version that includes same-category work.
- Readiness score: weighted composite of fatigue, RPE drift, subjective wellness, short-term performance trend, and bodyweight deviation.
- DOTS: 500 × total / polynomial(bodyweight) using the sex-specific coefficients.
- Attempt selection: projected comp max × attempt percentages, rounded to the nearest 2.5 kg.
"""
