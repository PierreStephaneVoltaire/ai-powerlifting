use std::collections::{BTreeMap, HashMap};

use chrono::{Duration, NaiveDate};
use serde::Serialize;

use super::weeks::week_start_for;
use super::{Computed, Dims, Env, Sessions, e1rm, fatigue};
use crate::model::{Lift, Maxes, Session};
use crate::util::{median, ols_slope, parse_date, population_sd, round};

const CTL_LAMBDA: f64 = 2.0 / 43.0;
const ATL_LAMBDA: f64 = 2.0 / 8.0;
const SEED_DAYS: usize = 14;
const MONOTONY_RELATIVE_SD_FLOOR: f64 = 0.10;
const MONOTONY_ABSOLUTE_SD_FLOOR: f64 = 1.0;
const MONOTONY_DISPLAY_CAP: f64 = 7.0;
const DECOUPLING_WINDOW: usize = 3;

fn resolved_maxes<'a>(
    env: Env<'_>,
    sessions: Sessions<'_>,
    maxes: &'a Maxes,
    storage: &'a mut Maxes,
) -> &'a Maxes {
    if maxes.is_empty() {
        *storage = e1rm::from_sessions_default(sessions, env.today);
        storage
    } else {
        maxes
    }
}

pub fn daily_baselines(baseline: &fatigue::ChronicBaseline) -> Dims {
    baseline.weekly.map(|weekly| (weekly / 7.0).max(1.0))
}

pub fn normalized_load(dims: Dims, baselines: Dims) -> f64 {
    100.0
        * (0.30 * dims.axial / baselines.axial.max(1.0)
            + 0.30 * dims.neural / baselines.neural.max(1.0)
            + 0.25 * dims.peripheral / baselines.peripheral.max(1.0)
            + 0.15 * dims.systemic / baselines.systemic.max(1.0))
}

pub fn tsb_label(tsb: f64, planned_overreach: bool) -> &'static str {
    if tsb < -30.0 {
        "Deep overload"
    } else if tsb < -10.0 {
        if planned_overreach {
            "Planned overreach"
        } else {
            "Productive fatigue"
        }
    } else if tsb <= 5.0 {
        "Building"
    } else if tsb <= 15.0 {
        "Peaking window"
    } else {
        "Detraining risk"
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct BanisterPoint {
    pub date: String,
    pub ctl: f64,
    pub atl: f64,
    pub tsb: f64,
}

#[derive(Debug, Serialize)]
pub struct Banister {
    pub ctl_today: f64,
    pub atl_today: f64,
    pub tsb_today: f64,
    pub tsb_label: &'static str,
    pub series: Vec<BanisterPoint>,
    pub load_baselines: Dims,
    pub baseline_weeks_used: usize,
    pub model: &'static str,
}

pub fn banister_ffm(
    env: Env<'_>,
    sessions: Sessions<'_>,
    program_start: &str,
    maxes: &Maxes,
    reference: Option<NaiveDate>,
) -> Computed<Banister> {
    let mut storage = Maxes::default();
    let maxes = resolved_maxes(env, sessions, maxes, &mut storage);
    let daily = fatigue::daily_by_dimension(env, sessions, maxes);
    let none = || Computed::insufficient("No completed training load available for Banister FFM");
    let Some(first) = daily.keys().next().copied() else {
        return none();
    };
    let last = reference.unwrap_or(env.today);
    let chronic = fatigue::chronic_baseline(env, sessions, maxes, last, program_start);
    let baselines = daily_baselines(&chronic);
    let mut loads: Vec<(NaiveDate, f64)> = Vec::new();
    let mut day = first;
    while day <= last {
        let dims = daily.get(&day).copied().unwrap_or_default();
        loads.push((day, normalized_load(dims, baselines).max(0.0)));
        day += Duration::days(1);
    }
    if !loads.iter().any(|(_, load)| *load != 0.0) {
        return none();
    }
    let seed_days = SEED_DAYS.min(loads.len());
    let seed = loads[..seed_days].iter().map(|(_, load)| load).sum::<f64>() / seed_days as f64;
    let (mut ctl, mut atl) = (seed, seed);
    let series: Vec<BanisterPoint> = loads
        .iter()
        .enumerate()
        .map(|(index, (date, load))| {
            if index > 0 {
                ctl = CTL_LAMBDA * load + (1.0 - CTL_LAMBDA) * ctl;
                atl = ATL_LAMBDA * load + (1.0 - ATL_LAMBDA) * atl;
            }
            BanisterPoint {
                date: date.to_string(),
                ctl: round(ctl, 3),
                atl: round(atl, 3),
                tsb: round(ctl - atl, 3),
            }
        })
        .collect();
    let current = series[series.len() - 1].clone();
    Computed::Ready(Banister {
        ctl_today: current.ctl,
        atl_today: current.atl,
        tsb_today: current.tsb,
        tsb_label: tsb_label(current.tsb, false),
        series,
        load_baselines: baselines.map(|value| round(value, 3)),
        baseline_weeks_used: chronic.weeks_used,
        model: "normalized_dimension_banister_v3",
    })
}

pub struct DailyLoad {
    pub date: NaiveDate,
    pub load: f64,
}

pub fn composite_daily_loads(
    env: Env<'_>,
    sessions: Sessions<'_>,
    program_start: &str,
    maxes: &Maxes,
    reference: Option<NaiveDate>,
) -> (Vec<DailyLoad>, Option<NaiveDate>) {
    let daily = fatigue::daily_by_dimension(env, sessions, maxes);
    let configured = parse_date(program_start).filter(|_| !program_start.is_empty());
    let Some(first) = daily.keys().next().copied() else {
        return (Vec::new(), configured);
    };
    let start = configured.unwrap_or(first);
    let end = reference.unwrap_or(env.today);
    if end < start {
        return (Vec::new(), Some(start));
    }
    let mut series = Vec::new();
    let mut day = start;
    while day <= end {
        let dims = daily.get(&day).copied().unwrap_or_default();
        series.push(DailyLoad {
            date: day,
            load: dims.weighted(),
        });
        day += Duration::days(1);
    }
    (series, Some(start))
}

#[derive(Debug, Clone, Serialize)]
pub struct MonotonyWeek {
    pub week_start: String,
    pub monotony: f64,
    pub monotony_raw: f64,
    pub strain: f64,
    pub nonzero_training_days: usize,
    pub days_observed: usize,
    pub partial: bool,
    pub strain_index: Option<f64>,
    pub flags: Vec<&'static str>,
}

#[derive(Debug, Serialize)]
pub struct Latest {
    pub monotony: f64,
    pub monotony_raw: f64,
    pub strain: f64,
    pub strain_index: Option<f64>,
    pub nonzero_training_days: usize,
    pub partial: bool,
}

#[derive(Debug, Serialize)]
pub struct MonotonyStrain {
    pub weekly: Vec<MonotonyWeek>,
    #[serde(flatten)]
    pub latest: Option<Latest>,
}

pub fn monotony_strain(
    env: Env<'_>,
    sessions: Sessions<'_>,
    program_start: &str,
    maxes: &Maxes,
    reference: Option<NaiveDate>,
    window_start: Option<NaiveDate>,
) -> MonotonyStrain {
    let empty = || MonotonyStrain {
        weekly: Vec::new(),
        latest: None,
    };
    let mut storage = Maxes::default();
    let maxes = resolved_maxes(env, sessions, maxes, &mut storage);
    let daily = fatigue::daily_by_dimension(env, sessions, maxes);
    let Some(first) = daily.keys().next().copied() else {
        return empty();
    };
    let last = reference.unwrap_or(env.today);
    let Some(anchor) = fatigue::week_anchor(program_start, sessions) else {
        return empty();
    };
    if last < first {
        return empty();
    }
    let baselines = daily_baselines(&fatigue::chronic_baseline(
        env,
        sessions,
        maxes,
        last,
        program_start,
    ));
    let mut by_week: BTreeMap<NaiveDate, Vec<f64>> = BTreeMap::new();
    let mut day = first;
    while day <= last {
        let dims = daily.get(&day).copied().unwrap_or_default();
        by_week
            .entry(week_start_for(day, anchor))
            .or_default()
            .push(normalized_load(dims, baselines).max(0.0));
        day += Duration::days(1);
    }
    let mut weekly: Vec<(NaiveDate, MonotonyWeek)> = by_week
        .iter()
        .map(|(week_start, loads)| {
            let total: f64 = loads.iter().sum();
            let mean = total / loads.len() as f64;
            let sd = population_sd(loads);
            let denominator = sd
                .max(mean * MONOTONY_RELATIVE_SD_FLOOR)
                .max(MONOTONY_ABSOLUTE_SD_FLOOR);
            let raw = if mean > 0.0 { mean / denominator } else { 0.0 };
            let monotony = raw.min(MONOTONY_DISPLAY_CAP);
            (
                *week_start,
                MonotonyWeek {
                    week_start: week_start.to_string(),
                    monotony: round(monotony, 3),
                    monotony_raw: round(raw, 3),
                    strain: round(total * monotony, 3),
                    nonzero_training_days: loads.iter().filter(|load| **load > 0.0).count(),
                    days_observed: loads.len(),
                    partial: loads.len() < 7,
                    strain_index: None,
                    flags: Vec::new(),
                },
            )
        })
        .collect();
    for index in 0..weekly.len() {
        let previous: Vec<f64> = weekly[index.saturating_sub(4)..index]
            .iter()
            .map(|(_, row)| row.strain)
            .collect();
        let row = &mut weekly[index].1;
        if row.nonzero_training_days >= 3 && row.monotony > 2.0 {
            row.flags.push("high_monotony");
        }
        if !previous.is_empty() {
            let center = median(&previous);
            let index_value = (center > 0.0).then(|| row.strain / center);
            row.strain_index = index_value.map(|value| round(value, 3));
            if index_value.is_some_and(|value| value > 1.5) {
                row.flags.push("strain_spike");
            }
        }
    }
    let weekly: Vec<MonotonyWeek> = weekly
        .into_iter()
        .filter(|(week_start, _)| {
            window_start.is_none_or(|start| *week_start + Duration::days(6) >= start)
        })
        .map(|(_, row)| row)
        .collect();
    let latest = weekly.last().map(|row| Latest {
        monotony: row.monotony,
        monotony_raw: row.monotony_raw,
        strain: row.strain,
        strain_index: row.strain_index,
        nonzero_training_days: row.nonzero_training_days,
        partial: row.partial,
    });
    MonotonyStrain { weekly, latest }
}

fn weekly_sbd_total(sessions: &[&Session]) -> Option<f64> {
    let mut best: HashMap<Lift, f64> = HashMap::new();
    for session in sessions {
        for exercise in &session.exercises {
            let Some(lift) = Lift::from_name(&exercise.key) else {
                continue;
            };
            if exercise.kg <= 0.0 || exercise.reps_int() <= 0 {
                continue;
            }
            if let Some(value) =
                e1rm::estimate(exercise.kg, exercise.reps_int(), session.session_rpe)
            {
                let slot = best.entry(lift).or_insert(0.0);
                *slot = slot.max(value);
            }
        }
    }
    (!best.is_empty()).then(|| Lift::ALL.iter().filter_map(|lift| best.get(lift)).sum())
}

#[derive(Debug, Clone, Serialize)]
pub struct DecouplingPoint {
    pub week_start: String,
    pub decoupling: f64,
    pub e1rm_slope_pct_per_week: f64,
    pub fi_slope_pct_points_per_week: f64,
}

#[derive(Debug, Serialize)]
pub struct Decoupling {
    pub current: DecouplingPoint,
    pub series: Vec<DecouplingPoint>,
    pub flags: Vec<&'static str>,
}

pub fn decoupling(
    env: Env<'_>,
    sessions: Sessions<'_>,
    program_start: &str,
    maxes: &Maxes,
    reference: Option<NaiveDate>,
) -> Computed<Decoupling> {
    let mut storage = Maxes::default();
    let maxes = resolved_maxes(env, sessions, maxes, &mut storage);
    let (series, start) = composite_daily_loads(env, sessions, program_start, maxes, reference);
    let Some(start) = start.filter(|_| !series.is_empty()) else {
        return Computed::insufficient("No completed training load available for decoupling");
    };
    let reference = reference.unwrap_or(env.today);
    let mut by_week: HashMap<NaiveDate, Vec<&Session>> = HashMap::new();
    for session in sessions.iter().filter(|session| session.completed) {
        let Some(date) = session
            .date
            .filter(|date| *date >= start && *date <= reference)
        else {
            continue;
        };
        by_week
            .entry(week_start_for(date, start))
            .or_default()
            .push(session);
    }
    let mut starts = Vec::new();
    let mut cursor = start;
    while cursor <= reference {
        starts.push(cursor);
        cursor += Duration::days(7);
    }
    if starts.len() < DECOUPLING_WINDOW {
        return Computed::insufficient("Need at least 3 weekly training windows for decoupling");
    }
    let mut index_cache: HashMap<NaiveDate, Option<f64>> = HashMap::new();
    let mut points: Vec<DecouplingPoint> = Vec::new();
    for index in (DECOUPLING_WINDOW - 1)..starts.len() {
        let window = &starts[index + 1 - DECOUPLING_WINDOW..=index];
        let (mut e1rms, mut indices) = (Vec::new(), Vec::new());
        for week_start in window {
            let members = by_week.get(week_start).map_or(&[][..], Vec::as_slice);
            let Some(total) = weekly_sbd_total(members) else {
                e1rms.clear();
                indices.clear();
                break;
            };
            let week_end = std::cmp::min(*week_start + Duration::days(6), reference);
            let score = *index_cache.entry(week_end).or_insert_with(|| {
                fatigue::fatigue_index(
                    env,
                    sessions,
                    fatigue::FatigueWindow {
                        days: 14,
                        reference: Some(week_end),
                        ..Default::default()
                    },
                    maxes,
                    program_start,
                )
                .ready()
                .map(|result| result.score)
            });
            let Some(score) = score else {
                e1rms.clear();
                indices.clear();
                break;
            };
            e1rms.push(total);
            indices.push(score);
        }
        if e1rms.len() != DECOUPLING_WINDOW || indices.len() != DECOUPLING_WINDOW {
            continue;
        }
        let xs = [0.0, 1.0, 2.0];
        let e1rm_slope = ols_slope(&xs, &e1rms);
        let fi_slope = ols_slope(&xs, &indices);
        let baseline = if e1rms[0].abs() > 1e-12 {
            e1rms[0]
        } else {
            1e-12
        };
        let e1rm_pct = round(e1rm_slope / baseline * 100.0, 3);
        let fi_points = round(fi_slope * 100.0, 3);
        points.push(DecouplingPoint {
            week_start: window[0].to_string(),
            decoupling: round(e1rm_pct - fi_points, 3),
            e1rm_slope_pct_per_week: e1rm_pct,
            fi_slope_pct_points_per_week: fi_points,
        });
    }
    let Some(current) = points.last().cloned() else {
        return Computed::insufficient("No qualifying 3-week windows for decoupling");
    };
    let mut flags = Vec::new();
    if points.len() >= 3
        && points[points.len() - 3..]
            .iter()
            .all(|point| point.decoupling < 0.0)
    {
        flags.push("decoupling_fatigue_dominant");
    }
    Computed::Ready(Decoupling {
        current,
        series: points,
        flags,
    })
}
