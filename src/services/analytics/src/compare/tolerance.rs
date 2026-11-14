use std::collections::BTreeMap;

use super::types::{Row, Tolerance, ToleranceLift};
use crate::blocks::strength::LIFTS;
use crate::blocks::types::Bundle;
use crate::js::round_or_null;

const REQUIRED_SAMPLE: i64 = 3;

pub fn build(rows: &[Row], bundles: &[Bundle]) -> Tolerance {
    let linked = rows
        .iter()
        .filter(|row| row.actual_total_kg.is_some())
        .count() as i64;
    let by_lift: BTreeMap<String, ToleranceLift> = LIFTS
        .iter()
        .map(|lift| {
            let positive: Vec<&Bundle> = bundles
                .iter()
                .filter(|bundle| {
                    bundle
                        .historical
                        .strength_delta
                        .lift(lift)
                        .is_some_and(|delta| delta > 0.0)
                })
                .collect();
            let best = positive
                .iter()
                .filter_map(|bundle| bundle.historical.analytics_summary.avg_inol.get(*lift))
                .copied()
                .fold(None, |best: Option<f64>, value| {
                    Some(best.map_or(value, |current| current.max(value)))
                });
            (
                (*lift).to_owned(),
                ToleranceLift {
                    best_observed_avg_inol: round_or_null(best, 2),
                    positive_delta_blocks: positive.len() as i64,
                },
            )
        })
        .collect();
    if linked < REQUIRED_SAMPLE {
        return Tolerance {
            status: "low_confidence".to_owned(),
            confidence: "low".to_owned(),
            sample_size: linked,
            required_sample_size: REQUIRED_SAMPLE,
            message: format!(
                "Need at least {} more comp-linked blocks before estimating volume tolerance.",
                (REQUIRED_SAMPLE - linked).max(0)
            ),
            by_lift,
        };
    }
    Tolerance {
        status: "estimated".to_owned(),
        confidence: if linked >= 5 { "medium" } else { "low" }.to_owned(),
        sample_size: linked,
        required_sample_size: REQUIRED_SAMPLE,
        message:
            "Volume tolerance is estimated from observed block-level INOL and strength outcomes."
                .to_owned(),
        by_lift,
    }
}
