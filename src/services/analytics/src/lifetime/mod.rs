use std::collections::BTreeMap;

use crate::blocks::Workspace;
use crate::blocks::scope::program_for_block;
use crate::blocks::strength::LIFTS;
use crate::blocks::types::Bundle;
use crate::calc::Env;
use crate::compare::{self, Context};
use crate::records::timestamp;

pub mod correlate;
pub mod exposure;
pub mod outcome;
pub mod signals;
pub mod tolerance;
pub mod types;

use correlate::{LOW_N, Row};
use signals::BlockFacts;
use tolerance::Point;
use types::{BlockRecord, Lifetime};

pub const SCHEMA_VERSION: i64 = 1;
pub const MIN_BLOCK_WEEKS: i64 = 4;

type PointsByLift = BTreeMap<String, BTreeMap<String, Vec<Point>>>;

pub fn record_for(
    workspace: &Workspace<'_>,
    env: Env<'_>,
    bundle: &Bundle,
) -> (BlockRecord, Context) {
    let (program, _) = program_for_block(workspace, &bundle.block);
    let context = compare::context::build(workspace, &bundle.block);
    let exposure = exposure::build(
        env,
        &program,
        &bundle.weekly,
        bundle.block.week_start,
        bundle.block.week_count,
    );
    let (outcome, classification) = outcome::build(bundle, &context, &program);
    let record = BlockRecord {
        block_key: bundle.block.block_key.clone(),
        label: bundle.block.label.clone(),
        start_date: bundle.block.start_date.clone(),
        end_date: bundle.block.end_date.clone(),
        week_count: bundle.block.week_count,
        is_current: bundle.block.is_current,
        training_only: bundle.block.training_only,
        exposure,
        outcome,
        classification,
        data_quality_flags: bundle.block.data_quality_flags.clone(),
    };
    (record, context)
}

fn rows_of(records: &[BlockRecord]) -> Vec<Row> {
    records
        .iter()
        .filter(|record| record.week_count >= MIN_BLOCK_WEEKS)
        .map(|record| {
            let mut row = Row {
                block_key: record.block_key.clone(),
                ..Row::default()
            };
            let exposure = &record.exposure;
            for lift in LIFTS {
                let Some(item) = exposure.lifts.get(lift) else {
                    continue;
                };
                row.exposures
                    .insert(format!("{lift}.weekly_hard_sets"), item.weekly_hard_sets);
                row.exposures
                    .insert(format!("{lift}.weekly_tonnage_kg"), item.weekly_tonnage_kg);
                row.exposures
                    .insert(format!("{lift}.weekly_frequency"), item.weekly_frequency);
                for (name, value) in [("avg_inol", item.avg_inol), ("avg_rpe", item.avg_rpe)] {
                    if let Some(value) = value {
                        row.exposures.insert(format!("{lift}.{name}"), value);
                    }
                }
            }
            let globals = [
                ("acwr_peak", exposure.acwr_peak),
                ("monotony_mean", exposure.monotony.mean),
                ("strain_mean", exposure.strain.mean),
                ("compliance_pct", exposure.compliance_pct),
                ("deload_per_10_weeks", Some(exposure.deload.per_10_weeks)),
                ("fatigue_index", exposure.fatigue.index),
                ("specificity_narrow", exposure.specificity.narrow),
                ("training_days_per_week", exposure.training_days_per_week),
                ("weekly_hard_sets", Some(exposure.weekly_hard_sets)),
                ("weekly_tonnage_kg", Some(exposure.weekly_tonnage_kg)),
                ("fatigue_axial_mean", exposure.fatigue.dimension_mean.axial),
                (
                    "fatigue_neural_mean",
                    exposure.fatigue.dimension_mean.neural,
                ),
                (
                    "fatigue_peripheral_mean",
                    exposure.fatigue.dimension_mean.peripheral,
                ),
                (
                    "fatigue_systemic_mean",
                    exposure.fatigue.dimension_mean.systemic,
                ),
            ];
            for (name, value) in globals {
                if let Some(value) = value {
                    row.exposures.insert(name.to_owned(), value);
                }
            }
            for key in correlate::OUTCOMES {
                if let Some(value) = record
                    .outcome
                    .e1rm
                    .get(key)
                    .and_then(|change| change.delta_per_week)
                {
                    row.outcomes.insert(key.to_owned(), value);
                }
            }
            row
        })
        .collect()
}

fn tolerance_points(records: &[BlockRecord]) -> PointsByLift {
    let mut points: PointsByLift = BTreeMap::new();
    for record in records.iter().filter(|r| r.week_count >= MIN_BLOCK_WEEKS) {
        for lift in LIFTS {
            let Some(exposure) = record.exposure.lifts.get(lift) else {
                continue;
            };
            let Some(delta) = record
                .outcome
                .e1rm
                .get(lift)
                .and_then(|change| change.delta_per_week)
            else {
                continue;
            };
            let label = record
                .classification
                .per_lift
                .get(lift)
                .map_or("insufficient_data", |verdict| verdict.label.as_str());
            for (name, value) in [
                ("weekly_hard_sets", Some(exposure.weekly_hard_sets)),
                ("avg_inol", exposure.avg_inol),
            ] {
                if let Some(x) = value {
                    points
                        .entry(lift.to_owned())
                        .or_default()
                        .entry(name.to_owned())
                        .or_default()
                        .push(Point {
                            block_key: record.block_key.clone(),
                            x,
                            delta_per_week: delta,
                            label: label.to_owned(),
                        });
                }
            }
        }
    }
    points
}

fn facts_of(records: &[BlockRecord]) -> BTreeMap<String, BlockFacts> {
    records
        .iter()
        .map(|record| {
            let mut classification: BTreeMap<String, String> = record
                .classification
                .per_lift
                .iter()
                .map(|(lift, verdict)| (lift.clone(), verdict.label.clone()))
                .collect();
            classification.insert(
                "total".to_owned(),
                record.classification.overall.label.clone(),
            );
            (
                record.block_key.clone(),
                BlockFacts {
                    label: record.label.clone(),
                    classification,
                },
            )
        })
        .collect()
}

fn limits(records: &[BlockRecord], correlations: &[types::Correlation]) -> Vec<String> {
    let short = records
        .iter()
        .filter(|record| record.week_count < MIN_BLOCK_WEEKS)
        .count();
    let mut notes = vec![
        "Associations are observational across blocks and do not establish causation.".to_owned(),
    ];
    if short > 0 {
        notes.push(format!(
            "{short} block(s) shorter than {MIN_BLOCK_WEEKS} weeks are excluded from correlations and tolerance bands."
        ));
    }
    if correlations.iter().any(|item| item.n < LOW_N as i64) {
        notes.push(format!(
            "Correlations with fewer than {LOW_N} blocks are flagged low_n and should be treated as exploratory."
        ));
    }
    notes
}

pub fn assemble(
    records: Vec<BlockRecord>,
    bundles: &[Bundle],
    contexts: &BTreeMap<String, Context>,
) -> Lifetime {
    let rows = rows_of(&records);
    let correlations = correlate::analyse(&rows);
    let points = tolerance_points(&records);
    let tolerance = tolerance::build(&points);
    let facts = facts_of(&records);
    let (worked, did_not_work) = signals::build(&correlations, &tolerance, &points, &facts);
    let comparison = compare::build(bundles, Vec::new(), contexts);
    let verdicts: Vec<_> = records
        .iter()
        .map(|record| record.classification.clone())
        .collect();
    Lifetime {
        schema_version: SCHEMA_VERSION,
        generated_at: timestamp(),
        block_count: records.len() as i64,
        min_block_weeks: MIN_BLOCK_WEEKS,
        classification: outcome::summarize(&verdicts),
        data_limits: limits(&records, &correlations),
        blocks: records,
        correlations,
        tolerance,
        exercise_roi: comparison.exercise_roi,
        lift_dose_response: comparison.lift_dose_response,
        training_day_response: comparison.training_day_response,
        pattern_signals: comparison.pattern_signals,
        worked,
        did_not_work,
    }
}
