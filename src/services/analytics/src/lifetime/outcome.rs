use std::collections::BTreeMap;

use super::types::{
    BlockClassification, Change, Classification, CompetitionResult, Counts, Drift, Outcome,
    Thresholds, Verdict,
};
use crate::blocks::outcome::{dots, ipf_gl};
use crate::blocks::scope::latest_bodyweight;
use crate::blocks::strength::{LIFTS, canonical_lift, set_e1rm};
use crate::blocks::types::Bundle;
use crate::calc::progression::rpe_drift;
use crate::compare::Context;
use crate::js::round_or_null;
use crate::model::{ProgramData, Session};
use crate::util::{mad, theil_sen};

pub const NOISE_MULTIPLIER: f64 = 1.0;
pub const MIN_THRESHOLD_PCT: f64 = 0.01;
pub const FALLBACK_NOISE_PCT: f64 = 0.02;
pub const MIN_SERIES_POINTS: usize = 4;
const MAD_TO_SIGMA: f64 = 1.4826;
const DRIFT_NAMES: [(&str, &str); 3] = [
    ("squat", "squat"),
    ("bench", "bench press"),
    ("deadlift", "deadlift"),
];

pub fn thresholds() -> Thresholds {
    Thresholds {
        method: "delta_vs_noise: improved above +threshold, regressed below -threshold, otherwise stalled; threshold = max(noise_multiplier * noise, min_threshold_pct * start e1RM); noise = 1.4826 * MAD of weekly best e1RM around its Theil-Sen trend, or fallback_noise_pct * start e1RM when the series is shorter than min_series_points".to_owned(),
        noise_multiplier: NOISE_MULTIPLIER,
        min_threshold_pct: MIN_THRESHOLD_PCT,
        fallback_noise_pct: FALLBACK_NOISE_PCT,
        min_series_points: MIN_SERIES_POINTS as i64,
    }
}

pub fn weekly_best(sessions: &[Session]) -> BTreeMap<&'static str, Vec<f64>> {
    let mut by_week: BTreeMap<(&'static str, i64), f64> = BTreeMap::new();
    for session in sessions.iter().filter(|session| session.completed) {
        let Some(week) = session.week_number.filter(|week| *week > 0) else {
            continue;
        };
        for exercise in &session.exercises {
            let Some(lift) = canonical_lift(&exercise.name) else {
                continue;
            };
            let rpe = exercise.rpe.or(session.session_rpe);
            if let Some(value) = set_e1rm(exercise.kg, exercise.reps, rpe) {
                let slot = by_week.entry((lift, week)).or_insert(value);
                *slot = slot.max(value);
            }
        }
    }
    let mut series: BTreeMap<&'static str, Vec<f64>> = BTreeMap::new();
    for ((lift, _), value) in by_week {
        series.entry(lift).or_default().push(value);
    }
    series
}

pub fn noise(series: &[f64]) -> Option<f64> {
    if series.len() < MIN_SERIES_POINTS {
        return None;
    }
    let xs: Vec<f64> = (0..series.len()).map(|index| index as f64).collect();
    let fit = theil_sen(series, &xs);
    let residuals: Vec<f64> = xs
        .iter()
        .zip(series)
        .map(|(x, y)| y - (fit.intercept + fit.slope * x))
        .collect();
    let value = MAD_TO_SIGMA * mad(&residuals);
    value.is_finite().then_some(value)
}

pub fn verdict(delta: Option<f64>, start: Option<f64>, noise_kg: Option<f64>) -> Verdict {
    let Some(delta) = delta else {
        return Verdict {
            label: "insufficient_data".to_owned(),
            delta_kg: None,
            noise_kg: None,
            threshold_kg: None,
            basis: "no_start_or_end_estimate".to_owned(),
        };
    };
    let reference = start.unwrap_or(0.0);
    let (noise_value, basis) = match noise_kg {
        Some(value) => (value, "weekly_mad"),
        None => (FALLBACK_NOISE_PCT * reference, "percent_fallback"),
    };
    let threshold = (NOISE_MULTIPLIER * noise_value).max(MIN_THRESHOLD_PCT * reference);
    let label = if delta > threshold {
        "improved"
    } else if delta < -threshold {
        "regressed"
    } else {
        "stalled"
    };
    Verdict {
        label: label.to_owned(),
        delta_kg: Some(delta),
        noise_kg: round_or_null(Some(noise_value), 2),
        threshold_kg: round_or_null(Some(threshold), 2),
        basis: basis.to_owned(),
    }
}

fn change(start: Option<f64>, end: Option<f64>, delta: Option<f64>, weeks: i64) -> Change {
    Change {
        start,
        end,
        delta,
        delta_per_week: delta.and_then(|delta| {
            round_or_null(Some(delta / weeks.max(1) as f64), 3)
        }),
    }
}

fn difference(start: Option<f64>, end: Option<f64>) -> Option<f64> {
    start
        .zip(end)
        .and_then(|(start, end)| round_or_null(Some(end - start), 2))
}

pub fn build(
    bundle: &Bundle,
    context: &Context,
    program: &ProgramData,
) -> (Outcome, BlockClassification) {
    let historical = &bundle.historical;
    let weeks = bundle.block.week_count;
    let series = weekly_best(&program.sessions);
    let mut e1rm = BTreeMap::new();
    let mut per_lift = BTreeMap::new();
    let mut squared = 0.0;
    for lift in LIFTS {
        let start = historical.start_strength.lift(lift);
        let end = historical.end_strength.lift(lift);
        let delta = historical.strength_delta.lift(lift);
        e1rm.insert(lift.to_owned(), change(start, end, delta, weeks));
        let noise_kg = series.get(lift).and_then(|values| noise(values));
        let result = verdict(delta, start, noise_kg);
        squared += result.threshold_kg.unwrap_or(0.0).powi(2);
        per_lift.insert(lift.to_owned(), result);
    }
    let total_start = historical.start_strength.total;
    e1rm.insert(
        "total".to_owned(),
        change(
            total_start,
            historical.end_strength.total,
            historical.strength_delta.total,
            weeks,
        ),
    );
    let total_delta = historical.strength_delta.total;
    let all_missing = per_lift.values().all(|item| item.label == "insufficient_data");
    let overall = if all_missing {
        verdict(None, None, None)
    } else {
        let threshold = squared.sqrt();
        let noise_equivalent = threshold / NOISE_MULTIPLIER;
        verdict(total_delta, total_start, Some(noise_equivalent))
    };
    let completed: Vec<&Session> = context.sessions.iter().filter(|s| s.completed).collect();
    let bodyweight_at = |date: &str| {
        latest_bodyweight(&completed, context.fallback_bodyweight, date, &context.weight_log)
    };
    let start_weight = bodyweight_at(&bundle.block.start_date);
    let end_weight = bodyweight_at(&bundle.block.end_date);
    let score = |total: Option<f64>, weight: Option<f64>, scorer: fn(f64, f64, &str) -> Option<f64>| {
        total
            .zip(weight)
            .and_then(|(total, weight)| scorer(total, weight, context.sex))
    };
    let start_dots = score(total_start, start_weight, dots);
    let end_dots = score(historical.end_strength.total, end_weight, dots);
    let start_gl = score(total_start, start_weight, ipf_gl);
    let end_gl = score(historical.end_strength.total, end_weight, ipf_gl);
    let refs: Vec<&Session> = program.sessions.iter().collect();
    let drift = DRIFT_NAMES
        .iter()
        .map(|(lift, name)| {
            let value = rpe_drift(
                &refs,
                name,
                &bundle.block.start_date,
                weeks,
                &program.phases,
            )
            .into_ready()
            .map(|drift| Drift {
                slope: drift.slope,
                direction: drift.drift_direction.to_owned(),
            });
            ((*lift).to_owned(), value)
        })
        .collect();
    let competition = historical.competition_outcome.as_ref().map(|outcome| CompetitionResult {
        name: outcome.competition_name.clone(),
        date: outcome.competition_date.clone(),
        total_kg: outcome
            .results
            .as_ref()
            .and_then(|results| results.get("total_kg"))
            .and_then(serde_json::Value::as_f64),
        dots: outcome.dots,
        ipf_gl: outcome.ipf_gl,
        projection_total_delta_kg: outcome
            .projection_accuracy
            .as_ref()
            .and_then(|accuracy| accuracy.get("total_kg"))
            .and_then(|total| total.get("deltaKg"))
            .and_then(serde_json::Value::as_f64),
    });
    (
        Outcome {
            e1rm,
            dots: change(start_dots, end_dots, difference(start_dots, end_dots), weeks),
            ipf_gl: change(start_gl, end_gl, difference(start_gl, end_gl), weeks),
            competition,
            rpe_drift: drift,
        },
        BlockClassification { overall, per_lift },
    )
}

pub fn summarize(blocks: &[BlockClassification]) -> Classification {
    let mut overall = Counts::default();
    let mut per_lift: BTreeMap<String, Counts> = LIFTS
        .iter()
        .map(|lift| ((*lift).to_owned(), Counts::default()))
        .collect();
    let tally = |counts: &mut Counts, label: &str| match label {
        "improved" => counts.improved += 1,
        "stalled" => counts.stalled += 1,
        "regressed" => counts.regressed += 1,
        _ => counts.insufficient_data += 1,
    };
    for block in blocks {
        tally(&mut overall, &block.overall.label);
        for (lift, verdict) in &block.per_lift {
            if let Some(counts) = per_lift.get_mut(lift) {
                tally(counts, &verdict.label);
            }
        }
    }
    Classification {
        thresholds: thresholds(),
        overall,
        per_lift,
    }
}
