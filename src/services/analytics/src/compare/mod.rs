use std::collections::BTreeMap;

use crate::blocks::types::Bundle;
use crate::records::timestamp;
use crate::windows::CACHE_SCHEMA_VERSION;

pub mod context;
pub mod format;
pub mod patterns;
pub mod roi;
pub mod tolerance;
pub mod trends;
pub mod types;

pub use context::Context;
use types::{Comparison, Finding, MissingData};

pub fn build(
    bundles: &[Bundle],
    findings: Vec<Finding>,
    contexts: &BTreeMap<String, Context>,
) -> Comparison {
    let mut rows: Vec<_> = bundles
        .iter()
        .map(|bundle| trends::row(bundle, contexts.get(&bundle.block.block_key)))
        .collect();
    rows.sort_by(|a, b| a.start_date.cmp(&b.start_date));
    let exercise_roi = roi::consolidated(bundles, &findings);
    let series: Vec<_> = bundles
        .iter()
        .flat_map(|bundle| trends::series_for_block(bundle, contexts.get(&bundle.block.block_key)))
        .collect();
    let days = trends::training_days(&rows, &series);
    Comparison {
        schema_version: CACHE_SCHEMA_VERSION,
        generated_at: timestamp(),
        selected_block_keys: rows.iter().map(|row| row.block_key.clone()).collect(),
        trends: trends::trends(&rows),
        roi_signals: roi::roi_signals(bundles),
        pattern_signals: patterns::build(&rows, &exercise_roi, &findings, &days, &series),
        lift_dose_response: roi::dose_response(bundles),
        volume_tolerance: tolerance::build(&rows, bundles),
        missing_data_summary: rows
            .iter()
            .map(|row| MissingData {
                block_key: row.block_key.clone(),
                label: row.label.clone(),
                flags: row.data_quality_flags.clone(),
            })
            .collect(),
        exercise_roi,
        correlation_findings: findings,
        training_day_response: days,
        trend_series: series,
        rows,
    }
}
