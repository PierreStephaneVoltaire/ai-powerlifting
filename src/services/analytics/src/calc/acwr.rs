use std::collections::BTreeMap;

use chrono::{Duration, NaiveDate};
use serde::Serialize;

use super::weeks::{current_week, infer_program_start, planned_overreach};
use super::{Computed, Dims, Env, Sessions, e1rm, fatigue};
use crate::model::{Maxes, Phase};
use crate::util::round;

const ACUTE_LAMBDA: f64 = 2.0 / (7.0 + 1.0);
const CHRONIC_LAMBDA: f64 = 2.0 / (28.0 + 1.0);
const MIN_DAYS: i64 = 25;

#[derive(Debug, Serialize)]
pub struct Dimension {
    pub value: Option<f64>,
    pub zone: &'static str,
    pub label: String,
}

#[derive(Debug, Serialize)]
pub struct DimensionSet {
    pub axial: Dimension,
    pub neural: Dimension,
    pub peripheral: Dimension,
    pub systemic: Dimension,
}

#[derive(Debug, Serialize)]
pub struct Acwr {
    pub composite: Option<f64>,
    pub composite_zone: &'static str,
    pub composite_label: String,
    pub dimensions: DimensionSet,
}

pub fn zone(value: Option<f64>) -> &'static str {
    match value {
        None => "unknown",
        Some(value) if value < 0.8 => "detraining_trend",
        Some(value) if value <= 1.3 => "steady_load",
        Some(value) if value <= 1.5 => "rapid_increase",
        Some(_) => "load_spike",
    }
}

fn label(zone: &str, planned_overreach: bool) -> String {
    let base = match zone {
        "detraining_trend" => "Detraining trend",
        "steady_load" => "Steady load",
        "rapid_increase" => "Rapid increase",
        "load_spike" => "Load spike",
        _ => "Unknown",
    };
    if planned_overreach && zone != "unknown" {
        format!("{base} (expected during planned overreach)")
    } else {
        base.to_owned()
    }
}

fn ewma(loads: &[f64]) -> Option<f64> {
    if (loads.len() as i64) < MIN_DAYS {
        return None;
    }
    let seed = loads[..7].iter().sum::<f64>() / 7.0;
    let (mut acute, mut chronic) = (seed, seed);
    for load in &loads[7..] {
        acute = ACUTE_LAMBDA * load + (1.0 - ACUTE_LAMBDA) * acute;
        chronic = CHRONIC_LAMBDA * load + (1.0 - CHRONIC_LAMBDA) * chronic;
    }
    (chronic > 1e-12).then(|| round(acute / chronic, 3))
}

fn dimensional(
    daily: &BTreeMap<NaiveDate, Dims>,
    overreach: bool,
    reference: NaiveDate,
) -> Computed<Acwr> {
    let too_short = || {
        Computed::insufficient(format!(
            "Need at least {MIN_DAYS} calendar days of completed training for EWMA ACWR"
        ))
    };
    let Some(start) = daily.keys().next().copied() else {
        return too_short();
    };
    if reference < start {
        return Computed::insufficient("Reference date precedes available training data");
    }
    let days = (reference - start).num_days() + 1;
    if days < MIN_DAYS {
        return too_short();
    }
    let loads: Vec<Dims> = (0..days)
        .map(|offset| {
            daily
                .get(&(start + Duration::days(offset)))
                .copied()
                .unwrap_or_default()
        })
        .collect();
    let series = |pick: fn(&Dims) -> f64| ewma(&loads.iter().map(pick).collect::<Vec<f64>>());
    let values = [
        series(|dims| dims.axial),
        series(|dims| dims.neural),
        series(|dims| dims.peripheral),
        series(|dims| dims.systemic),
    ];
    let weights = super::DIMENSION_WEIGHTS.each();
    let any_valid = values.iter().any(Option::is_some);
    let composite = any_valid.then(|| {
        round(
            values
                .iter()
                .zip(weights)
                .map(|(value, weight)| value.unwrap_or(0.0) * weight)
                .sum(),
            3,
        )
    });
    let composite_zone = zone(composite);
    let dimension = |value: Option<f64>| Dimension {
        value,
        zone: zone(value),
        label: label(zone(value), overreach),
    };
    Computed::Ready(Acwr {
        composite,
        composite_zone,
        composite_label: label(composite_zone, overreach),
        dimensions: DimensionSet {
            axial: dimension(values[0]),
            neural: dimension(values[1]),
            peripheral: dimension(values[2]),
            systemic: dimension(values[3]),
        },
    })
}

pub fn compute(
    env: Env<'_>,
    sessions: Sessions<'_>,
    program_start: &str,
    maxes: &Maxes,
    phases: Option<&[Phase]>,
    week: Option<i64>,
    reference: Option<NaiveDate>,
) -> Computed<Acwr> {
    let owned_start;
    let program_start = if program_start.is_empty() {
        owned_start = infer_program_start(sessions);
        owned_start.as_str()
    } else {
        program_start
    };
    let estimated;
    let maxes = if maxes.is_empty() {
        estimated = e1rm::from_sessions_default(sessions, env.today);
        &estimated
    } else {
        maxes
    };
    let week = week.unwrap_or_else(|| current_week(program_start, sessions, env.today));
    let daily = fatigue::daily_by_dimension(env, sessions, maxes);
    let overreach = planned_overreach(phases.unwrap_or(&[]), Some(week), program_start, env.today);
    dimensional(&daily, overreach, reference.unwrap_or(env.today))
}
