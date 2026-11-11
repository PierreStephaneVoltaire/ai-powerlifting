use std::collections::BTreeMap;

use serde::Serialize;

use super::Context;
use crate::calc::Computed;
use crate::calc::progression::{progression_rate, rpe_drift, volume_intensity};
use crate::util::{int_of, round};

#[derive(Debug, Serialize)]
pub struct LiftWorkload {
    pub progression_rate_kg_per_week: Option<f64>,
    pub fit_quality: Option<f64>,
    pub kendall_tau: Option<f64>,
    pub r2: Option<f64>,
    pub r_squared: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub volume_change_pct: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub intensity_change_pct: Option<f64>,
    pub rpe_trend: &'static str,
    pub failed_sets: i64,
    pub executed_sets: i64,
    pub planned_sets: i64,
    pub max_kg: f64,
    pub total_volume: f64,
}

#[derive(Debug, Serialize)]
pub struct ExerciseStats {
    pub total_sets: i64,
    pub total_volume: f64,
    pub max_kg: f64,
}

#[derive(Debug, Serialize)]
pub struct Workload {
    pub lifts: BTreeMap<String, LiftWorkload>,
    pub exercise_stats: BTreeMap<String, ExerciseStats>,
}

fn exercise_stats(context: &Context<'_>) -> BTreeMap<String, ExerciseStats> {
    let mut stats: BTreeMap<String, ExerciseStats> = BTreeMap::new();
    for exercise in context
        .completed_in_window
        .iter()
        .flat_map(|session| &session.exercises)
    {
        let name = exercise.name.trim();
        let sets = exercise.executed_sets();
        if name.is_empty() || sets <= 0.0 {
            continue;
        }
        let entry = stats.entry(name.to_owned()).or_insert(ExerciseStats {
            total_sets: 0,
            total_volume: 0.0,
            max_kg: 0.0,
        });
        entry.total_sets += int_of(sets);
        entry.total_volume += sets * exercise.reps * exercise.kg;
        if exercise.kg > entry.max_kg {
            entry.max_kg = exercise.kg;
        }
    }
    for entry in stats.values_mut() {
        entry.total_volume = round(entry.total_volume, 1);
        entry.max_kg = round(entry.max_kg, 1);
    }
    stats
}

pub fn build(context: &Context<'_>) -> (Workload, Vec<String>) {
    let names: Vec<&str> = context
        .completed_in_window
        .iter()
        .flat_map(|session| &session.exercises)
        .filter(|exercise| !exercise.name.is_empty() && exercise.executed_sets() > 0.0)
        .map(|exercise| exercise.key.as_str())
        .collect();
    let mut tracked: Vec<(&str, &str)> = Vec::new();
    for (canonical, output) in [
        ("squat", "squat"),
        ("bench press", "bench"),
        ("deadlift", "deadlift"),
        ("bench", "bench"),
    ] {
        if names.contains(&canonical) && !tracked.iter().any(|(_, existing)| *existing == output) {
            tracked.push((canonical, output));
        }
    }
    let mut lifts = BTreeMap::new();
    let mut flags = Vec::new();
    for (name, _) in tracked {
        let progression =
            progression_rate(&context.sessions, name, &context.program_start, context.end);
        let (rate, quality, tau, r2, r_squared) = match &progression {
            Computed::Ready(result) => (
                Some(result.slope_kg_per_week),
                Some(result.fit_quality),
                Some(result.kendall_tau),
                Some(result.r2),
                Some(result.r_squared),
            ),
            Computed::Insufficient(_) => (None, None, None, None, None),
        };
        let series = volume_intensity(&context.sessions, name, &context.program_start);
        let changes = series
            .as_ref()
            .filter(|series| series.volume.len() >= 2)
            .map(|series| {
                let (volume, intensity) = (&series.volume, &series.intensity);
                let (previous_volume, previous_intensity) =
                    (volume[volume.len() - 2], intensity[intensity.len() - 2]);
                let change = |latest: f64, previous: f64| {
                    round(
                        if previous > 0.0 {
                            (latest - previous) / previous * 100.0
                        } else {
                            0.0
                        },
                        1,
                    )
                };
                (
                    change(volume[volume.len() - 1], previous_volume),
                    change(intensity[intensity.len() - 1], previous_intensity),
                )
            });
        let drift = rpe_drift(
            &context.sessions,
            name,
            &context.program_start,
            4,
            context.phases,
        );
        let rpe_trend = match &drift {
            Computed::Ready(result) => {
                if let Some(flag) = result.flag {
                    flags.push(format!("{name}_rpe_{flag}"));
                }
                result.drift_direction
            }
            Computed::Insufficient(_) => "unknown",
        };
        let matching = || {
            context
                .completed_in_window
                .iter()
                .flat_map(|session| &session.exercises)
                .filter(move |exercise| exercise.key == name)
        };
        lifts.insert(
            name.to_owned(),
            LiftWorkload {
                progression_rate_kg_per_week: rate,
                fit_quality: quality,
                kendall_tau: tau,
                r2,
                r_squared,
                volume_change_pct: changes.map(|(volume, _)| volume),
                intensity_change_pct: changes.map(|(_, intensity)| intensity),
                rpe_trend,
                failed_sets: matching().map(|exercise| exercise.failed_sets()).sum(),
                executed_sets: int_of(matching().map(|exercise| exercise.executed_sets()).sum()),
                planned_sets: int_of(matching().map(|exercise| exercise.declared_sets).sum()),
                max_kg: round(
                    matching()
                        .filter(|exercise| exercise.executed_sets() > 0.0)
                        .map(|exercise| exercise.kg)
                        .fold(0.0_f64, f64::max),
                    1,
                ),
                total_volume: round(
                    matching().map(|exercise| exercise.executed_volume()).sum(),
                    1,
                ),
            },
        );
    }
    (
        Workload {
            lifts,
            exercise_stats: exercise_stats(context),
        },
        flags,
    )
}
