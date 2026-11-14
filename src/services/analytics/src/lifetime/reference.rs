use std::collections::BTreeSet;

use super::correlate::{Row, outcome_name};
use super::types::{BlockRecord, CurrentVsHistory, Reference};
use crate::js::round_digits;

fn median(sorted: &[f64]) -> f64 {
    let middle = sorted.len() / 2;
    if sorted.len().is_multiple_of(2) {
        (sorted[middle - 1] + sorted[middle]) / 2.0
    } else {
        sorted[middle]
    }
}

fn position(current: f64, min: f64, max: f64) -> &'static str {
    if current < min {
        "below_range"
    } else if current > max {
        "above_range"
    } else {
        "within_range"
    }
}

fn lift_of(metric: &str) -> Option<String> {
    let head = metric.split('.').next()?;
    ["squat", "bench", "deadlift", "total"]
        .contains(&head)
        .then(|| head.to_owned())
}

pub fn build(
    current: BlockRecord,
    current_row: &Row,
    history: &[(&BlockRecord, Row)],
) -> CurrentVsHistory {
    let mut names: BTreeSet<(String, &'static str)> = BTreeSet::new();
    for name in current_row.exposures.keys() {
        names.insert((name.clone(), "exposure"));
    }
    for name in current_row.outcomes.keys() {
        names.insert((name.clone(), "outcome"));
    }
    let metrics = names
        .into_iter()
        .filter_map(|(name, kind)| {
            let pick = |row: &Row| {
                if kind == "exposure" {
                    row.exposures.get(&name).copied()
                } else {
                    row.outcomes.get(&name).copied()
                }
            };
            let value = pick(current_row)?;
            let mut values: Vec<f64> = history
                .iter()
                .filter_map(|(_, row)| pick(row))
                .filter(|v| v.is_finite())
                .collect();
            if values.is_empty() || !value.is_finite() {
                return None;
            }
            values.sort_by(f64::total_cmp);
            let (min, max) = (values[0], values[values.len() - 1]);
            let (metric, lift) = if kind == "outcome" {
                (outcome_name(&name), Some(name.clone()))
            } else {
                (name.clone(), lift_of(&name))
            };
            Some(Reference {
                metric,
                kind: kind.to_owned(),
                lift,
                current: round_digits(value, 3),
                n: values.len() as i64,
                min: round_digits(min, 3),
                median: round_digits(median(&values), 3),
                max: round_digits(max, 3),
                position: position(value, min, max).to_owned(),
            })
        })
        .collect();
    CurrentVsHistory {
        block_key: current.block_key.clone(),
        label: current.label.clone(),
        reference_block_keys: history
            .iter()
            .map(|(record, _)| record.block_key.clone())
            .collect(),
        current,
        metrics,
    }
}
