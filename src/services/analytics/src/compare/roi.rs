use std::collections::BTreeMap;

use serde_json::Value;

use super::format::{grouped, plural};
use super::types::{Correlation, DoseResponse, ExerciseRoi, Finding, RoiBlock, RoiSignal};
use crate::blocks::strength::{LIFTS, canonical_lift};
use crate::blocks::types::Bundle;
use crate::js::{coerce_number, locale_order, round_digits, round_or_null};

const ROI_LIMIT: usize = 20;

pub fn normalize_exercise(name: &str) -> String {
    name.to_lowercase()
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
}

fn is_competition_lift(name: &str) -> bool {
    matches!(
        normalize_exercise(name).as_str(),
        "squat" | "bench" | "bench press" | "deadlift"
    )
}

struct Stat {
    exercise: String,
    sets: f64,
    volume: f64,
}

fn exercise_stats(bundle: &Bundle) -> Vec<Stat> {
    bundle
        .weekly
        .get("exercise_stats")
        .and_then(Value::as_object)
        .map(|stats| {
            stats
                .iter()
                .map(|(exercise, entry)| {
                    let sets = coerce_number(entry.get("total_sets"));
                    let volume = coerce_number(entry.get("total_volume"));
                    Stat {
                        exercise: exercise.clone(),
                        sets: if sets.is_finite() { sets } else { 0.0 },
                        volume: if volume.is_finite() {
                            round_digits(volume, 0)
                        } else {
                            0.0
                        },
                    }
                })
                .filter(|stat| {
                    !stat.exercise.trim().is_empty()
                        && !is_competition_lift(&stat.exercise)
                        && (stat.sets > 0.0 || stat.volume > 0.0)
                })
                .collect()
        })
        .unwrap_or_default()
}

fn lift_deltas(bundle: &Bundle) -> BTreeMap<String, Option<f64>> {
    let delta = &bundle.historical.strength_delta;
    ["squat", "bench", "deadlift", "total"]
        .into_iter()
        .map(|lift| (lift.to_owned(), delta.lift(lift)))
        .collect()
}

struct Accumulator {
    display: String,
    total_sets: f64,
    total_volume: f64,
    blocks: Vec<RoiBlock>,
}

pub fn consolidated(bundles: &[Bundle], findings: &[Finding]) -> Vec<ExerciseRoi> {
    let mut rows: Vec<(String, Accumulator)> = Vec::new();
    for bundle in bundles {
        for stat in exercise_stats(bundle) {
            let key = normalize_exercise(&stat.exercise);
            let index = match rows.iter().position(|(existing, _)| *existing == key) {
                Some(index) => index,
                None => {
                    rows.push((
                        key,
                        Accumulator {
                            display: stat.exercise.clone(),
                            total_sets: 0.0,
                            total_volume: 0.0,
                            blocks: Vec::new(),
                        },
                    ));
                    rows.len() - 1
                }
            };
            let row = &mut rows[index].1;
            row.total_sets += stat.sets;
            row.total_volume += stat.volume;
            let block = RoiBlock {
                block_key: bundle.block.block_key.clone(),
                label: bundle.block.label.clone(),
                sets: stat.sets as i64,
                volume_kg: stat.volume as i64,
                correlations: Vec::new(),
                lift_deltas_kg: lift_deltas(bundle),
            };
            match row
                .blocks
                .iter_mut()
                .find(|existing| existing.block_key == block.block_key)
            {
                Some(slot) => *slot = block,
                None => row.blocks.push(block),
            }
        }
    }
    for finding in findings {
        let key = normalize_exercise(&finding.exercise);
        let Some((_, row)) = rows.iter_mut().find(|(existing, _)| *existing == key) else {
            continue;
        };
        if let Some(block) = row
            .blocks
            .iter_mut()
            .find(|block| block.block_key == finding.block_key)
        {
            block.correlations.push(Correlation {
                lift: finding.lift.clone(),
                direction: finding.direction.clone(),
                strength: finding.strength.clone(),
            });
        }
    }
    let mut result: Vec<ExerciseRoi> = rows
        .into_iter()
        .map(|(_, mut row)| {
            row.blocks.sort_by(|a, b| locale_order(&a.label, &b.label));
            let correlations: Vec<&Correlation> =
                row.blocks.iter().flat_map(|block| &block.correlations).collect();
            let count = |direction: &str| {
                correlations
                    .iter()
                    .filter(|item| item.direction == direction)
                    .count() as i64
            };
            let (positive, negative, unclear) = (count("positive"), count("negative"), count("unclear"));
            let mut lifts: Vec<String> = correlations.iter().map(|item| item.lift.clone()).collect();
            lifts.sort();
            lifts.dedup();
            let blocks = row.blocks.len() as i64;
            let confidence = if blocks >= 3 && positive + negative >= 2 {
                "high"
            } else if blocks >= 2 && positive + negative >= 1 {
                "medium"
            } else {
                "low"
            };
            let signals = positive + negative + unclear;
            let signal_text = if signals > 0 {
                format!(
                    "{positive} positive, {negative} negative, {unclear} unclear correlation signal{}",
                    plural(signals)
                )
            } else {
                "no correlation finding".to_owned()
            };
            let lift_text = if lifts.is_empty() {
                String::new()
            } else {
                format!(" across {}", lifts.join(", "))
            };
            let total_sets = round_digits(row.total_sets, 0);
            let total_volume = round_digits(row.total_volume, 0);
            ExerciseRoi {
                summary: format!(
                    "{} appeared in {blocks} source block{} with {} sets and {} kg volume; {signal_text}{lift_text}.",
                    row.display,
                    plural(blocks),
                    grouped(total_sets),
                    grouped(total_volume),
                ),
                exercise: row.display,
                block_count: blocks,
                total_sets: total_sets as i64,
                total_volume_kg: total_volume as i64,
                correlated_lifts: lifts,
                positive_signals: positive,
                negative_signals: negative,
                unclear_signals: unclear,
                confidence: confidence.to_owned(),
                blocks: row.blocks,
            }
        })
        .filter(|row| row.block_count >= 2 || row.positive_signals + row.negative_signals > 0)
        .collect();
    result.sort_by(|a, b| {
        let signals = |row: &ExerciseRoi| row.positive_signals + row.negative_signals;
        signals(b)
            .cmp(&signals(a))
            .then(b.block_count.cmp(&a.block_count))
            .then(b.total_volume_kg.cmp(&a.total_volume_kg))
    });
    result.truncate(ROI_LIMIT);
    result
}

fn lift_stats(bundle: &Bundle, lift: &str) -> (f64, f64) {
    exercise_stats_raw(bundle)
        .filter(|(name, _, _)| canonical_lift(name) == Some(lift))
        .fold((0.0, 0.0), |(sets, volume), (_, set_count, vol)| {
            (sets + set_count, volume + vol)
        })
}

fn exercise_stats_raw(bundle: &Bundle) -> impl Iterator<Item = (&str, f64, f64)> {
    bundle
        .weekly
        .get("exercise_stats")
        .and_then(Value::as_object)
        .into_iter()
        .flatten()
        .map(|(name, entry)| {
            let finite = |value: f64| if value.is_finite() { value } else { 0.0 };
            (
                name.as_str(),
                finite(coerce_number(entry.get("total_sets"))),
                finite(coerce_number(entry.get("total_volume"))),
            )
        })
}

pub fn dose_response(bundles: &[Bundle]) -> Vec<DoseResponse> {
    let mut rows = Vec::new();
    for bundle in bundles {
        let inol = |key: &str, lift: &str| {
            round_or_null(
                bundle
                    .weekly
                    .pointer(&format!("/inol/{key}/{lift}"))
                    .and_then(Value::as_f64),
                2,
            )
        };
        for lift in LIFTS {
            let (sets, volume) = lift_stats(bundle, lift);
            let delta = bundle.historical.strength_delta.lift(lift);
            rows.push(DoseResponse {
                block_key: bundle.block.block_key.clone(),
                label: bundle.block.label.clone(),
                lift: lift.to_owned(),
                avg_inol: inol("avg_inol", lift),
                raw_avg_inol: inol("raw_avg_inol", lift),
                sets: round_digits(sets, 0) as i64,
                volume_kg: round_digits(volume, 0) as i64,
                strength_delta_kg: delta,
                response_per_set_kg: delta
                    .filter(|_| sets > 0.0)
                    .and_then(|delta| round_or_null(Some(delta / sets), 3)),
                response_per1000_kg: delta
                    .filter(|_| volume > 0.0)
                    .and_then(|delta| round_or_null(Some(delta / (volume / 1000.0)), 3)),
            });
        }
    }
    rows
}

pub fn roi_signals(bundles: &[Bundle]) -> Vec<RoiSignal> {
    LIFTS
        .iter()
        .map(|lift| {
            let inol: Vec<f64> = bundles
                .iter()
                .filter_map(|bundle| bundle.historical.analytics_summary.avg_inol.get(*lift).copied())
                .collect();
            let deltas: Vec<f64> = bundles
                .iter()
                .filter_map(|bundle| bundle.historical.strength_delta.lift(lift))
                .collect();
            let average = |values: &[f64]| {
                (!values.is_empty())
                    .then(|| round_digits(values.iter().sum::<f64>() / values.len() as f64, 2))
            };
            let (avg_inol, avg_delta) = (average(&inol), average(&deltas));
            let interpretation = match (avg_inol, avg_delta) {
                (Some(inol), Some(delta)) if delta > 0.0 => {
                    format!("Positive average e1RM response at {inol:.2} INOL/wk")
                }
                (Some(inol), Some(_)) => {
                    format!("No positive average e1RM response at {inol:.2} INOL/wk")
                }
                _ => "Insufficient signal".to_owned(),
            };
            RoiSignal {
                lift: (*lift).to_owned(),
                avg_inol_per_week: avg_inol,
                avg_strength_delta_kg: avg_delta,
                interpretation,
            }
        })
        .collect()
}
