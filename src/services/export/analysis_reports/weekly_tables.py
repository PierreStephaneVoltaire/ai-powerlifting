from datetime import date, timedelta
from statistics import mean
from typing import Any


AnalysisTable = tuple[str, list[str], list[list[Any]]]


def record(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def points(value: Any) -> list[dict]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def fields(row: dict, *keys: str) -> list[Any]:
    values = []
    for key in keys:
        value = row
        for part in key.removesuffix("%").split("."):
            value = record(value).get(part)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            value = round(value * 100, 1) if key.endswith("%") else round(value, 2)
        values.append(value)
    return values


def measures(row: dict, columns: dict[str, str]) -> list[list[Any]]:
    return [[label, value] for label, value in zip(columns, fields(row, *columns.values())) if value is not None]


def analysis_tables(weekly: dict, diet_notes: list[dict], meta: dict) -> list[AnalysisTable]:
    tables = [*weekly_tables(weekly), *nutrition_tables(diet_notes, meta)]
    measurements = measures(meta, {"Height (cm)": "height_cm", "Arm wingspan (cm)": "arm_wingspan_cm", "Leg length (cm)": "leg_length_cm"})
    if measurements:
        tables.append(("Athlete Measurements", ["Measurement", "Value"], measurements))
    return tables


def weekly_tables(weekly: dict) -> list[AnalysisTable]:
    tables: list[AnalysisTable] = []

    def add(title: str, headers: list[str], rows: list[list[Any]]) -> None:
        if rows:
            tables.append((title, headers, rows))

    def summary(title: str, value: Any, columns: dict[str, str]) -> None:
        add(title, ["Metric", "Value"], measures(record(value), columns))

    summary("Compliance", weekly.get("compliance"), {
        "Phase": "phase", "Planned sessions": "planned", "Completed sessions": "completed", "Missed sessions": "missed",
        "Session completion (%)": "pct", "Planned sets": "planned_sets", "Completed sets": "completed_sets",
        "Set completion (%)": "set_pct", "Planned reps": "planned_reps", "Completed reps": "completed_reps",
        "Rep completion (%)": "rep_pct", "Planned volume (kg)": "planned_volume", "Completed volume (kg)": "completed_volume",
        "Volume completion (%)": "vol_pct",
    })
    summary("Fatigue Index", {**record(weekly.get("fatigue_components")), "index": weekly.get("fatigue_index")}, {
        "Fatigue index (%)": "index%", "Window mean (%)": "window_mean_fi%", "Window peak (%)": "window_peak_fi%",
        "Failure stress (%)": "failure_stress%", "Acute spike stress (%)": "acute_spike_stress%", "RPE stress (%)": "rpe_stress%",
        "Reservoir stress (%)": "chronic_load_stress%", "Overload streak (%)": "overload_streak%",
        "Intensity density stress (%)": "intensity_density_stress%", "Monotony stress (%)": "monotony_stress%",
        "Context weeks": "fatigue_context_weeks_used", "Context confidence": "fatigue_context_confidence",
    })
    summary("Readiness", weekly.get("readiness_score"), {
        "Overall score": "score", "Zone": "zone", "Training score": "training_score", "External score": "external_score",
        "Fatigue (%)": "components.fatigue_norm%", "RPE drift (%)": "components.rpe_drift%", "Wellness (%)": "components.wellness%",
        "Performance trend (%)": "components.performance_trend%", "Bodyweight deviation (%)": "components.bw_deviation%",
        "Overall confidence (%)": "readiness_confidence%", "Training confidence (%)": "training_readiness_confidence%",
        "External confidence (%)": "external_readiness_confidence%",
    })
    lifts = record(weekly.get("lifts"))
    breakdowns = record(weekly.get("per_lift"))
    add("Per-Lift Breakdown", ["Lift", "Sets", "Raw sets", "Volume (kg)", "Raw volume (kg)", "Frequency", "Exposure frequency",
                                 "Progression (kg/week)", "Kendall tau", "Fit quality (%)", "Volume change (%)",
                                 "Intensity change (%)", "Failed sets", "RPE trend"], [
        [lift.title(), *fields(record(breakdowns.get(lift)), "sets", "raw_sets", "volume", "raw_volume", "frequency", "exposure_frequency"),
         *fields(record(lifts.get(lift)), "progression_rate_kg_per_week", "kendall_tau", "fit_quality%", "volume_change_pct",
                 "intensity_change_pct", "failed_sets", "rpe_trend")]
        for lift in dict.fromkeys([*lifts, *breakdowns])
    ])
    add("Accessory Workload", ["Lift", "Exercise", "Transfer", "Sets", "Weighted sets", "Volume (kg)"], [
        [lift.title(), *fields(accessory, "name", "transfer", "sets", "weighted_sets", "volume")]
        for lift, breakdown in breakdowns.items() for accessory in points(record(breakdown).get("accessories"))
    ])
    add("Exercise Volume", ["Exercise", "Total sets", "Volume (kg)", "Max (kg)"], [
        [name, *fields(record(stats), "total_sets", "total_volume", "max_kg")]
        for name, stats in record(weekly.get("exercise_stats")).items()
    ])
    muscle = record(weekly.get("muscle_volume"))
    add("Muscle Volume", ["Muscle", "Sets/week", "Total sets", "Status", "MV", "MEV", "MAV low", "MAV high", "MRV"], [
        [name.replace("_", " ").title(), *fields(record(entry), "weekly_sets", "total_sets", "status", "landmarks.mv",
                                               "landmarks.mev", "landmarks.mav_low", "landmarks.mav_high", "landmarks.mrv")]
        for name, entry in record(muscle.get("muscles")).items()
    ])
    add("Foster Monotony and Strain", ["Week", "Monotony", "Raw monotony", "Strain", "Strain index", "Nonzero training days"], [
        fields(row, "week_start", "monotony", "monotony_raw", "strain", "strain_index", "nonzero_training_days")
        for row in points(record(weekly.get("monotony_strain")).get("weekly"))
    ])
    acwr = record(weekly.get("acwr"))
    summary("EWMA ACWR Summary", acwr, {"Composite": "composite", "Zone": "composite_label", "Status": "reason"})
    add("EWMA ACWR", ["Dimension", "Ratio", "Acute", "Chronic", "Zone", "Weight (%)"], [
        [name.title(), *fields(record(value), "value", "acute", "chronic", "label"), *fields(record(acwr.get("weights_used")), f"{name}%")]
        for name, value in record(acwr.get("dimensions")).items()
    ])
    fatigue = record(weekly.get("fatigue_dimensions"))
    dimensions = ["axial", "neural", "peripheral", "systemic"]
    add("Fatigue Dimensions", ["Week", "Series", *[name.title() for name in dimensions]], [
        [week, label, *fields(record(values), *dimensions)]
        for key, label in (("weekly", "Raw"), ("normalized", "Normalized"))
        for week, values in record(fatigue.get(key)).items()
    ])
    inol = record(weekly.get("inol"))
    add("Stimulus-Adjusted INOL", ["Lift", "Adjusted", "Raw", "Coefficient", "Coefficient source", "Target low", "Target high",
                                  "Phase multiplier", "Trend pressure (%)"], [
        [lift.title(), *fields(record(value), "adjusted", "raw", "coefficient", "coefficient_source"),
         *fields(record(record(inol.get("phase_adjusted_thresholds")).get(lift)), "display_low", "display_high", "phase_multiplier"),
         *fields(record(record(inol.get("trend_pressure")).get(lift)), "value%")]
        for lift, value in record(inol.get("lifts")).items()
    ])
    add("Weekly INOL", ["Lift", "Week", "Adjusted", "Raw"], [
        [lift.title(), week, value, record(record(inol.get("raw_per_lift_per_week")).get(lift)).get(week)]
        for lift, weeks in record(inol.get("per_lift_per_week")).items() for week, value in record(weeks).items()
    ])
    intensity = record(weekly.get("ri_distribution"))
    add("Relative Intensity", ["Lift", "Zone", "Sets", "Percent"], [
        [lift.title(), band.title(), *fields(record(value), "count", "pct")]
        for lift, bands in {"overall": intensity.get("overall"), **record(intensity.get("per_lift"))}.items()
        for band, value in record(bands).items()
    ])
    summary("Specificity", weekly.get("specificity_ratio"), {
        "Narrow (%)": "narrow%", "Broad (%)": "broad%", "Competition sets": "sbd_sets", "Accessory sets": "secondary_sets",
        "Weighted sets": "weighted_sets", "Total sets": "total_sets", "Narrow expected min (%)": "expected_band.narrow.min%",
        "Narrow expected max (%)": "expected_band.narrow.max%", "Broad expected min (%)": "expected_band.broad.min%",
        "Broad expected max (%)": "expected_band.broad.max%", "Narrow status": "narrow_status", "Broad status": "broad_status",
    })
    add("Volume Landmarks", ["Lift", "MV", "MEV", "MAV", "MRV", "Confidence", "Data status"], [
        [lift.title(), *fields(record(value), "mv", "mev", "mav", "mrv", "confidence", "reason")]
        for lift, value in record(weekly.get("volume_landmarks")).items()
    ])
    banister = record(weekly.get("banister"))
    summary("Banister Summary", banister, {"Fitness (CTL)": "ctl_today", "Fatigue (ATL)": "atl_today", "Form (TSB)": "tsb_today", "Data status": "reason"})
    start, end = weekly.get("window_start"), weekly.get("window_end")
    add("Banister Fitness and Fatigue", ["Date", "Fitness (CTL)", "Fatigue (ATL)", "Form (TSB)", "Load"], [
        fields(point, "date", "ctl", "atl", "tsb", "load") for point in points(banister.get("series"))
        if (not start or point.get("date", "") >= start) and (not end or point.get("date", "") <= end)
    ])
    timeline = record(weekly.get("peaking_timeline"))
    summary("Peaking Status", timeline, {"Status": "status_label", "Details": "status_message", "Meet date": "comp_date",
                                        "Current form (TSB)": "current_tsb", "Peak date": "peak_date", "Peak distance (days)": "peak_delta_days",
                                        "Closest peak": "closest_peak_date", "Closest projected TSB": "closest_projected_tsb"})
    add("Peaking Timeline", ["Date", "Actual TSB", "Projected TSB"], [
        fields(point, "date", "actual_tsb", "projected_tsb") for point in points(timeline.get("series"))
    ])
    add("Peaking Specificity", ["Date", "Narrow (%)", "Broad (%)", "Weeks to meet", "Narrow min (%)", "Narrow max (%)", "Broad min (%)", "Broad max (%)"], [
        fields(point, "date", "narrow%", "broad%", "weeks_to_comp", "expected_band.narrow.min%", "expected_band.narrow.max%",
               "expected_band.broad.min%", "expected_band.broad.max%") for point in points(timeline.get("specificity_points"))
    ])
    decoupling = record(weekly.get("decoupling"))
    summary("Fatigue Decoupling Summary", decoupling, {"Current decoupling": "current.decoupling", "Data status": "reason"})
    add("Fatigue Decoupling", ["Week", "e1RM slope (%/week)", "Fatigue slope (pp/week)", "Decoupling"], [
        fields(point, "week_start", "e1rm_slope_pct_per_week", "fi_slope_pct_points_per_week", "decoupling")
        for point in points(decoupling.get("series"))
    ])
    summary("Taper Quality", weekly.get("taper_quality"), {
        "Score": "score", "Label": "label", "Weeks to meet": "weeks_to_comp", "Volume reduction (%)": "components.volume_reduction%",
        "Intensity maintained (%)": "components.intensity_maintained%", "Fatigue trend (%)": "components.fatigue_trend%",
        "TSB (%)": "components.tsb%", "Data status": "reason",
    })
    add("Meet Projections", ["Meet", "Weeks to meet", "Squat (kg)", "Bench (kg)", "Deadlift (kg)", "Total (kg)", "Confidence (%)", "Method"], [
        fields(row, "comp_name", "weeks_to_comp", "lifts.squat.projected", "lifts.bench.projected", "lifts.deadlift.projected",
               "total", "confidence%", "method") for row in points(weekly.get("projections"))
    ])
    summary("Projection Calibration", weekly.get("projection_calibration"), {
        "Calibrated": "calibrated", "Meets": "meets", "Median performance realization ratio": "median_prr",
        "Projection multiplier": "lambda_multiplier",
    })
    add("Analysis Alerts", ["Severity", "Source", "Message", "Detail"], [
        fields(alert, "severity", "source", "message", "raw_detail") if isinstance(alert, dict) else [None, None, alert, None]
        for alert in weekly.get("alerts") or []
    ])
    add("Analysis Flags", ["Flag"], [[flag] for flag in weekly.get("flags") or []])
    return tables


def nutrition_tables(notes: list[dict], meta: dict) -> list[AnalysisTable]:
    metrics = {
        "Calories": "avg_daily_calories", "Protein (g)": "avg_protein_g", "Carbs (g)": "avg_carb_g",
        "Fat (g)": "avg_fat_g", "Sleep (hours)": "avg_sleep_hours", "Water": "water_intake",
    }
    current = meta.get("current_block_id")
    block = next((block for block in points(meta.get("blocks")) if (block.get("id") or block.get("block_id")) == current), {})
    weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    day = block.get("week_start_day")
    offset = weekdays.index(day) if day in weekdays else 0
    by_week: dict[date, list[dict]] = {}
    for note in notes:
        try:
            day = date.fromisoformat(note.get("date") or "")
        except (TypeError, ValueError):
            continue
        week = day - timedelta(days=(day.weekday() - offset) % 7)
        by_week.setdefault(week, []).append(note)
    if not by_week:
        return []

    def average(entries: list[dict], field: str, decimals: int = 1):
        values = [row[field] for row in entries if isinstance(row.get(field), (int, float)) and not isinstance(row[field], bool)]
        return round(mean(values), decimals) if values else None

    rows = [[week.isoformat(), *[average(entries, field) for field in metrics.values()],
             round(100 * sum(bool(row.get("consistent")) for row in entries) / len(entries)),
             next((row.get("water_unit") for row in entries if row.get("water_unit")), None)]
            for week, entries in sorted(by_week.items())]
    summary = []
    scoped = [note for entries in by_week.values() for note in entries]
    for index, (label, field) in enumerate(metrics.items(), start=1):
        values = [row[index] for row in rows if row[index] is not None]
        if values:
            change = round((values[-1] - values[0]) / (len(values) - 1), 1) if len(values) > 1 else None
            summary.append([label, average(scoped, field), change])
    tables = [("Nutrition and Sleep", ["Metric", "Average", "Change/week"], summary)] if summary else []
    return [*tables, ("Weekly Nutrition and Sleep", ["Week starting", *metrics, "Consistency (%)", "Water unit"], rows)]
