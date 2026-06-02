













import argparse
import json
import sys
import urllib.request
import urllib.error
from datetime import date

def fetch_analysis(base_url: str, weeks: int) -> dict:
    url = f"{base_url}/v1/health/analysis/weekly?weeks={weeks}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())

def pp(obj, indent=2):
    return json.dumps(obj, indent=indent, ensure_ascii=False, default=str)

def build_audit(data: dict, weeks: int) -> str:
    out: list[str] = []
    w = lambda s='': out.append(s)

    w(f"{'='*80}")
    w(f"ANALYTICS AUDIT — Last {weeks} week(s)")
    w(f"Generated: {date.today().isoformat()}")
    w(f"{'='*80}")

    w()
    w("─" * 60)
    w("SECTION: Current Week & Phase")
    w("─" * 60)
    w(f"  Formula: max(1, (today - program_start).days // 7 + 1)")
    w(f"  current_week: {data.get('week')}")
    w(f"  phase/block: {data.get('block')}")

    w()
    w("─" * 60)
    w("SECTION: Sessions Analyzed")
    w("─" * 60)
    w(f"  sessions_in_window: {data.get('sessions_analyzed')}")

    w()
    w("─" * 60)
    w("SECTION: Deload Detection")
    w("  Formula: A week is DELOAD if (volume condition AND intensity condition)")
    w("  Volume (with primary lifts):    VL < 0.65 * median(prev 4 non-deload weeks)")
    w("  Volume (no primary lifts):      VL < 0.75 * median(prev 4 non-deload weeks)")
    w("  Intensity (RPE path):           all primary lift RPEs <= 6")
    w("  Intensity (e1RM path):          best_e1rm dropped >= 10% vs prev 2 non-deload weeks")
    w("  Stagnation (same e1RM) is NOT a deload.")
    w("  A week is a BREAK if no completed sessions or zero volume load.")
    w("  Week numbers are integers from session.week_number field (not fractional offsets).")
    w("─" * 60)
    di = data.get('deload_info', {})
    deload_wks = di.get('deload_weeks', [])
    break_wks = di.get('break_weeks', [])
    eff_wks = di.get('effective_training_weeks', 0)
    w(f"  Deload weeks ({len(deload_wks)}): {deload_wks}")
    w(f"  Break weeks ({len(break_wks)}): {break_wks}")
    w(f"  Effective training weeks: {eff_wks}")

    w()
    w("─" * 60)
    w("SECTION: Per-Lift Breakdown")
    w("─" * 60)
    lifts = data.get('lifts', {})
    for name, ld in lifts.items():
        w(f"\n  === {name.upper()} ===")

        w(f"  Progression Rate:")
        w(f"    Formula: Theil-Sen regression on best e1RM per effective training week")
        w(f"    Lookback: 90 days | Excludes: deload weeks, failed sets")
        prog = ld.get('progression_rate_kg_per_week')
        fit_quality = ld.get('fit_quality', ld.get('r_squared', ld.get('r2')))
        kendall_tau = ld.get('kendall_tau')
        if prog is not None:
            w(f"    slope_kg_per_week: {prog}")
            w(f"    fit_quality: {fit_quality}")
            w(f"    kendall_tau: {kendall_tau}")
        else:
            w(f"    INSUFFICIENT DATA")

        vol_chg = ld.get('volume_change_pct')
        int_chg = ld.get('intensity_change_pct')
        w(f"  Volume/Intensity Change:")
        w(f"    Formula: % change = ((recent - previous) / previous) * 100")
        if vol_chg is not None:
            w(f"    volume_change_pct: {vol_chg}")
            w(f"    intensity_change_pct: {int_chg}")

        w(f"  RPE Drift:")
        w(f"    Formula: Theil-Sen regression on RPE over time")
        w(f"    Residual mode: y = actual_rpe - phase_target_midpoint (if phase targets)")
        w(f"    Fit quality uses normalized MAD; Kendall tau is reported alongside slope.")
        w(f"    drift: {ld.get('rpe_trend', 'unknown')}")

        w(f"  Failed Sets: {ld.get('failed_sets', 0)}")

    w()
    w("─" * 60)
    w("SECTION: Compliance")
    w("  Formula: compliance_pct = completed_sessions / planned_sessions * 100")
    w("  Where completed = status in ('logged','completed')")
    w("  ALL weeks counted — deloads and programmed breaks are NOT excluded.")
    w("  A week with no planned sessions contributes nothing to either side.")
    w("─" * 60)
    comp = data.get('compliance', {})
    w(f"  Phase: {comp.get('phase')}")
    w(f"  Planned sessions: {comp.get('planned')}")
    w(f"  Completed sessions: {comp.get('completed')}")
    w(f"  Compliance %: {comp.get('pct')}")

    w()
    w("─" * 60)
    w("SECTION: Current Maxes (Estimated from Sessions)")
    w("  Formula: For each qualifying set: e1RM = kg / pct_of_1RM")
    w("  pct_of_1RM from RPE table (if session_rpe present, reps 1-6, rpe 6-10)")
    w("  OR from conservative rep table (if no session_rpe, reps 1-5)")
    w("  Requires >= 3 qualifying sets per lift")
    w("  Takes 90th percentile of sorted e1RM estimates")
    w("─" * 60)
    maxes = data.get('current_maxes', {})
    for lift in ('squat', 'bench', 'deadlift'):
        w(f"  {lift}: {maxes.get(lift)} kg")
    w(f"  Method: {maxes.get('method')}")

    w()
    w("─" * 60)
    w("SECTION: Estimated DOTS")
    w("  Formula: DOTS = (500 / denom) * total_kg")
    w("  where denom uses sex-specific bodyweight polynomial coefficients")
    w("  Requires bodyweight, sex, and all 3 lift maxes")
    w("─" * 60)
    w(f"  DOTS score: {data.get('estimated_dots')}")

    w()
    w("─" * 60)
    w("SECTION: Fatigue Index")
    w("  Formula: score = 0.40 * failed_ratio + 0.35 * composite_spike + 0.25 * rpe_stress")
    w("  failed_ratio   = failed_compound_sets / total_compound_sets")
    w("  composite_spike = weighted dimensional spike (axial+neural+peripheral+systemic)")
    w("  rpe_stress     = clamp((avg_session_rpe - 7.5) / 2.5, 0, 1)")
    w("                   RPE<=7.5 -> 0.0 | RPE 8.0 -> 0.2 | RPE 10 -> 1.0")
    w("  NOTE: skip_rate excluded — resting reduces fatigue, not increases it.")
    w("─" * 60)
    w(f"  Score: {data.get('fatigue_index')} (0-1 scale)")
    fc = data.get('fatigue_components', {})
    w(f"  Components:")
    w(f"    failed_compound_ratio: {fc.get('failed_compound_ratio')}")
    w(f"    composite_spike: {fc.get('composite_spike')}")
    w(f"    rpe_stress: {fc.get('rpe_stress')}")

    w()
    w("─" * 60)
    w("SECTION: Meet Projections")
    w("  Formula per lift:")
    w("    delta_w = slope from progression_rate()")
    w("    projected_gain = delta_w * λ * (1 - λ^n_t) / (1 - λ)  [diminishing returns]")
    w("    n_t = max(0, weeks_to_comp - weeks_taper - planned_deload_weeks)")
    w("    comp_max = (current_kg + projected_gain) * peak_factor")
    w("    Ceiling: current_kg * 1.10 | Floor: current_kg")
    w("  Returns INSUFFICIENT_DATA if no real progression data exists")
    w("─" * 60)
    projections = data.get('projections', [])
    reason = data.get('projection_reason')
    w(f"  Projection count: {len(projections)}")
    if reason:
        w(f"  Reason: {reason}")
    for proj in projections:
        w(f"\n  --- {proj.get('comp_name', 'Unknown')} ---")
        w(f"  total: {proj.get('total')}kg | confidence: {proj.get('confidence')}")
        w(f"  weeks_to_comp: {proj.get('weeks_to_comp')} | method: {proj.get('method')}")
        for ln in ('squat', 'bench', 'deadlift'):
            ld = proj.get('lifts', {}).get(ln, {})
            if ld:
                w(f"    {ln}: current={ld.get('current')} projected={ld.get('projected')} "
                  f"slope={ld.get('slope_kg_per_week')} conf={ld.get('confidence')} "
                  f"clamped={ld.get('ceiling_clamped')}")

    attempts = data.get('attempt_selection')
    if attempts:
        w()
        w("─" * 60)
        w("SECTION: Attempt Selection")
        w("  Formula: round_to_2_5(projected_max * attempt_pct)")
        w(f"  Pcts: {attempts.get('attempt_pct_used')}")
        w("─" * 60)
        for lift in ('squat', 'bench', 'deadlift'):
            la = attempts.get(lift, {})
            w(f"  {lift}: opener={la.get('opener')} second={la.get('second')} third={la.get('third')}")
        w(f"  Total: {attempts.get('total')}kg")

    w()
    w("─" * 60)
    w("SECTION: INOL (Intensity Number of Lifts)")
    w("  Formula per set: INOL_set = reps / (100 * sqrt((1 - min(I, 0.995))^2 + 0.02^2))")
    w("  where I = kg / estimated_max (relative intensity)")
    w("  Defaults: squat 1.6-3.5 | bench 2.0-5.0 | deadlift 1.0-2.5")
    w("─" * 60)
    inol = data.get('inol')
    if inol:
        w(f"  Avg INOL (window avg per lift): {pp(inol.get('avg_inol', {}))}")
        w(f"  Per-lift per-week: {pp(inol.get('per_lift_per_week', {}))}")
        w(f"  Flags (on window avg): {inol.get('flags', [])}")
    else:
        w(f"  INSUFFICIENT DATA")

    w()
    w("─" * 60)
    w("SECTION: ACWR (EWMA Daily Load Ratio)")
    w("  Formula per dimension: daily EWMA acute / daily EWMA chronic")
    w("  Seed = first 7 calendar days; lambdas: acute=0.25, chronic=2/29")
    w("  Requires >= 35 calendar days; returns insufficient_data otherwise.")
    w("  Composite = weighted: axial=0.30, neural=0.30, peripheral=0.25, systemic=0.15")
    w("  Zones: <0.8 detraining trend | 0.8-1.3 steady load | 1.3-1.5 rapid increase | >1.5 load spike")
    w("─" * 60)
    acwr = data.get('acwr') or {}
    if acwr.get('status') == 'insufficient_data':
        w(f"  INSUFFICIENT DATA: {acwr.get('reason')}")
    else:
        composite_label = acwr.get('composite_label', acwr.get('composite_zone'))
        w(f"  Composite: {acwr.get('composite')} ({composite_label})")
        for dim, info in acwr.get('dimensions', {}).items():
            w(f"    {dim}: value={info.get('value')} label={info.get('label', info.get('zone'))}")

    w()
    w("─" * 60)
    w("SECTION: Fatigue Dimensions (Weekly)")
    w("  Formula per set per dimension:")
    w("    F_axial     = profile.axial * weight^1.30 * reps")
    w("    F_neural    = profile.neural * reps * φ(I) * sqrt(weight / 100)")
    w("    F_peripheral = profile.peripheral * weight^1.15 * reps")
    w("    F_systemic  = profile.systemic * weight * reps * (1 + 0.30 * I)")
    w("    where φ(I) = ((max(0, I - 0.60)) / 0.40)^3")
    w("    and I = kg / e1RM (relative intensity)")
    w("  Week keys are integers (from session.week_number).")
    w("─" * 60)
    fd = data.get('fatigue_dimensions')
    if fd:
        weekly = fd.get('weekly', {})
        sorted_wk_keys = sorted(weekly.keys(), key=lambda x: int(x) if str(x).lstrip('-').isdigit() else float(x))
        for wk_key in sorted_wk_keys[-8:]:
            dims = weekly[wk_key]
            w(f"  W{wk_key}: axial={dims.get('axial', 0):.1f} neural={dims.get('neural', 0):.1f} "
              f"peripheral={dims.get('peripheral', 0):.1f} systemic={dims.get('systemic', 0):.1f}")
        acwr_dim = fd.get('acwr', {})
        spike_dim = fd.get('spike', {})
        if acwr_dim.get('status') == 'insufficient_data':
            w(f"  Dimensional ACWR: INSUFFICIENT DATA — {acwr_dim.get('reason')}")
        else:
            w(f"  Dimensional ACWR: {pp(acwr_dim)}")
        w(f"  Dimensional Spike: {pp(spike_dim)}")
        w(f"  Weights: {pp(fd.get('dimension_weights', {}))}")
    else:
        w("  No glossary data available")

    w()
    w("─" * 60)
    w("SECTION: Relative Intensity Distribution")
    w("  Formula: RI = kg / estimated_max")
    w("  Buckets: heavy (>0.85) | moderate (0.70-0.85) | light (<0.70)")
    w("  Only SBD exercises with known maxes")
    w("─" * 60)
    ri = data.get('ri_distribution')
    if ri:
        w(f"  Overall: {pp(ri.get('overall', {}))}")
        w(f"  Per-lift: {pp(ri.get('per_lift', {}))}")
    else:
        w(f"  INSUFFICIENT DATA")

    w()
    w("─" * 60)
    w("SECTION: Specificity Ratio")
    w("  narrow = SBD_sets / total_sets")
    w("  broad = (SBD_sets + secondary_sets) / total_sets")
    w("  Secondary = exercises in glossary with category squat/bench/deadlift but not main SBD names")
    w("─" * 60)
    sr = data.get('specificity_ratio')
    if sr:
        w(f"  Narrow (SBD only): {sr.get('narrow', 0):.1%}")
        w(f"  Broad (SBD + secondary): {sr.get('broad', 0):.1%}")
        w(f"  SBD sets: {sr.get('sbd_sets')} / Total sets: {sr.get('total_sets')}")
    else:
        w(f"  INSUFFICIENT DATA")

    w()
    w("─" * 60)
    w("SECTION: Readiness Score")
    w("  Formula: R = (1 - (0.30*F + 0.25*D + 0.20*W + 0.15*P + 0.10*B)) * 100")
    w("  F = fatigue_norm (0-1) from fatigue_index(14d)")
    w("  D = rpe_drift = |avg_session_rpe - phase_target_mid| / 2, clamped [0,1]")
    w("  W = subjective wellness = 1 - mean(wellness values)/5")
    w("  P = performance_trend = clamp((-slope(e1RM_14d)) / expected_weekly_delta, 0, 1)")
    w("  B = bw_deviation = cut-aware trajectory delta or bodyweight_CV / 0.03")
    w("  Zones: >75 green | >=50 yellow | else red")
    w("─" * 60)
    rs = data.get('readiness_score', {})
    w(f"  Score: {rs.get('score', 0)} / 100")
    w(f"  Zone: {rs.get('zone')}")
    rc = rs.get('components', {})
    w(f"  Components:")
    w(f"    fatigue_norm: {rc.get('fatigue_norm', 0)}")
    w(f"    rpe_drift: {rc.get('rpe_drift', 0)}")
    w(f"    wellness: {rc.get('wellness', 0)}")
    w(f"    performance_trend: {rc.get('performance_trend', 0)}")
    w(f"    bw_deviation: {rc.get('bw_deviation', 0)}")

    w()
    w("─" * 60)
    w("SECTION: Exercise Stats (completed sessions only)")
    w("  Only sessions with status='logged' or 'completed' are counted.")
    w("  Planned/skipped sessions are excluded to prevent inflated set counts.")
    w("  total_sets = sum of sets across completed sessions in window")
    w("  total_volume = sum of sets * reps * kg")
    w("  max_kg = highest kg seen")
    w("─" * 60)
    ex_stats = data.get('exercise_stats', {})
    for name, stats in sorted(ex_stats.items(), key=lambda x: -x[1].get('total_volume', 0)):
        w(f"  {name}: sets={stats.get('total_sets')} volume={stats.get('total_volume', 0):.0f} max={stats.get('max_kg', 0):.1f}kg")

    w()
    w("─" * 60)
    w("SECTION: Flags")
    w("─" * 60)
    flags = data.get('flags', [])
    if flags:
        for f in flags:
            w(f"  - {f}")
    else:
        w("  (none)")

    w()
    w("─" * 60)
    w(f"SECTION: Raw API Response (JSON)")
    w("─" * 60)
    w(pp(data))

    return '\n'.join(out)

def main():
    parser = argparse.ArgumentParser(description='Analytics audit via API')
    parser.add_argument('--base-url', default='http://192.168.2.56/agent',
                        help='Base URL for the agent API (default: http://192.168.2.56/agent)')
    args = parser.parse_args()

    for weeks in [1, 2, 4, 8]:
        fname = f'analytics_audit_{weeks}w.txt'
        print(f"Fetching {weeks}-week analysis from {args.base_url}...")
        try:
            data = fetch_analysis(args.base_url, weeks)
        except urllib.error.URLError as e:
            print(f"  ERROR: {e}", file=sys.stderr)
            continue
        print(f"Generating {fname}...")
        content = build_audit(data, weeks)
        with open(fname, 'w') as f:
            f.write(content)
        size_kb = len(content) / 1024
        print(f"  -> {fname} ({size_kb:.1f} KB)")

    print("\nDone. Files written to current directory.")

if __name__ == '__main__':
    main()
