use std::collections::BTreeMap;

use chrono::NaiveDate;
use serde::Serialize;

use super::weeks::{find_phase, infer_program_start, week_start_for};
use super::{ByLift, Computed, Sessions, deload, e1rm, fatigue};
use crate::model::{Glossary, Lift, LiftProfile, Maxes, Phase};
use crate::util::{clamp, median, round};

const EPSILON: f64 = 0.02;
const INTENSITY_CEILING: f64 = 0.995;
const COEFFICIENT_MIN: f64 = 0.5;
const COEFFICIENT_MAX: f64 = 2.0;

#[derive(Debug, Clone, Copy, Serialize)]
pub struct Bounds {
    pub low: f64,
    pub high: f64,
}

fn default_bounds(lift: Lift) -> Bounds {
    match lift {
        Lift::Squat => Bounds {
            low: 1.6,
            high: 3.5,
        },
        Lift::Bench => Bounds {
            low: 2.0,
            high: 5.0,
        },
        Lift::Deadlift => Bounds {
            low: 1.0,
            high: 2.5,
        },
    }
}

fn profile_for(profiles: &[LiftProfile], lift: Lift) -> Option<&LiftProfile> {
    profiles.iter().find(|profile| profile.lift == lift.key())
}

#[derive(Debug, Clone, Copy, Serialize)]
pub struct Coefficient {
    pub value: f64,
    pub source: &'static str,
}

pub fn stimulus_coefficient(profiles: &[LiftProfile], lift: Lift) -> Coefficient {
    profile_for(profiles, lift)
        .and_then(|profile| profile.stimulus_coefficient)
        .filter(|value| (COEFFICIENT_MIN..=COEFFICIENT_MAX).contains(value))
        .map_or(
            Coefficient {
                value: 1.0,
                source: "default",
            },
            |value| Coefficient {
                value: round(value, 2),
                source: "profile",
            },
        )
}

pub fn thresholds(profiles: &[LiftProfile], lift: Lift) -> Bounds {
    let mut bounds = default_bounds(lift);
    if let Some(profile) = profile_for(profiles, lift) {
        if let Some(low) = profile.inol_low_threshold {
            bounds.low = round(low.max(0.0), 2);
        }
        if let Some(high) = profile.inol_high_threshold {
            bounds.high = round(bounds.low.max(high), 2);
        }
        if bounds.high < bounds.low {
            bounds.high = bounds.low;
        }
    }
    bounds
}

fn phase_multiplier(phase: Option<&Phase>, effective_week: Option<usize>) -> f64 {
    let Some(phase) = phase else {
        return 1.0;
    };
    let text = phase.text();
    if text.contains("deload") {
        0.45
    } else if text.contains("taper") || text.contains("peak") {
        0.65
    } else if text.contains("overreach") || phase.target_rpe_max.unwrap_or(0.0) >= 9.0 {
        1.25
    } else if text.contains("hypertrophy")
        || text.contains("volume")
        || text.contains("accumulation")
    {
        1.10
    } else if text.contains("strength") {
        1.00
    } else if effective_week.is_some_and(|week| week <= 2) {
        0.70
    } else {
        1.0
    }
}

fn uncertainty(selected_weeks: i64) -> (f64, f64) {
    match selected_weeks {
        ..=1 => (0.75, 1.25),
        2 => (0.85, 1.15),
        _ => (1.0, 1.0),
    }
}

#[derive(Default)]
struct WeekRi {
    volume: f64,
    weighted: f64,
    sets: f64,
    average: f64,
}

fn weekly_volume_ri(
    sessions: Sessions<'_>,
    glossary: &Glossary,
    anchor: NaiveDate,
    maxes: &Maxes,
) -> ByLift<BTreeMap<NaiveDate, WeekRi>> {
    let mut result: ByLift<BTreeMap<NaiveDate, WeekRi>> = ByLift::new();
    for session in sessions.iter().filter(|session| session.completed) {
        let Some(date) = session.date else {
            continue;
        };
        let week = week_start_for(date, anchor);
        for exercise in &session.exercises {
            let Some(lift) = glossary.narrow_lift(&exercise.key) else {
                continue;
            };
            let max = maxes.get(lift).unwrap_or(0.0);
            let (kg, reps, sets) = (exercise.kg, exercise.reps_int(), exercise.sets_int());
            if max <= 0.0 || kg <= 0.0 || reps <= 0 || sets <= 0 {
                continue;
            }
            let row = result.entry(lift, BTreeMap::new).entry(week).or_default();
            row.volume += (sets * reps) as f64 * kg;
            row.weighted += kg / max * sets as f64;
            row.sets += sets as f64;
        }
    }
    for (_, weeks) in &mut result.0 {
        for row in weeks.values_mut() {
            row.average = if row.sets > 0.0 {
                row.weighted / row.sets
            } else {
                0.0
            };
        }
    }
    result
}

#[derive(Debug, Serialize)]
pub struct AdjustedBounds {
    pub low: f64,
    pub high: f64,
    pub display_low: f64,
    pub display_high: f64,
    pub phase_multiplier: f64,
}

#[derive(Debug, Serialize)]
pub struct TrendPressure {
    pub value: f64,
    pub volume_ratio: f64,
    pub ri_ratio: f64,
}

#[derive(Debug, Serialize)]
pub struct LiftInol {
    pub raw: f64,
    pub adjusted: f64,
    pub coefficient: f64,
    pub coefficient_source: &'static str,
}

#[derive(Debug, Serialize)]
pub struct Inol {
    pub lifts: ByLift<LiftInol>,
    pub per_lift_per_week: ByLift<BTreeMap<i64, f64>>,
    pub avg_inol: ByLift<f64>,
    pub raw_per_lift_per_week: ByLift<BTreeMap<i64, f64>>,
    pub raw_avg_inol: ByLift<f64>,
    pub stimulus_coefficients: ByLift<f64>,
    pub coefficient_sources: ByLift<&'static str>,
    pub thresholds: ByLift<Bounds>,
    pub phase_adjusted_thresholds: ByLift<AdjustedBounds>,
    pub trend_pressure: ByLift<TrendPressure>,
    pub ramp_up_grace: ByLift<bool>,
    pub flags: Vec<String>,
}

fn round_weeks(weeks: &BTreeMap<i64, f64>) -> BTreeMap<i64, f64> {
    weeks
        .iter()
        .map(|(week, value)| (*week, round(*value, 2)))
        .collect()
}

fn average(weeks: &BTreeMap<i64, f64>) -> f64 {
    round(weeks.values().sum::<f64>() / weeks.len() as f64, 2)
}

pub struct InolInput<'a> {
    pub glossary: &'a Glossary,
    pub sessions: Sessions<'a>,
    pub history: Sessions<'a>,
    pub seed: Sessions<'a>,
    pub program_start: &'a str,
    pub maxes: &'a Maxes,
    pub profiles: &'a [LiftProfile],
    pub phases: &'a [Phase],
    pub selected_weeks: i64,
    pub reference: Option<NaiveDate>,
    pub today: NaiveDate,
}

pub fn compute(input: InolInput<'_>) -> Computed<Inol> {
    let basis: Sessions<'_> = if input.history.is_empty() {
        input.sessions
    } else {
        input.history
    };
    let seed: Sessions<'_> = if input.seed.is_empty() {
        basis
    } else {
        input.seed
    };
    let estimated;
    let maxes = if input.maxes.is_empty() {
        estimated = e1rm::from_sessions_default(seed, input.reference.unwrap_or(input.today));
        &estimated
    } else {
        input.maxes
    };
    if maxes.is_empty() {
        return Computed::insufficient("No current maxes available for INOL calculation");
    }
    let owned_start;
    let program_start = if input.program_start.is_empty() {
        owned_start = infer_program_start(basis);
        owned_start.as_str()
    } else {
        input.program_start
    };
    let mut latest_dates: BTreeMap<i64, NaiveDate> = BTreeMap::new();
    let mut raw: ByLift<BTreeMap<i64, f64>> = ByLift::new();
    let mut adjusted: ByLift<BTreeMap<i64, f64>> = ByLift::new();
    for session in input.sessions.iter().filter(|session| session.completed) {
        let Some(week) = session.week(program_start) else {
            continue;
        };
        if let Some(date) = session.date {
            let slot = latest_dates.entry(week).or_insert(date);
            *slot = (*slot).max(date);
        }
        for exercise in &session.exercises {
            let Some(lift) = input.glossary.narrow_lift(&exercise.key) else {
                continue;
            };
            let max = maxes.get(lift).unwrap_or(0.0);
            let (kg, reps, sets) = (exercise.kg, exercise.reps_int(), exercise.sets_int());
            if max <= 0.0 || kg <= 0.0 || reps <= 0 {
                continue;
            }
            let intensity = kg / max;
            let denominator =
                ((1.0 - intensity.min(INTENSITY_CEILING)).powi(2) + EPSILON.powi(2)).sqrt();
            let contribution = (reps as f64 / (100.0 * denominator)) * sets as f64;
            let coefficient = stimulus_coefficient(input.profiles, lift).value;
            *raw.entry(lift, BTreeMap::new).entry(week).or_insert(0.0) += contribution;
            *adjusted
                .entry(lift, BTreeMap::new)
                .entry(week)
                .or_insert(0.0) += contribution * coefficient;
        }
    }
    if adjusted.is_empty() {
        return Computed::insufficient("No qualifying sets for INOL");
    }
    let raw_avg: ByLift<f64> = ByLift(
        raw.0
            .iter()
            .map(|(lift, weeks)| (*lift, average(weeks)))
            .collect(),
    );
    let avg = ByLift(
        adjusted
            .0
            .iter()
            .map(|(lift, weeks)| (*lift, average(weeks)))
            .collect::<Vec<_>>(),
    );
    let effective: BTreeMap<i64, usize> = deload::detect(basis, program_start)
        .iter()
        .filter_map(|load| Some((load.week, load.effective_index?)))
        .collect();
    let (low_factor, high_factor) = uncertainty(input.selected_weeks);
    let anchor = fatigue::week_anchor(program_start, seed);
    let volume_ri = anchor.map(|anchor| weekly_volume_ri(seed, input.glossary, anchor, maxes));

    let mut result = Inol {
        lifts: ByLift::new(),
        per_lift_per_week: ByLift(
            adjusted
                .0
                .iter()
                .map(|(lift, weeks)| (*lift, round_weeks(weeks)))
                .collect(),
        ),
        avg_inol: ByLift::new(),
        raw_per_lift_per_week: ByLift(
            raw.0
                .iter()
                .map(|(lift, weeks)| (*lift, round_weeks(weeks)))
                .collect(),
        ),
        raw_avg_inol: raw_avg.clone(),
        stimulus_coefficients: ByLift::new(),
        coefficient_sources: ByLift::new(),
        thresholds: ByLift::new(),
        phase_adjusted_thresholds: ByLift::new(),
        trend_pressure: ByLift::new(),
        ramp_up_grace: ByLift::new(),
        flags: Vec::new(),
    };
    for (lift, average_value) in &avg.0 {
        let lift = *lift;
        let weeks = adjusted
            .get(lift)
            .map_or(Vec::new(), |weeks| weeks.keys().copied().collect());
        let latest = weeks.last().copied();
        let phase = find_phase(input.phases, latest.unwrap_or(0));
        let effective_week = latest.and_then(|week| effective.get(&week).copied());
        let multiplier = phase_multiplier(phase, effective_week);
        let bounds = thresholds(input.profiles, lift);
        let coefficient = stimulus_coefficient(input.profiles, lift);
        let scale = coefficient.value * multiplier;
        let (adjusted_low, adjusted_high) = (bounds.low * scale, bounds.high * scale);
        let (display_low, display_high) = (adjusted_low * low_factor, adjusted_high * high_factor);
        let mut grace = effective_week.is_some_and(|week| week <= 2);
        if grace && let Some(phase) = phase {
            let text = phase.text();
            grace = !text.contains("overreach")
                && !text.contains("peak")
                && phase.target_rpe_max.unwrap_or(0.0) < 9.0;
        }
        let (mut pressure, mut volume_ratio, mut ri_ratio) = (0.0, 1.0, 1.0);
        let latest_start = latest
            .and_then(|week| latest_dates.get(&week))
            .zip(anchor)
            .map(|(date, anchor)| week_start_for(*date, anchor));
        if let (Some(latest_start), Some(volume_ri)) = (latest_start, volume_ri.as_ref()) {
            let history_weeks = volume_ri.get(lift);
            let current = history_weeks.and_then(|weeks| weeks.get(&latest_start));
            let previous: Vec<&WeekRi> = history_weeks
                .map(|weeks| {
                    weeks
                        .iter()
                        .filter(|(week, row)| **week < latest_start && row.volume > 0.0)
                        .map(|(_, row)| row)
                        .collect::<Vec<_>>()
                })
                .unwrap_or_default();
            let previous = &previous[previous.len().saturating_sub(4)..];
            let volumes: Vec<f64> = previous
                .iter()
                .map(|row| row.volume)
                .filter(|value| *value > 0.0)
                .collect();
            let ris: Vec<f64> = previous
                .iter()
                .map(|row| row.average)
                .filter(|value| *value > 0.0)
                .collect();
            if !volumes.is_empty() {
                let center = median(&volumes);
                volume_ratio = if center > 0.0 {
                    current.map_or(0.0, |row| row.volume) / center
                } else {
                    1.0
                };
            }
            if !ris.is_empty() {
                let center = median(&ris);
                ri_ratio = if center > 0.0 {
                    current.map_or(0.0, |row| row.average) / center
                } else {
                    1.0
                };
            }
            pressure = 0.60 * clamp((volume_ratio - 1.0) / 0.50, 0.0, 1.0)
                + 0.40 * clamp((ri_ratio - 1.0) / 0.15, 0.0, 1.0);
        }
        if *average_value > display_high && pressure > 0.35 {
            result
                .flags
                .push(format!("overreaching_risk_{}", lift.key()));
        } else if *average_value > display_high {
            result
                .flags
                .push(format!("high_inol_monitor_{}", lift.key()));
        }
        if *average_value < display_low && !grace {
            result.flags.push(format!("low_stimulus_{}", lift.key()));
        }
        result.phase_adjusted_thresholds.0.push((
            lift,
            AdjustedBounds {
                low: round(adjusted_low, 2),
                high: round(adjusted_high, 2),
                display_low: round(display_low, 2),
                display_high: round(display_high, 2),
                phase_multiplier: round(multiplier, 2),
            },
        ));
        result.ramp_up_grace.0.push((lift, grace));
        result.trend_pressure.0.push((
            lift,
            TrendPressure {
                value: round(pressure, 3),
                volume_ratio: round(volume_ratio, 3),
                ri_ratio: round(ri_ratio, 3),
            },
        ));
        result.lifts.0.push((
            lift,
            LiftInol {
                raw: raw_avg.get(lift).copied().unwrap_or(0.0),
                adjusted: *average_value,
                coefficient: coefficient.value,
                coefficient_source: coefficient.source,
            },
        ));
        result
            .stimulus_coefficients
            .0
            .push((lift, coefficient.value));
        result
            .coefficient_sources
            .0
            .push((lift, coefficient.source));
        result.thresholds.0.push((lift, bounds));
    }
    result.avg_inol = avg;
    Computed::Ready(result)
}
