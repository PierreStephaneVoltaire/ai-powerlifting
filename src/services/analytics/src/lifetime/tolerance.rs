use std::collections::BTreeMap;

use super::correlate::LOW_N;
use super::types::{Band, Range, Tolerance, VariableTolerance};
use crate::js::round_or_null;

const BAND_LABELS: [&str; 3] = ["low", "mid", "high"];

#[derive(Debug, Clone)]
pub struct Point {
    pub block_key: String,
    pub x: f64,
    pub delta_per_week: f64,
    pub label: String,
}

fn band(label: &str, members: &[&Point]) -> Band {
    let count = members.len() as f64;
    Band {
        label: label.to_owned(),
        min: members.iter().map(|p| p.x).fold(f64::MAX, f64::min),
        max: members.iter().map(|p| p.x).fold(f64::MIN, f64::max),
        blocks: members.len() as i64,
        mean_delta_per_week: round_or_null(
            Some(members.iter().map(|p| p.delta_per_week).sum::<f64>() / count),
            3,
        ),
        positive_share: round_or_null(
            Some(members.iter().filter(|p| p.label == "improved").count() as f64 / count),
            2,
        ),
    }
}

fn variable(points: &[Point]) -> VariableTolerance {
    let mut sorted: Vec<&Point> = points.iter().collect();
    sorted.sort_by(|a, b| a.x.total_cmp(&b.x));
    let bands = if sorted.len() < 3 {
        if sorted.is_empty() {
            Vec::new()
        } else {
            vec![band("all", &sorted)]
        }
    } else {
        let size = sorted.len().div_ceil(3);
        sorted
            .chunks(size)
            .zip(BAND_LABELS)
            .map(|(chunk, label)| band(label, chunk))
            .collect()
    };
    let improved: Vec<f64> = sorted
        .iter()
        .filter(|p| p.label == "improved")
        .map(|p| p.x)
        .collect();
    let positive_range = improved
        .iter()
        .copied()
        .reduce(f64::min)
        .zip(improved.iter().copied().reduce(f64::max))
        .map(|(min, max)| Range { min, max });
    let stall_onset = positive_range.as_ref().and_then(|range| {
        sorted
            .iter()
            .filter(|p| matches!(p.label.as_str(), "stalled" | "regressed") && p.x > range.max)
            .map(|p| p.x)
            .reduce(f64::min)
    });
    VariableTolerance {
        sample_size: points.len() as i64,
        low_n: points.len() < LOW_N,
        bands,
        positive_range,
        stall_onset,
    }
}

pub fn build(points: &BTreeMap<String, BTreeMap<String, Vec<Point>>>) -> Tolerance {
    Tolerance {
        min_sample_size: LOW_N as i64,
        by_lift: points
            .iter()
            .map(|(lift, variables)| {
                (
                    lift.clone(),
                    variables
                        .iter()
                        .map(|(name, items)| (name.clone(), variable(items)))
                        .collect(),
                )
            })
            .collect(),
    }
}
