use std::cmp::Ordering;
use std::collections::BTreeMap;

use statrs::distribution::{ContinuousCDF, Normal, StudentsT};

use super::types::{Correlation, Kendall, Observation, Spearman};
use crate::blocks::strength::LIFTS;
use crate::util::round;

pub const LOW_N: usize = 5;
const MIN_PAIRS: usize = 3;
const STRONG_TAU: f64 = 0.6;
const MODERATE_TAU: f64 = 0.4;
const DIRECTION_TAU: f64 = 0.1;
pub const OUTCOMES: [&str; 4] = ["squat", "bench", "deadlift", "total"];

#[derive(Debug, Clone, Default)]
pub struct Row {
    pub block_key: String,
    pub exposures: BTreeMap<String, f64>,
    pub outcomes: BTreeMap<String, f64>,
}

pub fn outcome_name(outcome: &str) -> String {
    format!("{outcome}_e1rm_delta_per_week")
}

fn lift_of(exposure: &str) -> Option<&str> {
    exposure
        .split_once('.')
        .map(|(lift, _)| lift)
        .filter(|lift| LIFTS.contains(lift))
}

fn ranks(values: &[f64]) -> Vec<f64> {
    let mut order: Vec<usize> = (0..values.len()).collect();
    order.sort_by(|a, b| values[*a].partial_cmp(&values[*b]).unwrap_or(Ordering::Equal));
    let mut ranked = vec![0.0; values.len()];
    let mut start = 0;
    while start < order.len() {
        let mut end = start;
        while end + 1 < order.len() && values[order[end + 1]] == values[order[start]] {
            end += 1;
        }
        let average = (start + end) as f64 / 2.0 + 1.0;
        for index in &order[start..=end] {
            ranked[*index] = average;
        }
        start = end + 1;
    }
    ranked
}

fn pearson(xs: &[f64], ys: &[f64]) -> Option<f64> {
    let count = xs.len() as f64;
    let (mean_x, mean_y) = (xs.iter().sum::<f64>() / count, ys.iter().sum::<f64>() / count);
    let (mut covariance, mut var_x, mut var_y) = (0.0, 0.0, 0.0);
    for (x, y) in xs.iter().zip(ys) {
        covariance += (x - mean_x) * (y - mean_y);
        var_x += (x - mean_x).powi(2);
        var_y += (y - mean_y).powi(2);
    }
    let denominator = (var_x * var_y).sqrt();
    (denominator > 1e-12).then(|| covariance / denominator)
}

fn two_sided_normal(z: f64) -> Option<f64> {
    let normal = Normal::new(0.0, 1.0).ok()?;
    Some((2.0 * (1.0 - normal.cdf(z.abs()))).clamp(0.0, 1.0))
}

pub fn kendall(xs: &[f64], ys: &[f64]) -> Kendall {
    let empty = Kendall {
        tau: None,
        z: None,
        p: None,
    };
    if xs.len() < MIN_PAIRS {
        return empty;
    }
    match kendalls::tau_b_with_comparator(xs, ys, |a, b| a.partial_cmp(b).unwrap_or(Ordering::Equal))
    {
        Ok((tau, z)) if tau.is_finite() && z.is_finite() => Kendall {
            tau: Some(round(tau, 4)),
            z: Some(round(z, 4)),
            p: two_sided_normal(z).map(|p| round(p, 4)),
        },
        _ => empty,
    }
}

pub fn spearman(xs: &[f64], ys: &[f64]) -> Spearman {
    let empty = Spearman { rho: None, p: None };
    if xs.len() < MIN_PAIRS {
        return empty;
    }
    let Some(rho) = pearson(&ranks(xs), &ranks(ys)).filter(|rho| rho.is_finite()) else {
        return empty;
    };
    let degrees = (xs.len() - 2) as f64;
    let p = if rho.abs() >= 1.0 - 1e-12 {
        Some(0.0)
    } else {
        let t = rho * (degrees / (1.0 - rho * rho)).sqrt();
        StudentsT::new(0.0, 1.0, degrees)
            .ok()
            .map(|dist| (2.0 * (1.0 - dist.cdf(t.abs()))).clamp(0.0, 1.0))
    };
    Spearman {
        rho: Some(round(rho.clamp(-1.0, 1.0), 4)),
        p: p.map(|p| round(p, 4)),
    }
}

pub fn strength_of(tau: Option<f64>) -> &'static str {
    match tau.map(f64::abs) {
        Some(value) if value >= STRONG_TAU => "strong",
        Some(value) if value >= MODERATE_TAU => "moderate",
        _ => "weak",
    }
}

fn direction_of(tau: Option<f64>) -> &'static str {
    match tau {
        Some(value) if value > DIRECTION_TAU => "positive",
        Some(value) if value < -DIRECTION_TAU => "negative",
        _ => "none",
    }
}

pub fn correlate(
    exposure: &str,
    outcome: &str,
    pairs: &[(String, f64, f64)],
) -> Correlation {
    let xs: Vec<f64> = pairs.iter().map(|pair| pair.1).collect();
    let ys: Vec<f64> = pairs.iter().map(|pair| pair.2).collect();
    let kendall = kendall(&xs, &ys);
    let tau = kendall.tau;
    Correlation {
        exposure: exposure.to_owned(),
        outcome: outcome_name(outcome),
        lift: if outcome == "total" {
            lift_of(exposure).map(str::to_owned)
        } else {
            Some(outcome.to_owned())
        },
        n: pairs.len() as i64,
        low_n: pairs.len() < LOW_N,
        spearman: spearman(&xs, &ys),
        direction: direction_of(tau).to_owned(),
        strength: strength_of(tau).to_owned(),
        kendall,
        observations: pairs
            .iter()
            .map(|(block_key, x, y)| Observation {
                block_key: block_key.clone(),
                x: *x,
                y: *y,
            })
            .collect(),
    }
}

pub fn analyse(rows: &[Row]) -> Vec<Correlation> {
    let mut names: Vec<&String> = rows.iter().flat_map(|row| row.exposures.keys()).collect();
    names.sort();
    names.dedup();
    let mut result = Vec::new();
    for name in names {
        let outcomes: Vec<&str> = match lift_of(name) {
            Some(lift) => vec![lift, "total"],
            None => OUTCOMES.to_vec(),
        };
        for outcome in outcomes {
            let pairs: Vec<(String, f64, f64)> = rows
                .iter()
                .filter_map(|row| {
                    Some((
                        row.block_key.clone(),
                        *row.exposures.get(name)?,
                        *row.outcomes.get(outcome)?,
                    ))
                })
                .collect();
            if pairs.is_empty() {
                continue;
            }
            result.push(correlate(name, outcome, &pairs));
        }
    }
    result.sort_by(|a, b| {
        let magnitude = |item: &Correlation| item.kendall.tau.map_or(-1.0, f64::abs);
        magnitude(b)
            .partial_cmp(&magnitude(a))
            .unwrap_or(Ordering::Equal)
    });
    result
}
