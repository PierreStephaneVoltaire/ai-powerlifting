use std::collections::BTreeMap;

use super::weeks::infer_program_start;
use super::{Sessions, e1rm, is_primary};
use crate::util::median;

#[derive(Debug, Clone)]
pub struct WeekLoad {
    pub week: i64,
    pub is_deload: bool,
    pub is_break: bool,
    pub effective_index: Option<usize>,
}

impl WeekLoad {
    pub fn excluded(&self) -> bool {
        self.is_deload || self.is_break
    }
}

const VOLUME_THRESHOLD: f64 = 0.65;
const VOLUME_THRESHOLD_NO_MAIN: f64 = 0.75;
const ROLLING_WINDOW: usize = 4;

pub fn best_primary_e1rm(sessions: Sessions<'_>) -> Option<f64> {
    let mut best: Option<f64> = None;
    for session in sessions {
        for exercise in &session.exercises {
            if !is_primary(&exercise.key)
                || exercise.failed_sets() > 0
                || exercise.executed_sets() <= 0.0
            {
                continue;
            }
            if exercise.kg <= 0.0 || exercise.reps_int() <= 0 {
                continue;
            }
            let estimate = e1rm::estimate(exercise.kg, exercise.reps_int(), session.session_rpe);
            if let Some(value) =
                estimate.filter(|value| best.is_none_or(|current| *value > current))
            {
                best = Some(value);
            }
        }
    }
    best
}

fn primary_rpes(week: Sessions<'_>) -> Vec<f64> {
    let mut rpes = Vec::new();
    for session in week {
        if !session
            .exercises
            .iter()
            .any(|exercise| is_primary(&exercise.key))
        {
            continue;
        }
        if let Some(rpe) = session.session_rpe {
            rpes.push(rpe);
            continue;
        }
        rpes.extend(
            session
                .exercises
                .iter()
                .filter(|exercise| is_primary(&exercise.key))
                .filter_map(|exercise| exercise.rpe),
        );
    }
    rpes
}

pub fn detect(sessions: Sessions<'_>, program_start: &str) -> Vec<WeekLoad> {
    let owned_start;
    let program_start = if program_start.is_empty() {
        owned_start = infer_program_start(sessions);
        owned_start.as_str()
    } else {
        program_start
    };
    let mut by_week: BTreeMap<i64, Vec<&crate::model::Session>> = BTreeMap::new();
    let mut last_week = 1;
    for session in sessions {
        let Some(week) = session.week(program_start) else {
            continue;
        };
        last_week = last_week.max(week);
        if session.completed {
            by_week.entry(week).or_default().push(session);
        }
    }
    let mut results: Vec<WeekLoad> = Vec::new();
    let mut previous_volumes: Vec<f64> = Vec::new();
    let mut previous_e1rms: Vec<f64> = Vec::new();
    for week in 1..=last_week {
        let members = by_week.get(&week).map_or(&[][..], Vec::as_slice);
        let volume: f64 = members
            .iter()
            .flat_map(|session| &session.exercises)
            .map(|exercise| exercise.executed_volume())
            .sum();
        let is_break = volume == 0.0;
        let has_main = members
            .iter()
            .flat_map(|session| &session.exercises)
            .any(|exercise| is_primary(&exercise.key) && exercise.executed_sets() > 0.0);
        let mut is_deload = false;
        if !is_break && !previous_volumes.is_empty() {
            let from = previous_volumes.len().saturating_sub(ROLLING_WINDOW);
            let center = median(&previous_volumes[from..]);
            let threshold = if has_main {
                VOLUME_THRESHOLD
            } else {
                VOLUME_THRESHOLD_NO_MAIN
            };
            if center > 0.0 && volume < threshold * center {
                is_deload = if has_main {
                    let rpes = primary_rpes(members);
                    if rpes.is_empty() {
                        match (best_primary_e1rm(members), previous_e1rms.is_empty()) {
                            (Some(best), false) => {
                                let tail =
                                    &previous_e1rms[previous_e1rms.len().saturating_sub(2)..];
                                let reference = tail.iter().copied().fold(f64::MIN, f64::max);
                                best < reference * 0.90
                            }
                            _ => false,
                        }
                    } else {
                        rpes.iter().all(|rpe| *rpe <= 6.0)
                    }
                } else {
                    true
                };
            }
        }
        let best_e1rm = best_primary_e1rm(members);
        results.push(WeekLoad {
            week,
            is_deload,
            is_break,
            effective_index: None,
        });
        if !is_deload && !is_break {
            previous_volumes.push(volume);
            if let Some(value) = best_e1rm {
                previous_e1rms.push(value);
            }
        }
    }
    let mut effective = 0;
    for result in &mut results {
        if !result.excluded() {
            result.effective_index = Some(effective);
            effective += 1;
        }
    }
    results
}
