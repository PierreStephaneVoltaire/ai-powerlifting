use std::collections::BTreeMap;

use chrono::{Duration, NaiveDate};
use serde::Serialize;

use super::{Computed, Dims, Env, Sessions, e1rm, fatigue};
use crate::model::Maxes;
use crate::util::round;

const ACUTE_LAMBDA: f64 = 2.0 / (7.0 + 1.0);
const CHRONIC_LAMBDA: f64 = 2.0 / (28.0 + 1.0);
const MIN_DAYS: i64 = 25;

#[derive(Debug, Serialize)]
pub struct Dimension {
    pub value: Option<f64>,
    pub acute: Option<f64>,
    pub chronic: Option<f64>,
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
    pub weights_used: Dims,
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
    if planned_overreach && matches!(zone, "rapid_increase" | "load_spike") {
        format!("{base} (expected during planned overreach)")
    } else {
        base.to_owned()
    }
}

struct Ratio {
    value: f64,
    acute: f64,
    chronic: f64,
}

fn ewma(loads: &[f64]) -> Option<Ratio> {
    if (loads.len() as i64) < MIN_DAYS {
        return None;
    }
    let seed = loads[..7].iter().sum::<f64>() / 7.0;
    let (mut acute, mut chronic) = (seed, seed);
    for load in &loads[7..] {
        acute = ACUTE_LAMBDA * load + (1.0 - ACUTE_LAMBDA) * acute;
        chronic = CHRONIC_LAMBDA * load + (1.0 - CHRONIC_LAMBDA) * chronic;
    }
    (chronic > 1e-12).then(|| Ratio {
        value: round(acute / chronic, 3),
        acute: round(acute, 1),
        chronic: round(chronic, 1),
    })
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
    let weight_total: f64 = values
        .iter()
        .zip(weights)
        .filter(|(value, _)| value.is_some())
        .map(|(_, weight)| weight)
        .sum();
    let used = |index: usize| {
        if values[index].is_some() && weight_total > 0.0 {
            weights[index] / weight_total
        } else {
            0.0
        }
    };
    let composite = (weight_total > 0.0).then(|| {
        round(
            values
                .iter()
                .enumerate()
                .map(|(index, value)| value.as_ref().map_or(0.0, |ratio| ratio.value) * used(index))
                .sum(),
            3,
        )
    });
    let composite_zone = zone(composite);
    let dimension = |ratio: &Option<Ratio>| {
        let value = ratio.as_ref().map(|ratio| ratio.value);
        Dimension {
            value,
            acute: ratio.as_ref().map(|ratio| ratio.acute),
            chronic: ratio.as_ref().map(|ratio| ratio.chronic),
            zone: zone(value),
            label: label(zone(value), overreach),
        }
    };
    Computed::Ready(Acwr {
        composite,
        composite_zone,
        composite_label: label(composite_zone, overreach),
        dimensions: DimensionSet {
            axial: dimension(&values[0]),
            neural: dimension(&values[1]),
            peripheral: dimension(&values[2]),
            systemic: dimension(&values[3]),
        },
        weights_used: Dims::from_each([used(0), used(1), used(2), used(3)]).map(|w| round(w, 4)),
    })
}

pub fn compute(
    env: Env<'_>,
    sessions: Sessions<'_>,
    maxes: &Maxes,
    planned_overreach: bool,
    reference: Option<NaiveDate>,
) -> Computed<Acwr> {
    let estimated;
    let maxes = if maxes.is_empty() {
        estimated = e1rm::from_sessions_default(sessions, env.today);
        &estimated
    } else {
        maxes
    };
    let daily = fatigue::daily_by_dimension(env, sessions, maxes);
    dimensional(&daily, planned_overreach, reference.unwrap_or(env.today))
}
