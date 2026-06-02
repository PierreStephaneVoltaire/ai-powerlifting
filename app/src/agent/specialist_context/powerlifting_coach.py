




from __future__ import annotations

import json
import logging
import os
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

_SEP = "══════════════════════════════════════════════════"

def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None

def _num(v: Any) -> float:
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(v)
    except (ValueError, TypeError):
        return 0.0

def _j(obj: Any) -> str:
    return json.dumps(obj, indent=2, default=str)

def _section_current_state(
    program: dict,
    sessions: list[dict],
    _calculate_current_week,
    _find_current_phase,
    summarize_planned_sessions,
) -> str | None:
    try:
        today = date.today()
        meta = program.get("meta", {})
        phases = program.get("phases", [])
        program_start = meta.get("program_start", "")

        sorted_sessions = sorted(sessions, key=lambda s: s.get("date", ""))
        current_week = None
        current_phase_name = None
        for s in sorted_sessions:
            status = (s.get("status") or "").lower()
            if status not in ("completed", "skipped", "missed"):
                wn = s.get("week_number")
                if wn is not None:
                    try:
                        current_week = int(wn)
                    except (ValueError, TypeError):
                        pass
                    if current_week is not None:
                        phase_field = s.get("phase") or {}
                        if isinstance(phase_field, dict):
                            current_phase_name = phase_field.get("name")
                        else:
                            current_phase_name = s.get("phase_name") or s.get("phase")
                break
        if current_week is None:
            current_week = _calculate_current_week(program_start)

        if not current_phase_name:
            cp = _find_current_phase(phases, current_week)
            current_phase_name = cp.get("name", "Unknown") if cp else "Unknown"

        phase_start = phase_end = None
        cp = _find_current_phase(phases, current_week)
        if cp:
            phase_start = cp.get("start_week")
            phase_end = cp.get("end_week")

        days_to_comp_str = ""
        comp_date_str = meta.get("comp_date", "")
        comp_date = _parse_date(comp_date_str)
        if comp_date and comp_date > today:
            days_left = (comp_date - today).days
            comps = sorted(program.get("competitions", []), key=lambda c: c.get("date", ""))
            comp_name = next(
                (c.get("name", comp_date_str) for c in comps
                 if c.get("date", "") == comp_date_str),
                comp_date_str,
            )
            days_to_comp_str = f"\nDays to competition: {days_left} ({comp_name} on {comp_date_str})"

        phase_range = f"Wk {phase_start}–{phase_end}" if phase_start is not None else ""
        week_line = f"Current week: {current_week} — {current_phase_name}"
        if phase_range:
            week_line += f" ({phase_range})"

        lines = [
            _SEP,
            "CURRENT STATE",
            _SEP,
            "",
            f"Today: {today.isoformat()} ({today.strftime('%A')})",
            week_line,
        ]
        if days_to_comp_str:
            lines.append(days_to_comp_str.strip())

        completed_sessions = sorted(
            [s for s in sessions if s.get("status") in ("completed",) or s.get("completed") is True],
            key=lambda s: s.get("date", ""),
            reverse=True,
        )
        if completed_sessions:
            last = completed_sessions[0]
            lines.append("")
            lines.append(f"LAST COMPLETED SESSION ({last.get('date', 'unknown')}):")
            phase_field = last.get("phase") or {}
            phase_label = phase_field.get("name") if isinstance(phase_field, dict) else (last.get("phase_name") or last.get("phase") or "")
            rpe_val = last.get("session_rpe", "—")
            bw_val = last.get("body_weight_kg", "—")
            lines.append(f"  Phase: {phase_label}  |  Session RPE: {rpe_val}  |  BW: {bw_val}kg")
            exercises = (last.get("exercises") or [])[:5]
            if exercises:
                lines.append("  Exercises:")
                for ex in exercises:
                    name = ex.get("name", "")
                    sets = ex.get("sets", "?")
                    reps = ex.get("reps", "?")
                    kg = ex.get("kg", "?")
                    ex_rpe = ex.get("rpe", "")
                    rpe_part = f" (RPE {ex_rpe})" if ex_rpe else ""
                    lines.append(f"    - {name}: {sets}×{reps} @ {kg}kg{rpe_part}")

        upcoming = summarize_planned_sessions(sessions, limit=3)
        if upcoming:
            lines.append("")
            lines.append("UPCOMING SESSIONS (next 3):")
            for s in upcoming:
                lines.append(f"  {s.get('date', '?')} — {s.get('day', '?')} — {s.get('phase', '?')}")
                for ex in (s.get("exercises") or []):
                    name = ex.get("name", "")
                    sets = ex.get("sets", "?")
                    reps = ex.get("reps", "?")
                    load = ex.get("load", "?")
                    lines.append(f"    - {name}: {sets}×{reps} @ {load}")

        return "\n".join(lines)
    except Exception as e:
        logger.debug(f"[SpecialistContext] current_state section failed: {e}")
        return None

def _section_athlete_profile(
    program: dict,
    summarize_program_meta,
    summarize_measurements,
    summarize_lift_profiles,
    summarize_phases,
) -> str | None:
    try:
        meta = program.get("meta", {})
        prog_meta = summarize_program_meta(meta)
        measurements = summarize_measurements(meta)
        lift_profiles = summarize_lift_profiles(program.get("lift_profiles"))
        phases = summarize_phases(program.get("phases"))
        current_maxes = program.get("current_maxes", {})

        lines = [
            _SEP,
            "ATHLETE PROFILE",
            _SEP,
            "",
            f"Program: {prog_meta.get('program_name', '?')} (started {prog_meta.get('program_start', '?')})",
        ]

        bw_kg = measurements.get("current_body_weight_kg") or prog_meta.get("current_body_weight_kg")
        bw_lb = prog_meta.get("current_body_weight_lb")
        wc = measurements.get("weight_class_kg") or prog_meta.get("weight_class_kg")
        h = measurements.get("height_cm")
        ws = measurements.get("arm_wingspan_cm")
        ll = measurements.get("leg_length_cm")

        bw_part = f"{bw_kg}kg" + (f" / {bw_lb}lb" if bw_lb else "")
        wc_part = f"  |  Weight class: {wc}kg" if wc else ""
        lines.append(f"Bodyweight: {bw_part}{wc_part}")

        body_parts = []
        if h:
            body_parts.append(f"Height: {h}cm")
        if ws:
            body_parts.append(f"Wingspan: {ws}cm")
        if ll:
            body_parts.append(f"Leg length: {ll}cm")
        if body_parts:
            lines.append("  |  ".join(body_parts))

        goals_parts = []
        for key, label in [("target_squat_kg", "Squat"), ("target_bench_kg", "Bench"),
                           ("target_dl_kg", "DL"), ("target_total_kg", "Total")]:
            val = prog_meta.get(key)
            if val:
                goals_parts.append(f"{label} {val}kg")
        if goals_parts:
            lines.append(f"Goals: {' | '.join(goals_parts)}")

        if current_maxes:
            lines.append("")
            lines.append("CURRENT MAXES (estimated 1RM):")
            sq = current_maxes.get("squat")
            bp = current_maxes.get("bench")
            dl = current_maxes.get("deadlift")
            parts = []
            if sq is not None:
                parts.append(f"Squat: {sq}kg")
            if bp is not None:
                parts.append(f"Bench: {bp}kg")
            if dl is not None:
                parts.append(f"Deadlift: {dl}kg")
            if parts:
                lines.append("  " + "  |  ".join(parts))

        if phases:
            lines.append("")
            lines.append("PHASES:")
            for p in phases:
                lines.append(f"  Wk{p.get('start_week')}–{p.get('end_week')}: {p.get('name')} — {p.get('intent', '')}")

        if lift_profiles:
            lines.append("")
            lines.append("LIFT PROFILES:")
            for lp in lift_profiles:
                lift = lp.get("lift", "").capitalize()
                style = lp.get("style_notes", "")
                stick = lp.get("sticking_points", "")
                primary = lp.get("primary_muscle", "")
                vol_tol = lp.get("volume_tolerance", "")
                parts = []
                if style:
                    parts.append(f"Style: {style}")
                if stick:
                    parts.append(f"Sticking: {stick}")
                if primary:
                    parts.append(f"Primary: {primary}")
                if vol_tol:
                    parts.append(f"Vol tolerance: {vol_tol}")
                lines.append(f"  {lift}: {' | '.join(parts)}")

        return "\n".join(lines)
    except Exception as e:
        logger.debug(f"[SpecialistContext] athlete_profile section failed: {e}")
        return None

def _section_competitions(program: dict, summarize_competitions) -> str | None:
    try:
        result = summarize_competitions(program)
        comps = result.get("competitions", [])
        if not comps:
            return None

        lines = [_SEP, "COMPETITIONS & GOALS", _SEP, ""]
        for c in comps:
            name = c.get("name", "?")
            comp_date = c.get("date", "?")
            weeks = c.get("weeks_to_comp")
            status = c.get("status", "?")
            wc = c.get("weight_class_kg")
            target = c.get("target_total_kg")
            actual = c.get("actual_total_kg")

            weeks_str = f" ({weeks}wk away)" if weeks is not None and weeks > 0 else " (past)"
            header = f"{name} — {comp_date}{weeks_str} — {status}"
            lines.append(header)
            detail_parts = []
            if wc:
                detail_parts.append(f"Weight class: {wc}kg")
            if target:
                detail_parts.append(f"Target total: {target}kg")
            if actual:
                detail_parts.append(f"Actual total: {actual}kg")
            if detail_parts:
                lines.append("  " + "  |  ".join(detail_parts))

        return "\n".join(lines)
    except Exception as e:
        logger.debug(f"[SpecialistContext] competitions section failed: {e}")
        return None

def _section_trends(
    program: dict,
    sessions: list[dict],
    progression_rate,
    summarize_bodyweight_trend,
    summarize_diet_context,
) -> str | None:
    try:
        meta = program.get("meta", {})
        program_start = meta.get("program_start", "")

        lines = [_SEP, "TRENDS (last 8 weeks)", _SEP, ""]

        e1rm_lines = []
        for lift_name in ("squat", "bench", "deadlift"):
            result = progression_rate(sessions, lift_name, program_start)
            slope = result.get("slope_kg_per_week")
            fit_quality = result.get("fit_quality", result.get("r_squared", result.get("r2")))
            tau = result.get("kendall_tau")
            if slope is not None:
                parts = [f"{lift_name.capitalize()}: {slope}kg/wk"]
                if fit_quality is not None:
                    parts.append(f"fit={fit_quality}")
                if tau is not None:
                    parts.append(f"tau={tau}")
                e1rm_lines.append("  " + "  |  ".join(parts))
        if e1rm_lines:
            lines.append("E1RM PROGRESSION (Theil-Sen slope):")
            lines.extend(e1rm_lines)
            lines.append("")

        bw_trend = summarize_bodyweight_trend(sessions)
        entries = bw_trend.get("entries", 0)
        if entries:
            latest = bw_trend.get("latest")
            change = bw_trend.get("change")
            direction = bw_trend.get("direction", "unclear")
            points = bw_trend.get("points", [])
            lines.append(f"BODYWEIGHT TREND ({entries} sessions):")
            lines.append(f"  Latest: {latest}kg  |  Change: {change}kg ({direction})")
            if points:
                history_str = ", ".join(f"{p['date']}: {p['kg']}kg" for p in points[-8:])
                lines.append(f"  History: {history_str}")
            lines.append("")

        diet = summarize_diet_context(program, bodyweight_trend=bw_trend)
        status = diet.get("status", "unclear")
        reasoning = diet.get("reasoning", "")
        if status != "unclear" or diet.get("avg_calories"):
            lines.append("DIET/SLEEP TREND:")
            lines.append(f"  Status: {status} ({reasoning})")
            kcal = diet.get("avg_calories")
            protein = diet.get("avg_protein_g")
            sleep = diet.get("avg_sleep_hours")
            consistency = diet.get("consistency_pct")
            parts = []
            if kcal is not None:
                parts.append(f"Avg calories: {kcal}")
            if protein is not None:
                parts.append(f"Protein: {protein}g")
            if sleep is not None:
                parts.append(f"Sleep: {sleep}h")
            if parts:
                lines.append("  " + "  |  ".join(parts))
            if consistency is not None:
                lines.append(f"  Consistency: {consistency}%")

        if len(lines) <= 3:
            return None
        return "\n".join(lines)
    except Exception as e:
        logger.debug(f"[SpecialistContext] trends section failed: {e}")
        return None

def _section_fatigue_readiness(
    pk: str,
    program: dict,
    sessions: list[dict],
    fatigue_index,
    compute_inol,
    compute_acwr,
    compute_readiness_score,
    _calculate_current_week,
) -> str | None:
    try:
        meta = program.get("meta", {})
        program_start = meta.get("program_start", "")
        current_maxes = program.get("current_maxes", {})
        phases = program.get("phases", [])
        current_week = _calculate_current_week(program_start, sessions)

        cached = None
        fatigue_data = inol_data = acwr_data = readiness_data = None

        try:
            import boto3
            today = date.today()
            week_start = today - timedelta(days=today.weekday())
            cache_sk = f"weekly_analysis#{week_start.isoformat()}"
            table = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "ca-central-1")).Table(
                os.environ.get("IF_HEALTH_TABLE_NAME", "if-health")
            )
            item = table.get_item(Key={"pk": pk, "sk": cache_sk}).get("Item")
            if item and item.get("generated_at"):
                generated_at = item["generated_at"]
                try:
                    gen_dt = datetime.fromisoformat(str(generated_at))
                    if (datetime.now(gen_dt.tzinfo) - gen_dt).total_seconds() < 86400:
                        cached = item
                except Exception:
                    pass
        except Exception as cache_err:
            logger.debug(f"[SpecialistContext] DynamoDB cache read failed: {cache_err}")

        if cached:
            fatigue_data = cached.get("fatigue")
            inol_data = cached.get("inol")
            acwr_data = cached.get("acwr")
            readiness_data = cached.get("readiness_score")

        completed = [s for s in sessions if s.get("status") in ("completed",) or s.get("completed") is True]

        if fatigue_data is None:
            try:
                fatigue_data = fatigue_index(sessions, days=14)
            except Exception:
                pass

        if inol_data is None:
            try:
                inol_data = compute_inol(sessions, program_start, current_maxes or None)
            except Exception:
                pass

        if acwr_data is None:
            try:
                acwr_data = compute_acwr(
                    sessions,
                    None,
                    program_start,
                    current_maxes or None,
                    phases=phases,
                    current_week=current_week,
                )
            except Exception:
                pass

        if readiness_data is None:
            try:
                readiness_data = compute_readiness_score(sessions, program)
            except Exception:
                pass

        if all(x is None for x in (fatigue_data, inol_data, acwr_data, readiness_data)):
            return None

        cache_note = "(cached)" if cached else "(fresh)"
        lines = [_SEP, f"FATIGUE & READINESS {cache_note}", _SEP, ""]

        if fatigue_data and "score" in fatigue_data:
            score = fatigue_data.get("score", "?")
            flags = fatigue_data.get("flags", [])
            comps = fatigue_data.get("components", {})
            flags_str = f" [{', '.join(flags)}]" if flags else ""
            lines.append(f"Fatigue index: {score}{flags_str}")
            if comps:
                failed = comps.get("failed_compound_ratio", "?")
                spike = comps.get("composite_spike", "?")
                rpe_stress = comps.get("rpe_stress", "?")
                lines.append(f"  Failed compound ratio: {failed}  |  Volume spike: {spike}  |  RPE stress: {rpe_stress}")
            lines.append("")

        if inol_data and "avg_inol" in inol_data:
            avg = inol_data["avg_inol"]
            inol_flags = inol_data.get("flags", [])
            parts = []
            for lift in ("squat", "bench", "deadlift"):
                val = avg.get(lift)
                if val is not None:
                    parts.append(f"{lift.capitalize()}: {val}")
            lines.append("INOL (avg per lift per week):")
            if parts:
                lines.append("  " + "  |  ".join(parts))
            if inol_flags:
                lines.append(f"  Flags: {', '.join(inol_flags)}")
            lines.append("")

        if acwr_data and "composite" in acwr_data:
            composite = acwr_data.get("composite")
            composite_zone = acwr_data.get("composite_zone", "unknown")
            composite_label = acwr_data.get("composite_label", composite_zone)
            dims = acwr_data.get("dimensions", {})
            lines.append("ACWR (EWMA load ratio):")
            lines.append(f"  Composite: {composite} ({composite_label})")
            dim_parts = []
            for dim in ("axial", "neural", "peripheral", "systemic"):
                d = dims.get(dim, {})
                val = d.get("value") if isinstance(d, dict) else d
                label = d.get("label", d.get("zone", "?")) if isinstance(d, dict) else "?"
                if val is not None:
                    dim_parts.append(f"{dim.capitalize()}: {val} ({label})")
            if dim_parts:
                lines.append("  " + "  |  ".join(dim_parts))
            lines.append("")
        elif acwr_data and acwr_data.get("status") == "insufficient_data":
            lines.append("ACWR (EWMA load ratio):")
            lines.append(f"  Insufficient data: {acwr_data.get('reason', 'not enough training history')}")
            lines.append("")

        if readiness_data and "score" in readiness_data:
            r_score = readiness_data.get("score", "?")
            lines.append(f"Readiness score: {r_score}/100")

        return "\n".join(lines)
    except Exception as e:
        logger.debug(f"[SpecialistContext] fatigue_readiness section failed: {e}")
        return None

def _section_per_lift_breakdown(program: dict, sessions: list[dict], glossary: list[dict]) -> str | None:
    try:
        from datetime import date, timedelta as _td

        today = date.today()
        window_start = today - _td(weeks=8)
        num_weeks = 8

        completed = [
            s for s in sessions
            if (s.get("status") in ("completed",) or s.get("completed") is True)
            and _parse_date(s.get("date", "")) is not None
            and _parse_date(s.get("date", "")) >= window_start
        ]

        if not completed:
            return None

        def normalize(name: str) -> str:
            return name.strip().lower()

        category_lookup: dict[str, str] = {normalize(ex["name"]): ex.get("category", "") for ex in glossary}
        muscles_lookup: dict[str, dict] = {
            normalize(ex["name"]): {
                "primary": ex.get("primary_muscles", []),
                "secondary": ex.get("secondary_muscles", []),
            }
            for ex in glossary
        }

        main_lift_names = {
            "squat": {"squat"},
            "bench": {"bench", "bench press"},
            "deadlift": {"deadlift"},
        }

        lift_stats: dict[str, dict] = {
            "squat": {"sessions": 0, "raw_sets": 0, "accessories": defaultdict(lambda: {"sets": 0, "volume": 0.0})},
            "bench": {"sessions": 0, "raw_sets": 0, "accessories": defaultdict(lambda: {"sets": 0, "volume": 0.0})},
            "deadlift": {"sessions": 0, "raw_sets": 0, "accessories": defaultdict(lambda: {"sets": 0, "volume": 0.0})},
        }

        for s in completed:
            exercises = s.get("exercises", [])
            ex_names_lower = {normalize(ex.get("name", "")) for ex in exercises if ex.get("name")}

            for lift_key, lift_set in main_lift_names.items():
                category_str = lift_key

                has_lift = any(n in lift_set for n in ex_names_lower)
                has_category = has_lift or any(
                    category_lookup.get(n, "") == category_str for n in ex_names_lower
                )

                if has_category:
                    lift_stats[lift_key]["sessions"] += 1

                for ex in exercises:
                    if not ex.get("name"):
                        continue
                    n = normalize(ex.get("name", ""))
                    sets = int(_num(ex.get("sets", 0)))
                    kg = _num(ex.get("kg", 0))
                    if sets <= 0:
                        continue

                    if n in lift_set:
                        lift_stats[lift_key]["raw_sets"] += sets
                    elif category_lookup.get(n, "") == category_str:
                        acc = lift_stats[lift_key]["accessories"][ex.get("name", n)]
                        acc["sets"] += sets
                        acc["volume"] += sets * _num(ex.get("reps", 0)) * kg

        muscle_sets: dict[str, float] = defaultdict(float)
        for s in completed:
            for ex in s.get("exercises", []):
                if not ex.get("name"):
                    continue
                n = normalize(ex.get("name", ""))
                sets = int(_num(ex.get("sets", 0)))
                if sets <= 0:
                    continue
                ml = muscles_lookup.get(n, {})
                for pm in ml.get("primary", []):
                    muscle_sets[pm] += sets
                for sm in ml.get("secondary", []):
                    muscle_sets[sm] += sets * 0.5

        lines = [_SEP, "PER-LIFT BREAKDOWN (last 8 weeks)", _SEP, ""]

        for lift_key in ("squat", "bench", "deadlift"):
            stats = lift_stats[lift_key]
            freq = round(stats["sessions"] / num_weeks, 1)
            raw_sets = stats["raw_sets"]
            lines.append(f"{lift_key.upper()} — {freq}/wk avg | {raw_sets} total sets")
            acc_sorted = sorted(stats["accessories"].items(), key=lambda x: x[1]["sets"], reverse=True)
            if acc_sorted:
                acc_str = ", ".join(f"{name} ({v['sets']} sets)" for name, v in acc_sorted[:5])
                lines.append(f"  Accessories: {acc_str}")
            lines.append("")

        if muscle_sets:
            lines.append("MUSCLE GROUP SETS (primary + 0.5× secondary):")
            sorted_muscles = sorted(muscle_sets.items(), key=lambda x: x[1], reverse=True)
            for muscle, total in sorted_muscles[:10]:
                avg_wk = round(total / num_weeks, 1)
                lines.append(f"  {muscle}: {round(total, 1)} sets ({avg_wk}/wk avg)")

        return "\n".join(lines)
    except Exception as e:
        logger.debug(f"[SpecialistContext] per_lift_breakdown section failed: {e}")
        return None

def _section_cached_deep_analyses(pk: str) -> str | None:
    try:
        import boto3

        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        table_name = os.environ.get("IF_HEALTH_TABLE_NAME", "if-health")
        region = os.environ.get("AWS_REGION", "ca-central-1")
        table = boto3.resource("dynamodb", region_name=region).Table(table_name)

        lines = [_SEP, "CACHED DEEP ANALYSES", _SEP, ""]
        has_content = False

        try:
            eval_sk = f"program_eval#{week_start.isoformat()}"
            eval_item = table.get_item(Key={"pk": pk, "sk": eval_sk}).get("Item")
            if eval_item and eval_item.get("report"):
                has_content = True
                gen_at = eval_item.get("generated_at", "?")
                report = eval_item["report"]
                report_text = _j(report) if isinstance(report, dict) else str(report)
                lines.append(f"PROGRAM EVALUATION (generated {gen_at}, week starting {week_start.isoformat()}):")
                lines.append(report_text)
                lines.append("")
        except Exception as e:
            logger.debug(f"[SpecialistContext] program_eval read failed: {e}")

        try:
            weeks = 4
            raw_cutoff = today - timedelta(weeks=weeks)
            window_start = (raw_cutoff - timedelta(days=raw_cutoff.weekday())).isoformat()
            corr_sk = f"corr_report#{window_start}_{weeks}w"
            corr_item = table.get_item(Key={"pk": pk, "sk": corr_sk}).get("Item")
            if corr_item and corr_item.get("report"):
                has_content = True
                gen_at = corr_item.get("generated_at", "?")
                report = corr_item["report"]
                findings = report.get("findings") if isinstance(report, dict) else None
                findings_text = _j(findings) if findings else (_j(report) if isinstance(report, dict) else str(report))
                lines.append(f"EXERCISE ROI CORRELATION ({window_start}, {weeks}w window, generated {gen_at}):")
                lines.append(findings_text)
                lines.append("")
        except Exception as e:
            logger.debug(f"[SpecialistContext] corr_report read failed: {e}")

        if not has_content:
            return None
        return "\n".join(lines)
    except Exception as e:
        logger.debug(f"[SpecialistContext] cached_deep_analyses section failed: {e}")
        return None

async def build_context(pk: str, task: str) -> str | None:





    try:
        from core import _get_store, _get_glossary_store
        from analytics import (
            fatigue_index,
            compute_acwr,
            compute_inol,
            compute_readiness_score,
            progression_rate,
            _calculate_current_week,
            _find_current_phase,
        )
        from prompt_context import (
            summarize_program_meta,
            summarize_lift_profiles,
            summarize_phases,
            summarize_measurements,
            summarize_competitions,
            summarize_bodyweight_trend,
            summarize_diet_context,
            summarize_planned_sessions,
            summarize_completed_sessions,
            summarize_supplements,
            FORMULA_REFERENCE,
        )
    except ImportError as e:
        logger.warning(f"[SpecialistContext] Health imports unavailable: {e}")
        return None

    try:
        store = _get_store()
        program = await store.get_program()
    except Exception as e:
        logger.warning(f"[SpecialistContext] Failed to load program: {e}")
        return None

    if not program:
        return None

    sessions: list[dict] = program.get("sessions", [])

    sections: list[str] = []

    s1 = _section_current_state(program, sessions, _calculate_current_week, _find_current_phase, summarize_planned_sessions)
    if s1:
        sections.append(s1)

    s2 = _section_athlete_profile(program, summarize_program_meta, summarize_measurements, summarize_lift_profiles, summarize_phases)
    if s2:
        sections.append(s2)

    s3 = _section_competitions(program, summarize_competitions)
    if s3:
        sections.append(s3)

    s4 = _section_trends(program, sessions, progression_rate, summarize_bodyweight_trend, summarize_diet_context)
    if s4:
        sections.append(s4)

    s5 = _section_fatigue_readiness(pk, program, sessions, fatigue_index, compute_inol, compute_acwr, compute_readiness_score, _calculate_current_week)
    if s5:
        sections.append(s5)

    s6: str | None = None
    try:
        glossary_store = _get_glossary_store()
        glossary = await glossary_store.get_glossary()
        s6 = _section_per_lift_breakdown(program, sessions, glossary)
    except Exception as e:
        logger.debug(f"[SpecialistContext] Glossary unavailable for per_lift_breakdown: {e}")
    if s6:
        sections.append(s6)

    s7 = _section_cached_deep_analyses(pk)
    if s7:
        sections.append(s7)

    if sections:
        sections.append(FORMULA_REFERENCE)

    if not sections:
        return None

    result = "\n\n".join(sections)

    BUDGET = 12000
    if len(result) > BUDGET and s7:
        truncated_s7 = s7[:3000] + "...[truncated]"
        sections_trimmed = [
            (truncated_s7 if s is s7 else s)
            for s in sections
        ]
        result = "\n\n".join(sections_trimmed)

    if len(result) > BUDGET and s4:
        import re
        def trim_history(match: re.Match) -> str:
            full = match.group(0)
            lines_in = full.split("\n")
            out = []
            for line in lines_in:
                if line.strip().startswith("History:"):
                    parts = line.split(",")
                    out.append(parts[0] + (" ..." if len(parts) > 1 else ""))
                else:
                    out.append(line)
            return "\n".join(out)

        s4_trimmed = re.sub(r"History:.*", lambda m: m.group(0).split(",")[0] + " ...", s4)
        sections_trimmed = [
            (s4_trimmed if s is s4 else s)
            for s in sections
        ]
        result = "\n\n".join(sections_trimmed)

    logger.debug(f"[SpecialistContext] powerlifting_coach built {len(result)} chars")
    return result
