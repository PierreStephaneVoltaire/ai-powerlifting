import logging
from datetime import datetime, date, timedelta, timezone
from typing import Any, Dict, List, Optional, Set
import math
from statistics import median

logger = logging.getLogger(__name__)

# Constants and Tables (Mirrored from Node.js / Python analytics)
_PRIMARY_LIFT_NAMES = {"squat", "bench", "deadlift", "bench press"}

def canonical_lift(name: str) -> Optional[str]:
    nl = name.lower().strip()
    if nl == "squat": return "squat"
    if nl in ("bench", "bench press"): return "bench"
    if nl == "deadlift": return "deadlift"
    return None

def round_or_null(val: Optional[float], precision: int = 1) -> Optional[float]:
    if val is None or not math.isfinite(val):
        return None
    return round(float(val), precision)

def _num(val: Any) -> float:
    try:
        return float(val) if val is not None else 0.0
    except (ValueError, TypeError):
        return 0.0

def build_block_comparison(bundles: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Port of Node.js buildBlockComparison logic."""
    # 1. Sort bundles by start date
    ordered = sorted(bundles, key=lambda b: b.get("block", {}).get("startDate", ""))
    
    rows = []
    for b in ordered:
        rows.append(_comparison_row(b))
    
    # 2. Build consolidated ROI
    exercise_roi = _build_consolidated_exercise_roi(ordered)
    
    # 3. Build trend series
    trend_series = []
    for b in ordered:
        trend_series.extend(_build_block_trend_series(b))
    
    # 4. Build dose-response
    lift_dose_response = _build_lift_dose_response(ordered)
    training_day_response = _build_training_day_response(rows, trend_series)
    
    # 5. Build trends object for charts
    point = lambda r, v: {"blockKey": r["blockKey"], "label": r["label"], "value": v}
    trends = {
        "actualTotal": [point(r, r["actualTotalKg"]) for r in rows],
        "dots": [point(r, r["actualDots"] or r["estimatedDots"]) for r in rows],
        "ipfGl": [point(r, r["actualIpfGl"]) for r in rows],
        "e1rmTotal": [point(r, r["endTotalKg"]) for r in rows],
        "compliance": [point(r, r["compliancePct"]) for r in rows],
        "fatigue": [point(r, r["fatigueIndex"]) for r in rows],
        "volume": [point(r, r["totalVolumeKg"]) for r in rows],
    }
    
    # 6. Pattern signals
    pattern_signals = _build_pattern_signals(rows, exercise_roi, training_day_response, trend_series)
    
    return {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat() if hasattr(datetime, 'now') else datetime.utcnow().isoformat(),
        "selectedBlockKeys": [r["blockKey"] for r in rows],
        "rows": rows,
        "trends": trends,
        "exerciseRoi": exercise_roi,
        "patternSignals": pattern_signals,
        "liftDoseResponse": lift_dose_response,
        "trainingDayResponse": training_day_response,
        "trendSeries": trend_series,
        "volumeTolerance": _build_volume_tolerance(rows, ordered),
    }

def _comparison_row(bundle: Dict[str, Any]) -> Dict[str, Any]:
    block = bundle.get("block", {})
    hist = bundle.get("historical", {})
    summary = hist.get("analyticsSummary", {})
    comp = hist.get("competitionOutcome")
    
    start_total = round_or_null(sum(v for v in hist.get("startStrength", {}).values() if v), 1)
    end_total = round_or_null(sum(v for v in hist.get("endStrength", {}).values() if v), 1)
    
    return {
        "blockKey": block.get("blockKey"),
        "block": block.get("block"),
        "label": block.get("label"),
        "startDate": block.get("startDate"),
        "endDate": block.get("endDate"),
        "weekCount": block.get("weekCount"),
        "compliancePct": bundle.get("weekly", {}).get("compliance", {}).get("pct"),
        "fatigueIndex": bundle.get("weekly", {}).get("fatigue_index"),
        "totalVolumeKg": summary.get("totalVolumeKg"),
        "startTotalKg": start_total,
        "endTotalKg": end_total,
        "e1rmDeltaKg": round_or_null((end_total - start_total) if end_total and start_total else None, 1),
        "actualTotalKg": comp.get("actualTotalKg") if comp else None,
        "estimatedDots": hist.get("dots", {}).get("end"),
        "actualDots": comp.get("actualDots") if comp else None,
        "actualIpfGl": comp.get("actualIpfGl") if comp else None,
        "dataQualityFlags": block.get("dataQualityFlags", []),
    }

def _build_consolidated_exercise_roi(bundles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    # Consolidation logic for exercise ROI signals across blocks
    signals = {}
    for b in bundles:
        # Check if we have an AI correlation report for this block
        roi_findings = b.get("correlation_report", {}).get("findings", [])
        for f in roi_findings:
            ex = f.get("exercise")
            if not ex: continue
            
            if ex not in signals:
                signals[ex] = {
                    "exercise": ex,
                    "blockCount": 0,
                    "positiveSignals": 0,
                    "negativeSignals": 0,
                    "correlatedLifts": set(),
                    "totalSets": 0,
                    "totalVolume": 0,
                }
            
            s = signals[ex]
            s["blockCount"] += 1
            if f.get("correlation") == "positive": s["positiveSignals"] += 1
            elif f.get("correlation") == "negative": s["negativeSignals"] += 1
            
            lifts = f.get("correlated_lifts", [])
            if isinstance(lifts, list):
                for l in lifts: s["correlatedLifts"].add(l)
    
    # Also incorporate raw volume stats from each block's weekly stats
    for b in bundles:
        exercise_stats = b.get("weekly", {}).get("exercise_stats", {})
        for name, stats in exercise_stats.items():
            if name not in signals: continue # Only track exercises that have AI ROI signals for now
            s = signals[name]
            s["totalSets"] += int(_num(stats.get("total_sets")))
            s["totalVolume"] += _num(stats.get("total_volume"))

    result = []
    for ex, s in signals.items():
        score = s["positiveSignals"] - s["negativeSignals"]
        confidence = "high" if s["blockCount"] >= 3 else ("medium" if s["blockCount"] >= 2 else "low")
        
        summary = f"{s['positiveSignals']} positive / {s['negativeSignals']} negative signals over {s['blockCount']} blocks."
        
        result.append({
            "exercise": ex,
            "score": score,
            "blockCount": s["blockCount"],
            "positiveSignals": s["positiveSignals"],
            "negativeSignals": s["negativeSignals"],
            "correlatedLifts": list(s["correlatedLifts"]),
            "totalSets": s["totalSets"],
            "totalVolume": round(s["totalVolume"]),
            "confidence": confidence,
            "summary": summary,
        })
    
    return sorted(result, key=lambda x: x["score"], reverse=True)

def _build_block_trend_series(bundle: Dict[str, Any]) -> List[Dict[str, Any]]:
    # Port of buildBlockTrendSeries
    # This usually needs session data, but we might be able to use the weekly monotony_strain rows
    monotony = bundle.get("weekly", {}).get("monotony_strain", {})
    weekly_rows = monotony.get("weekly", [])
    
    result = []
    for row in weekly_rows:
        result.append({
            "blockKey": bundle.get("block", {}).get("blockKey"),
            "label": bundle.get("block", {}).get("label"),
            "weekNumber": row.get("week_num"),
            "weekStart": row.get("week_start"),
            "trainingDays": row.get("nonzero_training_days", 0),
            "strain": row.get("strain"),
            # Note: squat/bench/deadlift/total/dots would need raw session data for accurate per-week bests
            # If we don't have sessions, we can't fully reconstruct this series.
        })
    return result

def _build_lift_dose_response(bundles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = []
    for b in bundles:
        block = b.get("block", {})
        weekly = b.get("weekly", {})
        inol = weekly.get("inol", {})
        avg_inol = inol.get("avg_inol", {})
        
        exercise_stats = weekly.get("exercise_stats", {})
        
        for lift in ["squat", "bench", "deadlift"]:
            # Aggregate sets/volume for this lift category
            l_sets = 0
            l_vol = 0
            for name, stats in exercise_stats.items():
                if canonical_lift(name) == lift:
                    l_sets += int(_num(stats.get("total_sets")))
                    l_vol += _num(stats.get("total_volume"))
            
            delta = b.get("historical", {}).get("strengthDelta", {}).get(lift)
            
            rows.append({
                "blockKey": block.get("blockKey"),
                "label": block.get("label"),
                "lift": lift,
                "avgInol": round_or_null(avg_inol.get(lift), 2),
                "sets": l_sets,
                "volumeKg": round(l_vol),
                "strengthDeltaKg": delta,
                "responsePerSetKg": round_or_null(delta / l_sets, 3) if delta and l_sets > 0 else None,
                "responsePer1000Kg": round_or_null(delta / (l_vol / 1000), 3) if delta and l_vol > 0 else None,
            })
    return rows

def _build_training_day_response(rows: List[Dict[str, Any]], trend_series: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    result = []
    for r in rows:
        series = [p for p in trend_series if p["blockKey"] == r["blockKey"]]
        total_days = sum(p["trainingDays"] for p in series)
        weeks = len(series)
        result.append({
            "blockKey": r["blockKey"],
            "label": r["label"],
            "completedWeeks": weeks,
            "totalTrainingDays": total_days,
            "avgTrainingDaysPerWeek": round_or_null(total_days / weeks, 2) if weeks > 0 else None,
            "strengthDeltaKg": r["e1rmDeltaKg"],
            "compliancePct": r["compliancePct"],
        })
    return result

def _build_pattern_signals(rows: List[Dict[str, Any]], exercise_roi: List[Dict[str, Any]], training_day_response: List[Dict[str, Any]], trend_series: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    patterns = []
    
    if exercise_roi:
        top = exercise_roi[0]
        patterns.append({
            "kind": "roi",
            "finding": f"{top['exercise']} has the strongest consolidated exercise ROI signal.",
            "evidence": top["summary"],
            "confidence": top["confidence"],
        })
        
    repeated = next((x for x in exercise_roi if x["blockCount"] >= 2 and x["positiveSignals"] >= 2), None)
    if repeated:
        patterns.append({
            "kind": "roi",
            "finding": f"{repeated['exercise']} has repeated positive transfer signals.",
            "evidence": f"{repeated['positiveSignals']} positive correlations over {repeated['blockCount']} blocks.",
            "confidence": repeated["confidence"],
        })

    completed = [r for r in rows if r["e1rmDeltaKg"] is not None]
    if len(completed) >= 2:
        best = sorted(completed, key=lambda x: x["e1rmDeltaKg"], reverse=True)[0]
        patterns.append({
            "kind": "training_response",
            "finding": f"{best['label']} had the strongest total response.",
            "evidence": f"{best['e1rmDeltaKg']} kg total delta.",
            "confidence": "medium" if len(completed) >= 3 else "low",
        })

    return patterns

def _build_volume_tolerance(rows: List[Dict[str, Any]], bundles: List[Dict[str, Any]]) -> Dict[str, Any]:
    comp_linked = [r for r in rows if r["actualTotalKg"] is not None]
    by_lift = {}
    for lift in ["squat", "bench", "deadlift"]:
        positives = []
        for b in bundles:
            delta = b.get("historical", {}).get("strengthDelta", {}).get(lift)
            if delta and delta > 0:
                positives.append(b)
        
        best_inol = None
        for b in positives:
            val = b.get("historical", {}).get("analyticsSummary", {}).get("avgInol", {}).get(lift)
            if val and (best_inol is None or val > best_inol):
                best_inol = val
        
        by_lift[lift] = {
            "bestObservedAvgInol": round_or_null(best_inol, 2),
            "positiveDeltaBlocks": len(positives),
        }

    return {
        "status": "estimated" if len(comp_linked) >= 3 else "low_confidence",
        "confidence": "medium" if len(comp_linked) >= 5 else "low",
        "sampleSize": len(comp_linked),
        "requiredSampleSize": 3,
        "byLift": by_lift,
    }
