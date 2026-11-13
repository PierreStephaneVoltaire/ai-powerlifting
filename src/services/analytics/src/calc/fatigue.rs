use std::collections::BTreeMap;

use chrono::{Duration, NaiveDate};
use serde::Serialize;

use super::weeks::{calendar_week, infer_program_start, week_start_for};
use super::{Computed, Dims, Env, Sessions, acwr, banister, deload, e1rm};
use crate::model::{Exercise, Maxes};
use crate::util::{clamp, median, parse_date, round};

const AXIAL_EXPONENT: f64 = 1.30;
const PERIPHERAL_EXPONENT: f64 = 1.15;
const SYSTEMIC_BETA: f64 = 0.30;
const NEURAL_FLOOR: f64 = 0.60;
const NEURAL_CEILING: f64 = 0.995;
const NEURAL_LOAD_SCALE: f64 = 100.0;
const HALF_LIFE_DAYS: Dims = Dims {
    axial: 5.0,
    neural: 6.0,
    peripheral: 4.0,
    systemic: 2.0,
};
const BASELINE_LOOKBACK_DAYS: i64 = 56;
const CHRONIC_BASELINE_WEEKS: i64 = 12;
const BASELINE_GAP_DAYS: i64 = 14;
const DEFAULT_PROFILE: Dims = Dims {
    axial: 0.3,
    neural: 0.3,
    peripheral: 0.5,
    systemic: 0.3,
};
const COMPOUND_KEYWORDS: [&str; 8] = [
    "squat", "deadlift", "bench", "press", "row", "rdl", "pullup", "chinup",
];

pub fn profile_for(env: Env<'_>, name_key: &str) -> Dims {
    if !env.glossary.is_empty()
        && let Some(profile) = env.glossary.entry(name_key).and_then(|entry| entry.profile)
    {
        return Dims::from_each(profile);
    }
    DEFAULT_PROFILE
}

fn neural_scaling(intensity: f64) -> f64 {
    if intensity <= NEURAL_FLOOR {
        return 0.0;
    }
    ((intensity - NEURAL_FLOOR) / (NEURAL_CEILING - NEURAL_FLOOR)).powi(3)
}

pub fn per_set(weight: f64, reps: i64, profile: Dims, intensity: f64, rpe: Option<f64>) -> Dims {
    let multiplier = match rpe {
        Some(rpe) if rpe > 0.0 => 1.0 + 0.20 * clamp((rpe - 7.0) / 3.0, 0.0, 1.0),
        _ => 1.0,
    };
    let reps = reps as f64;
    Dims {
        axial: profile.axial * weight.powf(AXIAL_EXPONENT) * reps,
        neural: profile.neural
            * reps
            * neural_scaling(intensity)
            * (weight.max(0.0) / NEURAL_LOAD_SCALE).sqrt()
            * multiplier,
        peripheral: profile.peripheral * weight.powf(PERIPHERAL_EXPONENT) * reps * multiplier,
        systemic: profile.systemic * weight * reps * (1.0 + SYSTEMIC_BETA * intensity) * multiplier,
    }
}

pub fn resolve_intensity(
    env: Env<'_>,
    name_key: &str,
    weight: f64,
    reps: i64,
    rpe: Option<f64>,
    maxes: &Maxes,
) -> f64 {
    let direct = match name_key {
        "squat" => maxes.squat,
        "bench press" | "bench" => maxes.bench,
        "deadlift" => maxes.deadlift,
        _ => None,
    };
    if let Some(max) = direct.filter(|max| *max > 0.0) {
        return 1.0_f64.min(weight / max);
    }
    let mut category = "isolation";
    if !env.glossary.is_empty()
        && let Some(entry) = env.glossary.entry(name_key)
    {
        if let Some(max) = entry.e1rm {
            return 1.0_f64.min(weight / max);
        }
        category = entry.category.as_str();
    }
    if let Some(rpe) = rpe.filter(|rpe| *rpe > 0.0)
        && let Some(estimate) = e1rm::estimate(weight, reps, Some(rpe)).filter(|value| *value > 0.0)
    {
        return 1.0_f64.min(weight / estimate);
    }
    if weight > 0.0 && reps > 0 {
        let estimate = weight * (1.0 + reps as f64 / 30.0);
        let epley = 1.0_f64.min(weight / estimate);
        return if matches!(
            category,
            "squat" | "bench" | "deadlift" | "main" | "competition"
        ) {
            clamp(epley, 0.60, 0.95)
        } else if category.contains("variation") {
            clamp(epley, 0.55, 0.90)
        } else if category.contains("machine") || category.contains("compound") {
            clamp(epley, 0.50, 0.85)
        } else {
            clamp(epley, 0.45, 0.80)
        };
    }
    if matches!(category, "main" | "competition") {
        0.75
    } else if category.contains("variation") {
        0.70
    } else if category.contains("machine") || category.contains("compound") {
        0.65
    } else {
        0.55
    }
}

fn exercise_dims(
    env: Env<'_>,
    exercise: &Exercise,
    session_rpe: Option<f64>,
    maxes: &Maxes,
) -> Option<(Dims, i64)> {
    let (kg, sets, reps) = (exercise.kg, exercise.sets_int(), exercise.reps_int());
    if kg <= 0.0 || sets <= 0 || reps <= 0 {
        return None;
    }
    let profile = profile_for(env, &exercise.key);
    let rpe = exercise.rpe.or(session_rpe);
    let intensity = resolve_intensity(env, &exercise.key, kg, reps, rpe, maxes);
    Some((per_set(kg, reps, profile, intensity, rpe), sets))
}

pub fn weekly_by_dimension(
    env: Env<'_>,
    sessions: Sessions<'_>,
    program_start: &str,
    maxes: &Maxes,
) -> BTreeMap<i64, Dims> {
    let mut weekly: BTreeMap<i64, Dims> = BTreeMap::new();
    for session in sessions.iter().filter(|session| session.completed) {
        let Some(week) = session.week(program_start) else {
            continue;
        };
        let entry = weekly.entry(week).or_default();
        for exercise in &session.exercises {
            if let Some((dims, sets)) = exercise_dims(env, exercise, session.session_rpe, maxes) {
                entry.add(dims, sets as f64);
            }
        }
    }
    weekly
}

pub fn daily_by_dimension(
    env: Env<'_>,
    sessions: Sessions<'_>,
    maxes: &Maxes,
) -> BTreeMap<NaiveDate, Dims> {
    let mut daily: BTreeMap<NaiveDate, Dims> = BTreeMap::new();
    for session in sessions.iter().filter(|session| session.completed) {
        let Some(date) = session.date else {
            continue;
        };
        let entry = daily.entry(date).or_default();
        for exercise in &session.exercises {
            if let Some((dims, sets)) = exercise_dims(env, exercise, session.session_rpe, maxes) {
                entry.add(dims, sets as f64);
            }
        }
    }
    daily
}

pub fn week_anchor(program_start: &str, sessions: Sessions<'_>) -> Option<NaiveDate> {
    parse_date(program_start)
        .filter(|_| !program_start.is_empty())
        .or_else(|| sessions.iter().filter_map(|session| session.date).min())
}

pub fn weekly_by_date(
    env: Env<'_>,
    sessions: Sessions<'_>,
    maxes: &Maxes,
    anchor: NaiveDate,
) -> BTreeMap<NaiveDate, Dims> {
    let mut weekly: BTreeMap<NaiveDate, Dims> = BTreeMap::new();
    for (date, dims) in daily_by_dimension(env, sessions, maxes) {
        weekly
            .entry(week_start_for(date, anchor))
            .or_default()
            .add(dims, 1.0);
    }
    weekly
}

#[derive(Debug, Clone, Copy, Serialize)]
pub struct ChronicBaseline {
    pub weekly: Dims,
    pub weeks_used: usize,
}

pub fn chronic_baseline(
    env: Env<'_>,
    sessions: Sessions<'_>,
    maxes: &Maxes,
    reference: NaiveDate,
    program_start: &str,
) -> ChronicBaseline {
    let unit = Dims {
        axial: 1.0,
        neural: 1.0,
        peripheral: 1.0,
        systemic: 1.0,
    };
    let Some(anchor) = week_anchor(program_start, sessions) else {
        return ChronicBaseline {
            weekly: unit,
            weeks_used: 0,
        };
    };
    let weekly = weekly_by_date(env, sessions, maxes, anchor);
    let floor = reference - Duration::weeks(CHRONIC_BASELINE_WEEKS);
    let in_range = |start: &NaiveDate| *start > floor && *start <= reference;
    let complete: Vec<&Dims> = weekly
        .iter()
        .filter(|(start, _)| in_range(start) && **start + Duration::days(6) <= reference)
        .map(|(_, dims)| dims)
        .collect();
    let rows = if complete.is_empty() {
        weekly
            .iter()
            .filter(|(start, _)| in_range(start))
            .map(|(_, dims)| dims)
            .collect()
    } else {
        complete
    };
    let center = |pick: fn(&Dims) -> f64| {
        let mut values: Vec<f64> = rows
            .iter()
            .map(|dims| pick(dims))
            .filter(|value| *value > 0.0)
            .collect();
        values.sort_by(f64::total_cmp);
        if values.is_empty() {
            1.0
        } else {
            median(&values).max(1.0)
        }
    };
    ChronicBaseline {
        weekly: Dims {
            axial: center(|dims| dims.axial),
            neural: center(|dims| dims.neural),
            peripheral: center(|dims| dims.peripheral),
            systemic: center(|dims| dims.systemic),
        },
        weeks_used: rows.len(),
    }
}

pub struct Reservoir {
    pub date: NaiveDate,
    pub dims: Dims,
}

pub fn reservoir_series(
    env: Env<'_>,
    sessions: Sessions<'_>,
    program_start: &str,
    maxes: &Maxes,
    reference: NaiveDate,
) -> Vec<Reservoir> {
    let daily = daily_by_dimension(env, sessions, maxes);
    let Some(first) = daily.keys().next().copied() else {
        return Vec::new();
    };
    let start = parse_date(program_start).unwrap_or(first);
    let decay = HALF_LIFE_DAYS.map(|half_life| (-(2.0_f64.ln()) / half_life).exp());
    let mut state = Dims::default();
    let mut series = Vec::new();
    let mut day = start;
    while day <= reference {
        let intake = daily.get(&day).copied().unwrap_or_default();
        state = Dims {
            axial: state.axial * decay.axial + intake.axial,
            neural: state.neural * decay.neural + intake.neural,
            peripheral: state.peripheral * decay.peripheral + intake.peripheral,
            systemic: state.systemic * decay.systemic + intake.systemic,
        };
        series.push(Reservoir {
            date: day,
            dims: state,
        });
        day += Duration::days(1);
    }
    series
}

#[derive(Debug, Serialize)]
pub struct ReservoirStress {
    pub dimensions: Dims,
    pub weighted: f64,
    pub max_dimension: f64,
    pub composite: f64,
    pub confidence: &'static str,
    pub context_days_used: usize,
}

pub fn reservoir_stress(series: &[Reservoir], target: NaiveDate) -> ReservoirStress {
    let current = series.first().and_then(|first| {
        let offset = (target - first.date).num_days();
        usize::try_from(offset)
            .ok()
            .and_then(|index| series.get(index))
    });
    let Some(current) = current else {
        return ReservoirStress {
            dimensions: Dims::default(),
            weighted: 0.0,
            max_dimension: 0.0,
            composite: 0.0,
            confidence: "low",
            context_days_used: 0,
        };
    };
    let from = target - Duration::days(BASELINE_LOOKBACK_DAYS);
    let to = target - Duration::days(BASELINE_GAP_DAYS);
    let baseline: Vec<&Reservoir> = series
        .iter()
        .filter(|row| from <= row.date && row.date <= to)
        .collect();
    let confidence = match baseline.len() {
        28.. => "high",
        14.. => "medium",
        _ => "low",
    };
    let stress = |value: fn(&Dims) -> f64| {
        let values: Vec<f64> = baseline
            .iter()
            .map(|row| value(&row.dims))
            .filter(|value| *value > 0.0)
            .collect();
        if values.is_empty() {
            return 0.0;
        }
        let center = median(&values);
        let ratio = if center > 0.0 {
            value(&current.dims) / center
        } else {
            0.0
        };
        clamp((ratio - 1.0) / 0.75, 0.0, 1.0)
    };
    let stresses = Dims {
        axial: stress(|dims| dims.axial),
        neural: stress(|dims| dims.neural),
        peripheral: stress(|dims| dims.peripheral),
        systemic: stress(|dims| dims.systemic),
    };
    let weighted = stresses.weighted();
    let max_dimension = stresses.max();
    let composite = 0.60 * max_dimension + 0.40 * weighted;
    ReservoirStress {
        dimensions: stresses.map(|value| round(value, 3)),
        weighted: round(weighted, 3),
        max_dimension: round(max_dimension, 3),
        composite: round(composite, 3),
        confidence,
        context_days_used: baseline.len(),
    }
}

#[derive(Debug, Serialize)]
pub struct Spike {
    pub dimensions: BTreeMap<&'static str, f64>,
    pub composite: Option<f64>,
}

pub fn dimensional_spike(weekly: &BTreeMap<i64, Dims>) -> Spike {
    if weekly.len() < 2 {
        return Spike {
            dimensions: BTreeMap::new(),
            composite: None,
        };
    }
    let rows: Vec<Dims> = weekly.values().copied().collect();
    let spike = |value: fn(&Dims) -> f64| {
        let series: Vec<f64> = rows.iter().map(value).collect();
        let current = series[series.len() - 1];
        let history = &series[..series.len() - 1];
        let previous = &history[history.len().saturating_sub(3)..];
        let mean = previous.iter().sum::<f64>() / previous.len() as f64;
        round(
            if mean > 0.0 {
                clamp((current - mean) / mean, 0.0, 1.0)
            } else {
                0.0
            },
            3,
        )
    };
    let dims = Dims {
        axial: spike(|dims| dims.axial),
        neural: spike(|dims| dims.neural),
        peripheral: spike(|dims| dims.peripheral),
        systemic: spike(|dims| dims.systemic),
    };
    Spike {
        dimensions: BTreeMap::from([
            ("axial", dims.axial),
            ("neural", dims.neural),
            ("peripheral", dims.peripheral),
            ("systemic", dims.systemic),
        ]),
        composite: Some(round(dims.weighted(), 3)),
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct Components {
    pub failure_stress: f64,
    pub acute_spike_stress: f64,
    pub rpe_stress: f64,
    pub chronic_load_stress: f64,
    pub overload_streak: f64,
    pub intensity_density_stress: f64,
    pub monotony_stress: f64,
    pub failed_compound_ratio: f64,
    pub composite_spike: f64,
    pub reservoir_stress: f64,
    pub reservoir_dimension_stress: Dims,
    pub reservoir_max_dimension_stress: f64,
    pub reservoir_weighted_stress: f64,
    pub fatigue_context_days_used: usize,
    pub latest_week_fi: f64,
    pub window_mean_fi: f64,
    pub window_peak_fi: f64,
    pub fatigue_window_weeks: i64,
    pub fatigue_context_weeks_used: usize,
    pub fatigue_context_confidence: &'static str,
    pub fatigue_model: &'static str,
    pub current_state_fi: f64,
    pub window_weighted_fi: f64,
}

#[derive(Debug, Serialize)]
pub struct FatigueIndex {
    pub score: f64,
    pub components: Components,
    pub flags: Vec<&'static str>,
}

#[derive(Clone, Copy, Default)]
pub struct FatigueWindow<'a> {
    pub days: i64,
    pub reference: Option<NaiveDate>,
    pub start: Option<&'a str>,
    pub end: Option<&'a str>,
    pub target_rpe_midpoint: Option<f64>,
}

struct WeekFi {
    score: f64,
    components: Components,
    confidence: &'static str,
}

fn median_of(mut values: Vec<f64>) -> f64 {
    values.sort_by(f64::total_cmp);
    median(&values)
}

pub fn fatigue_index(
    env: Env<'_>,
    sessions: Sessions<'_>,
    window: FatigueWindow<'_>,
    maxes: &Maxes,
    program_start: &str,
) -> Computed<FatigueIndex> {
    let reference = window.reference.unwrap_or(env.today);
    let end = match window.end {
        Some(text) => parse_date(text).unwrap_or(reference),
        None => reference,
    };
    let start = match window.start {
        Some(text) => parse_date(text).unwrap_or(end - Duration::days(window.days)),
        None => end - Duration::days(window.days),
    };
    let history: Vec<&crate::model::Session> = sessions
        .iter()
        .copied()
        .filter(|session| session.completed && session.date.is_some_and(|date| date <= end))
        .collect();
    let window_week_count = ((((end - start).num_days() + 1) as f64 / 7.0).ceil() as i64).max(1);
    let owned_start;
    let program_start = if program_start.is_empty() {
        owned_start = infer_program_start(&history);
        owned_start.as_str()
    } else {
        program_start
    };
    let start_day = parse_date(program_start)
        .or_else(|| {
            if program_start.is_empty() {
                Some(
                    history
                        .iter()
                        .filter_map(|session| session.date)
                        .min()
                        .unwrap_or(env.today),
                )
            } else {
                None
            }
        })
        .unwrap_or(env.today);
    let mut by_week: BTreeMap<i64, Vec<&crate::model::Session>> = BTreeMap::new();
    for session in &history {
        if let Some(week) = session.week(program_start) {
            by_week.entry(week).or_default().push(session);
        }
    }
    let loads = deload::detect(&history, program_start);
    let deload_weeks: Vec<i64> = loads
        .iter()
        .filter(|load| load.excluded())
        .map(|load| load.week)
        .collect();
    let weekly_dims = weekly_by_dimension(env, &history, program_start, maxes);
    let series = reservoir_series(env, &history, program_start, maxes, end);
    let first_week = by_week
        .keys()
        .chain(weekly_dims.keys())
        .copied()
        .min()
        .unwrap_or(1);
    let last_week = calendar_week(end, start_day);
    let monotony_rows: BTreeMap<NaiveDate, banister::MonotonyWeek> =
        banister::monotony_strain(env, &history, program_start, maxes, Some(end), None)
            .weekly
            .into_iter()
            .filter_map(|row| Some((parse_date(&row.week_start)?, row)))
            .collect();
    let mut weekly: BTreeMap<i64, WeekFi> = BTreeMap::new();
    let mut streak = 0.0_f64;
    for week in first_week..=last_week {
        let members = by_week.get(&week).map_or(&[][..], Vec::as_slice);
        let (mut failed, mut compound) = (0.0, 0.0);
        for exercise in members.iter().flat_map(|session| &session.exercises) {
            if COMPOUND_KEYWORDS
                .iter()
                .any(|keyword| exercise.lower.contains(keyword))
            {
                compound += exercise.executed_sets();
                failed += exercise.failed_sets() as f64;
            }
        }
        let failed_ratio = if compound > 0.0 {
            failed / compound
        } else {
            0.0
        };
        let failure_stress = clamp(failed_ratio / 0.15, 0.0, 1.0);
        let week_start = start_day + Duration::days((week - 1) * 7);
        let week_end = week_start + Duration::days(6);
        let recent: Vec<&crate::model::Session> = history
            .iter()
            .copied()
            .filter(|session| {
                session
                    .date
                    .is_some_and(|date| date <= week_end && date >= week_start - Duration::days(28))
            })
            .collect();
        let spike = dimensional_spike(&weekly_by_dimension(env, &recent, program_start, maxes));
        let composite_spike = spike.composite.unwrap_or(0.0);
        let acute_spike_stress = clamp((composite_spike - 0.05) / 0.35, 0.0, 1.0);

        let mut excesses = Vec::new();
        let (mut high, mut rated) = (0usize, 0usize);
        for session in members {
            let rpe = session.session_rpe.unwrap_or(0.0);
            if rpe > 0.0 {
                rated += 1;
                let excess = match window.target_rpe_midpoint {
                    Some(target) => clamp((rpe - target) / 2.0, 0.0, 1.0),
                    None => clamp((rpe - 7.0) / 3.0, 0.0, 1.0),
                };
                excesses.push(excess.powi(2));
                if rpe >= 9.0 {
                    high += 1;
                }
            }
        }
        let rpe_base = if excesses.is_empty() {
            0.0
        } else {
            (excesses.iter().sum::<f64>() / excesses.len() as f64).sqrt()
        };
        let rpe_frequency = if rated > 0 {
            high as f64 / rated as f64
        } else {
            0.0
        };
        let rpe_stress = clamp(0.70 * rpe_base + 0.30 * rpe_frequency, 0.0, 1.0);

        let reservoir =
            reservoir_stress(&series, std::cmp::min(week_start + Duration::days(6), end));
        let chronic = reservoir.composite;

        let (mut heavy, mut very_heavy, mut eligible) = (0i64, 0i64, 0i64);
        for exercise in members.iter().flat_map(|session| &session.exercises) {
            let sets = exercise.sets_int();
            if sets <= 0 || exercise.kg <= 0.0 || exercise.reps_int() <= 0 {
                continue;
            }
            let max = match exercise.key.as_str() {
                "squat" => maxes.squat,
                "bench" | "bench press" => maxes.bench,
                "deadlift" => maxes.deadlift,
                other if !env.glossary.is_empty() => {
                    env.glossary.entry(other).and_then(|entry| entry.e1rm)
                }
                _ => None,
            };
            if let Some(max) = max.filter(|max| *max > 0.0) {
                let intensity = exercise.kg / max;
                eligible += sets;
                if intensity >= 0.90 {
                    very_heavy += sets;
                    heavy += sets;
                } else if intensity >= 0.85 {
                    heavy += sets;
                }
            }
        }
        let heavy_ratio = if eligible > 0 {
            heavy as f64 / eligible as f64
        } else {
            0.0
        };
        let very_heavy_ratio = if eligible > 0 {
            very_heavy as f64 / eligible as f64
        } else {
            0.0
        };
        let density = clamp(
            0.60 * heavy_ratio / 0.35 + 0.40 * very_heavy_ratio / 0.15,
            0.0,
            1.0,
        );

        let (monotony, strain) = monotony_rows
            .get(&week_start)
            .map_or((0.0, 0.0), |row| (row.monotony, row.strain));
        let prior: Vec<f64> = (week - 4..week)
            .filter_map(|prior_week| {
                monotony_rows.get(&(start_day + Duration::days((prior_week - 1) * 7)))
            })
            .map(|row| row.strain)
            .collect();
        let median_strain = if prior.is_empty() {
            0.0
        } else {
            median_of(prior)
        };
        let monotony_stress = clamp((monotony - 1.5) / 1.0, 0.0, 1.0).max(if median_strain > 0.0 {
            clamp((strain / median_strain - 1.0) / 0.5, 0.0, 1.0)
        } else {
            0.0
        });

        let acwr_value = acwr::compute(env, &history, maxes, false, Some(week_end))
            .ready()
            .and_then(|result| result.composite)
            .unwrap_or(0.0);
        let overload = if deload_weeks.contains(&week) {
            false
        } else {
            chronic >= 0.35
                || acwr_value >= 1.15
                || density >= 0.50
                || (median_strain > 0.0 && strain >= median_strain * 1.25)
        };
        streak = if overload { streak + 1.0 } else { 0.0 };
        let overload_streak = clamp(streak / 4.0, 0.0, 1.0);

        let score = clamp(
            0.10 * failure_stress
                + 0.12 * acute_spike_stress
                + 0.15 * rpe_stress
                + 0.34 * chronic
                + 0.10 * overload_streak
                + 0.10 * density
                + 0.09 * monotony_stress,
            0.0,
            1.0,
        );
        weekly.insert(
            week,
            WeekFi {
                score,
                confidence: reservoir.confidence,
                components: Components {
                    failure_stress: round(failure_stress, 3),
                    acute_spike_stress: round(acute_spike_stress, 3),
                    rpe_stress: round(rpe_stress, 3),
                    chronic_load_stress: round(chronic, 3),
                    overload_streak: round(overload_streak, 3),
                    intensity_density_stress: round(density, 3),
                    monotony_stress: round(monotony_stress, 3),
                    failed_compound_ratio: round(failed_ratio, 3),
                    composite_spike: round(composite_spike, 3),
                    reservoir_stress: round(chronic, 3),
                    reservoir_dimension_stress: reservoir.dimensions,
                    reservoir_max_dimension_stress: reservoir.max_dimension,
                    reservoir_weighted_stress: reservoir.weighted,
                    fatigue_context_days_used: reservoir.context_days_used,
                    latest_week_fi: 0.0,
                    window_mean_fi: 0.0,
                    window_peak_fi: 0.0,
                    fatigue_window_weeks: 0,
                    fatigue_context_weeks_used: 0,
                    fatigue_context_confidence: "low",
                    fatigue_model: "reservoir_v2",
                    current_state_fi: 0.0,
                    window_weighted_fi: 0.0,
                },
            },
        );
    }
    let start_week = calendar_week(start, start_day);
    let end_week = calendar_week(end, start_day);
    let window_rows: Vec<(i64, &WeekFi)> = (start_week..=end_week)
        .filter_map(|week| weekly.get(&week).map(|row| (week, row)))
        .collect();
    let Some((_, latest)) = window_rows.last().copied() else {
        return Computed::insufficient("No data in selected window");
    };
    let half_life = clamp(window_week_count as f64 / 2.0, 1.0, 4.0);
    let (mut weighted_sum, mut weight_total) = (0.0, 0.0);
    for (week, row) in &window_rows {
        let weight = (-(2.0_f64.ln()) * (end_week - week) as f64 / half_life).exp();
        weighted_sum += row.score * weight;
        weight_total += weight;
    }
    let final_fi = if weight_total > 0.0 {
        weighted_sum / weight_total
    } else {
        0.0
    };
    let window_mean =
        window_rows.iter().map(|(_, row)| row.score).sum::<f64>() / window_rows.len() as f64;
    let window_peak = window_rows
        .iter()
        .map(|(_, row)| row.score)
        .fold(f64::MIN, f64::max);
    let latest_fi = latest.score;
    let mut components = latest.components.clone();
    components.latest_week_fi = round(latest_fi, 3);
    components.window_mean_fi = round(window_mean, 3);
    components.window_peak_fi = round(window_peak, 3);
    components.fatigue_window_weeks = window_week_count;
    components.fatigue_context_weeks_used = weekly_dims
        .keys()
        .filter(|week| **week < start_week)
        .count();
    components.fatigue_context_confidence = latest.confidence;
    components.current_state_fi = round(latest_fi, 3);
    components.window_weighted_fi = round(final_fi, 3);
    let score = round(latest_fi, 3);
    let mut flags = Vec::new();
    if components.failed_compound_ratio > 0.15 {
        flags.push("failed_sets_spike");
    }
    if components.composite_spike > 0.20 {
        flags.push("volume_spike");
    }
    if components.rpe_stress > 0.50 {
        flags.push("high_rpe_stress");
    }
    if components.overload_streak >= 0.75 {
        flags.push("sustained_overload");
    }
    if components.chronic_load_stress >= 0.65 {
        flags.push("high_chronic_load");
    }
    if components.reservoir_max_dimension_stress >= 0.75 {
        flags.push("localized_fatigue_high");
    }
    if components.intensity_density_stress >= 0.65 {
        flags.push("high_intensity_density");
    }
    if components.monotony_stress >= 0.65 {
        flags.push("high_monotony_strain");
    }
    if score >= 0.65 {
        flags.push("overreaching_risk");
    } else if score >= 0.45 {
        flags.push("fatigue_high");
    }
    Computed::Ready(FatigueIndex {
        score,
        components,
        flags,
    })
}
