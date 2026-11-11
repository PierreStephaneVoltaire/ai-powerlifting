use std::collections::{BTreeMap, BTreeSet};

use chrono::NaiveDate;
use serde_json::Value;

use super::types::{
    Bands, CategoryExposure, Deload, DimensionStat, Exposure, Fatigue, LiftExposure, Specificity,
    Spread,
};
use crate::blocks::strength::{LIFTS, canonical_lift};
use crate::calc::{Env, acwr};
use crate::js::round_or_null;
use crate::model::{Maxes, ProgramData, Session};

const HARD_SET_MIN_RPE: f64 = 7.0;
const UNCATEGORIZED: &str = "uncategorized";

#[derive(Default)]
struct Week {
    hard_sets: f64,
    sets: f64,
    tonnage: f64,
    days: BTreeSet<String>,
    rpe_sum: f64,
    rpe_sets: f64,
}

#[derive(Default)]
struct Series {
    weeks: BTreeMap<i64, Week>,
}

impl Series {
    fn add(&mut self, week: i64, session: &Session, sets: f64, tonnage: f64, rpe: Option<f64>) {
        let slot = self.weeks.entry(week).or_default();
        slot.sets += sets;
        slot.tonnage += tonnage;
        if rpe.is_none_or(|value| value >= HARD_SET_MIN_RPE) {
            slot.hard_sets += sets;
        }
        if let Some(value) = rpe {
            slot.rpe_sum += value * sets;
            slot.rpe_sets += sets;
        }
        slot.days.insert(session.date_text.clone());
    }

    fn per_week(&self, pick: impl Fn(&Week) -> f64, training_weeks: f64) -> f64 {
        self.weeks.values().map(pick).sum::<f64>() / training_weeks
    }

    fn avg_rpe(&self) -> Option<f64> {
        let (sum, sets) = self
            .weeks
            .values()
            .fold((0.0, 0.0), |(sum, sets), week| (sum + week.rpe_sum, sets + week.rpe_sets));
        round_or_null((sets > 0.0).then(|| sum / sets), 2)
    }

    fn totals(&self) -> (f64, f64, f64) {
        self.weeks.values().fold((0.0, 0.0, 0.0), |acc, week| {
            (acc.0 + week.sets, acc.1 + week.tonnage, acc.2 + week.days.len() as f64)
        })
    }
}

fn round2(value: f64) -> f64 {
    round_or_null(Some(value), 2).unwrap_or(0.0)
}

fn number(value: Option<&Value>) -> Option<f64> {
    value.and_then(Value::as_f64).filter(|value| value.is_finite())
}

fn spread(rows: &[&Value], key: &str) -> Spread {
    let values: Vec<f64> = rows.iter().filter_map(|row| number(row.get(key))).collect();
    Spread {
        mean: round_or_null(
            (!values.is_empty()).then(|| values.iter().sum::<f64>() / values.len() as f64),
            3,
        ),
        peak: round_or_null(values.iter().copied().reduce(f64::max), 3),
    }
}

fn dimension_stat(weekly: &Value, reduce: impl Fn(&[f64]) -> f64) -> DimensionStat {
    let rows: Vec<&Value> = weekly
        .pointer("/fatigue_dimensions/weekly")
        .and_then(Value::as_object)
        .map(|map| map.values().collect())
        .unwrap_or_default();
    let pick = |key: &str| {
        let values: Vec<f64> = rows.iter().filter_map(|row| number(row.get(key))).collect();
        round_or_null((!values.is_empty()).then(|| reduce(&values)), 1)
    };
    DimensionStat {
        axial: pick("axial"),
        neural: pick("neural"),
        peripheral: pick("peripheral"),
        systemic: pick("systemic"),
    }
}

fn mean(values: &[f64]) -> f64 {
    values.iter().sum::<f64>() / values.len() as f64
}

fn peak(values: &[f64]) -> f64 {
    values.iter().copied().fold(f64::MIN, f64::max)
}

fn maxes_of(weekly: &Value) -> Maxes {
    let lift = |key: &str| number(weekly.pointer(&format!("/current_maxes/{key}")));
    Maxes {
        squat: lift("squat"),
        bench: lift("bench"),
        deadlift: lift("deadlift"),
    }
}

fn acwr_peak(env: Env<'_>, program: &ProgramData, weekly: &Value) -> Option<f64> {
    let completed: Vec<&Session> = program.sessions.iter().filter(|s| s.completed).collect();
    let start = program.meta.program_start();
    let maxes = maxes_of(weekly);
    let mut last_day: BTreeMap<i64, NaiveDate> = BTreeMap::new();
    for session in &completed {
        if let (Some(week), Some(date)) = (session.week_number, session.date) {
            let slot = last_day.entry(week).or_insert(date);
            *slot = (*slot).max(date);
        }
    }
    last_day
        .into_iter()
        .filter_map(|(week, date)| {
            acwr::compute(
                env,
                &completed,
                &start,
                &maxes,
                Some(&program.phases),
                Some(week),
                Some(date),
            )
            .into_ready()
            .and_then(|value| value.composite)
        })
        .reduce(f64::max)
}

fn deload(weekly: &Value, week_start: i64, week_count: i64) -> Deload {
    let list = |key: &str| -> Vec<i64> {
        weekly
            .pointer(&format!("/deload_info/{key}"))
            .and_then(Value::as_array)
            .map(|items| items.iter().filter_map(Value::as_i64).collect())
            .unwrap_or_default()
    };
    let weeks = list("deload_weeks");
    let positions: Vec<f64> = weeks
        .iter()
        .map(|week| round2((*week - week_start) as f64 / week_count.max(1) as f64))
        .collect();
    let placement = match positions.first() {
        None => "none",
        Some(position) if *position < 1.0 / 3.0 => "early",
        Some(position) if *position < 2.0 / 3.0 => "mid",
        Some(_) => "late",
    };
    Deload {
        count: weeks.len() as i64,
        per_10_weeks: round2(weeks.len() as f64 / week_count.max(1) as f64 * 10.0),
        break_weeks: list("break_weeks"),
        positions,
        placement: placement.to_owned(),
        weeks,
    }
}

fn bands(weekly: &Value, lift: &str) -> Bands {
    let pct = |band: &str| {
        number(weekly.pointer(&format!("/ri_distribution/per_lift/{lift}/{band}/pct")))
    };
    Bands {
        heavy_pct: pct("heavy"),
        moderate_pct: pct("moderate"),
        light_pct: pct("light"),
    }
}

pub fn build(
    env: Env<'_>,
    program: &ProgramData,
    weekly: &Value,
    week_start: i64,
    week_count: i64,
) -> Exposure {
    let mut lifts: BTreeMap<&'static str, Series> = BTreeMap::new();
    let mut categories: BTreeMap<String, Series> = BTreeMap::new();
    let mut training_weeks: BTreeSet<i64> = BTreeSet::new();
    let mut days: BTreeSet<&str> = BTreeSet::new();
    let mut all = Series::default();
    for session in program.sessions.iter().filter(|session| session.completed) {
        let Some(week) = session.week_number.filter(|week| *week > 0) else {
            continue;
        };
        training_weeks.insert(week);
        days.insert(session.date_text.as_str());
        for exercise in &session.exercises {
            let sets = exercise.executed_sets();
            if sets <= 0.0 {
                continue;
            }
            let tonnage = exercise.executed_volume();
            let rpe = exercise.rpe.or(session.session_rpe);
            all.add(week, session, sets, tonnage, rpe);
            match canonical_lift(&exercise.name) {
                Some(lift) => lifts.entry(lift).or_default().add(week, session, sets, tonnage, rpe),
                None => {
                    let category = env.glossary.category(&exercise.key);
                    let category = if category.is_empty() { UNCATEGORIZED } else { category };
                    categories
                        .entry(category.to_owned())
                        .or_default()
                        .add(week, session, sets, tonnage, rpe);
                }
            }
        }
    }
    let weeks = training_weeks.len().max(1) as f64;
    let summarize = |series: &Series| {
        let (sets, _, day_count) = series.totals();
        (
            round2(series.per_week(|week| week.hard_sets, weeks)),
            round2(series.per_week(|week| week.tonnage, weeks)),
            round2(day_count / weeks),
            series.avg_rpe(),
            sets,
        )
    };
    let lift_map = LIFTS
        .iter()
        .map(|lift| {
            let (hard, tonnage, frequency, rpe, sets) =
                lifts.get(lift).map_or((0.0, 0.0, 0.0, None, 0.0), summarize);
            let peak_inol = weekly
                .pointer(&format!("/inol/per_lift_per_week/{lift}"))
                .and_then(Value::as_object)
                .and_then(|map| map.values().filter_map(Value::as_f64).reduce(f64::max));
            (
                (*lift).to_owned(),
                LiftExposure {
                    weekly_hard_sets: hard,
                    weekly_tonnage_kg: tonnage,
                    weekly_frequency: frequency,
                    avg_rpe: rpe,
                    avg_inol: number(weekly.pointer(&format!("/inol/avg_inol/{lift}"))),
                    peak_inol: round_or_null(peak_inol, 2),
                    total_sets: sets,
                    intensity_bands: bands(weekly, lift),
                },
            )
        })
        .collect();
    let accessories = categories
        .iter()
        .map(|(name, series)| {
            let (hard, tonnage, frequency, rpe, sets) = summarize(series);
            (
                name.clone(),
                CategoryExposure {
                    weekly_hard_sets: hard,
                    weekly_tonnage_kg: tonnage,
                    weekly_frequency: frequency,
                    avg_rpe: rpe,
                    total_sets: sets,
                },
            )
        })
        .collect();
    let monotony_rows: Vec<&Value> = weekly
        .pointer("/monotony_strain/weekly")
        .and_then(Value::as_array)
        .map(|rows| rows.iter().collect())
        .unwrap_or_default();
    Exposure {
        training_weeks: training_weeks.len() as i64,
        training_days_per_week: (!training_weeks.is_empty())
            .then(|| round2(days.len() as f64 / weeks)),
        weekly_hard_sets: round2(all.per_week(|week| week.hard_sets, weeks)),
        weekly_tonnage_kg: round2(all.per_week(|week| week.tonnage, weeks)),
        lifts: lift_map,
        accessories,
        fatigue: Fatigue {
            index: number(weekly.get("fatigue_index")),
            dimension_mean: dimension_stat(weekly, mean),
            dimension_peak: dimension_stat(weekly, peak),
        },
        acwr_peak: round_or_null(acwr_peak(env, program, weekly), 3),
        acwr_composite: number(weekly.pointer("/acwr/composite")),
        monotony: spread(&monotony_rows, "monotony"),
        strain: spread(&monotony_rows, "strain"),
        compliance_pct: number(weekly.pointer("/compliance/pct")),
        deload: deload(weekly, week_start, week_count),
        specificity: Specificity {
            broad: number(weekly.pointer("/specificity_ratio/broad")),
            narrow: number(weekly.pointer("/specificity_ratio/narrow")),
        },
    }
}
