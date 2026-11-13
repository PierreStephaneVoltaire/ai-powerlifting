use std::collections::{BTreeMap, BTreeSet, HashMap};

use chrono::{Duration, NaiveDate};

use crate::calc::{Dims, Env, e1rm, fatigue, muscle_volume};
use crate::model::{Exercise, Lift, Maxes, NARROW_TRANSFER, Session};
use crate::proto::analytics::{
    DriverStat, ExerciseProfile, ExerciseWeek, FatigueDims, FatigueWeek, LiftSession,
    LiftTransferWeights, MuscleLandmark, MuscleWeek,
};
use crate::util::{mean, median, round, spearman};

const MAX_EXERCISES: usize = 20;
const MIN_TRANSFER: f64 = 0.2;
const HIGH_LOAD_RATIO: f64 = 1.25;
const PRIOR_DAYS: i64 = 2;
const TRAILING_SESSIONS: usize = 3;
const MIN_PAIRS: usize = 4;
const DIMENSIONS: [&str; 4] = ["axial", "neural", "peripheral", "systemic"];

pub struct Input<'a> {
    pub env: Env<'a>,
    pub sessions: &'a [Session],
    pub cutoff: &'a str,
    pub program_start: &'a str,
    pub maxes: Maxes,
    pub weekly_e1rm: &'a BTreeMap<i64, [Option<f64>; 3]>,
}

#[derive(Debug, Default)]
pub struct Drivers {
    pub exercise_weeks: Vec<ExerciseWeek>,
    pub exercises: Vec<ExerciseProfile>,
    pub muscle_weeks: Vec<MuscleWeek>,
    pub muscle_landmarks: Vec<MuscleLandmark>,
    pub fatigue_weeks: Vec<FatigueWeek>,
    pub lift_sessions: Vec<LiftSession>,
    pub driver_stats: Vec<DriverStat>,
}

#[derive(Default)]
struct Dose {
    sets: f64,
    reps: f64,
    volume: f64,
    sessions: BTreeSet<usize>,
    intensity_sets: f64,
    intensity_sum: f64,
    rpe_count: f64,
    rpe_sum: f64,
}

struct LiftRow {
    lift: Lift,
    dims: Dims,
    row: LiftSession,
}

fn week_of(week: i64) -> i32 {
    i32::try_from(week).unwrap_or(i32::MAX)
}

fn fatigue_dims(dims: Dims, digits: usize) -> FatigueDims {
    FatigueDims {
        axial: round(dims.axial, digits),
        neural: round(dims.neural, digits),
        peripheral: round(dims.peripheral, digits),
        systemic: round(dims.systemic, digits),
    }
}

fn ratio(dims: Dims, base: Dims) -> Dims {
    let (values, bases) = (dims.each(), base.each());
    Dims::from_each(std::array::from_fn(|index| values[index] / bases[index]))
}

fn typical_daily(daily: &BTreeMap<NaiveDate, Dims>) -> Dims {
    let center = |index: usize| {
        let mut values: Vec<f64> = daily
            .values()
            .map(|dims| dims.each()[index])
            .filter(|value| *value > 0.0)
            .collect();
        values.sort_by(f64::total_cmp);
        if values.is_empty() {
            1.0
        } else {
            median(&values).max(1.0)
        }
    };
    Dims::from_each(std::array::from_fn(center))
}

fn reference_max(env: Env<'_>, maxes: &Maxes, key: &str) -> Option<f64> {
    maxes
        .by_name(key)
        .or_else(|| env.glossary.entry(key).and_then(|entry| entry.e1rm))
        .filter(|max| *max > 0.0)
}

fn estimate(exercise: &Exercise, session_rpe: Option<f64>) -> Option<f64> {
    let (kg, reps) = (exercise.kg, exercise.reps_int());
    if kg <= 0.0 || reps <= 0 {
        return None;
    }
    e1rm::estimate(kg, reps, exercise.rpe.or(session_rpe)).or_else(|| {
        Some(if exercise.reps < 30.0 {
            kg * (1.0 + exercise.reps / 30.0)
        } else {
            kg
        })
    })
}

fn pairs_for(
    weekly_e1rm: &BTreeMap<i64, [Option<f64>; 3]>,
    lift: Lift,
    sets_of: impl Fn(i64) -> f64,
) -> (Vec<f64>, Vec<f64>) {
    let slot = lift as usize;
    let mut xs = Vec::new();
    let mut ys = Vec::new();
    for (week, lifts) in weekly_e1rm {
        let (Some(now), Some(next)) = (
            lifts[slot],
            weekly_e1rm.get(&(week + 1)).and_then(|next| next[slot]),
        ) else {
            continue;
        };
        xs.push(sets_of(*week));
        ys.push(next - now);
    }
    (xs, ys)
}

fn rho_stat(
    driver_type: &str,
    driver: &str,
    lift: Lift,
    xs: &[f64],
    ys: &[f64],
) -> Option<DriverStat> {
    if xs.len() < MIN_PAIRS {
        return None;
    }
    let rho = spearman(xs, ys)?;
    Some(DriverStat {
        driver_type: driver_type.to_owned(),
        driver: driver.to_owned(),
        lift: lift.key().to_owned(),
        rho: Some(round(rho, 2)),
        n: i32::try_from(xs.len()).unwrap_or(i32::MAX),
        ..DriverStat::default()
    })
}

fn mean_of(values: impl Iterator<Item = f64>, digits: usize) -> Option<f64> {
    let collected: Vec<f64> = values.collect();
    (!collected.is_empty()).then(|| round(mean(&collected), digits))
}

fn sequence_stats(rows: &[LiftRow]) -> Vec<DriverStat> {
    let mut stats = Vec::new();
    for lift in Lift::ALL {
        let of_lift: Vec<&LiftRow> = rows.iter().filter(|row| row.lift == lift).collect();
        for (index, dimension) in DIMENSIONS.iter().enumerate() {
            let (high, low): (Vec<&LiftRow>, Vec<&LiftRow>) = of_lift
                .iter()
                .partition(|row| row.dims.each()[index] >= HIGH_LOAD_RATIO);
            if high.is_empty() || low.is_empty() {
                continue;
            }
            let residual = |group: &[&LiftRow]| {
                mean_of(group.iter().filter_map(|row| row.row.e1rm_residual_pct), 2)
            };
            let rpe =
                |group: &[&LiftRow]| mean_of(group.iter().filter_map(|row| row.row.avg_rpe), 2);
            stats.push(DriverStat {
                driver_type: "sequence".to_owned(),
                driver: (*dimension).to_owned(),
                lift: lift.key().to_owned(),
                n_high: i32::try_from(high.len()).unwrap_or(i32::MAX),
                n_low: i32::try_from(low.len()).unwrap_or(i32::MAX),
                mean_residual_pct_high: residual(&high),
                mean_residual_pct_low: residual(&low),
                mean_rpe_high: rpe(&high),
                mean_rpe_low: rpe(&low),
                ..DriverStat::default()
            });
        }
    }
    stats
}

pub fn build(input: Input<'_>) -> Drivers {
    let Input {
        env,
        sessions,
        cutoff,
        program_start,
        maxes,
        weekly_e1rm,
    } = input;
    let mut completed: Vec<&Session> = sessions
        .iter()
        .filter(|session| {
            session.completed
                && session.date_text.as_str() >= cutoff
                && session.week_number.is_some_and(|week| week > 0)
        })
        .collect();
    completed.sort_by(|a, b| a.date_text.cmp(&b.date_text));
    if completed.is_empty() {
        return Drivers::default();
    }

    let mut names: BTreeMap<String, String> = BTreeMap::new();
    let mut transferred: BTreeMap<String, f64> = BTreeMap::new();
    for exercise in completed.iter().flat_map(|session| &session.exercises) {
        let sets = exercise.executed_sets();
        if sets <= 0.0 {
            continue;
        }
        let transfer = env.glossary.transfer(&exercise.key);
        names
            .entry(exercise.key.clone())
            .or_insert_with(|| exercise.name.trim().to_owned());
        *transferred.entry(exercise.key.clone()).or_default() +=
            sets * (transfer.squat + transfer.bench + transfer.deadlift);
    }
    let mut accessories: Vec<(&String, &f64)> = transferred
        .iter()
        .filter(|(key, weighted)| Lift::from_name(key).is_none() && **weighted > 0.0)
        .collect();
    accessories.sort_by(|a, b| b.1.total_cmp(a.1).then_with(|| a.0.cmp(b.0)));
    let selected: BTreeSet<String> = transferred
        .keys()
        .filter(|key| Lift::from_name(key).is_some())
        .cloned()
        .chain(
            accessories
                .into_iter()
                .take(MAX_EXERCISES)
                .map(|(key, _)| key.clone()),
        )
        .collect();

    let mut doses: BTreeMap<(i64, String), Dose> = BTreeMap::new();
    let mut muscle_sets: BTreeMap<(i64, String), f64> = BTreeMap::new();
    let mut muscle_by_date: BTreeMap<NaiveDate, BTreeMap<String, f64>> = BTreeMap::new();
    for (index, session) in completed.iter().enumerate() {
        let week = session.week_number.unwrap_or(1);
        for exercise in &session.exercises {
            let sets = exercise.executed_sets();
            if sets <= 0.0 {
                continue;
            }
            if let Some(entry) = env.glossary.entry(&exercise.key) {
                for (muscles, weight) in muscle_volume::tiers(entry).into_iter().take(2) {
                    for muscle in muscles {
                        *muscle_sets.entry((week, muscle.clone())).or_default() += sets * weight;
                        if let Some(date) = session.date {
                            *muscle_by_date
                                .entry(date)
                                .or_default()
                                .entry(muscle.clone())
                                .or_default() += sets * weight;
                        }
                    }
                }
            }
            if !selected.contains(&exercise.key) {
                continue;
            }
            let dose = doses.entry((week, exercise.key.clone())).or_default();
            dose.sets += sets;
            dose.reps += sets * exercise.reps;
            dose.volume += exercise.executed_volume();
            dose.sessions.insert(index);
            if let Some(max) = reference_max(env, &maxes, &exercise.key)
                && exercise.kg > 0.0
            {
                dose.intensity_sets += sets;
                dose.intensity_sum += sets * exercise.kg / max * 100.0;
            }
            if let Some(rpe) = exercise
                .rpe
                .or(session.session_rpe)
                .filter(|rpe| *rpe > 0.0)
            {
                dose.rpe_count += 1.0;
                dose.rpe_sum += rpe;
            }
        }
    }

    let exercise_weeks: Vec<ExerciseWeek> = doses
        .iter()
        .map(|((week, key), dose)| ExerciseWeek {
            week_number: week_of(*week),
            exercise: names.get(key).cloned().unwrap_or_else(|| key.clone()),
            sets: round(dose.sets, 1),
            reps: round(dose.reps, 0),
            volume_kg: round(dose.volume, 0),
            sessions: i32::try_from(dose.sessions.len()).unwrap_or(i32::MAX),
            avg_intensity_pct: (dose.intensity_sets > 0.0)
                .then(|| round(dose.intensity_sum / dose.intensity_sets, 1)),
            avg_rpe: (dose.rpe_count > 0.0).then(|| round(dose.rpe_sum / dose.rpe_count, 1)),
        })
        .collect();

    let exercises: Vec<ExerciseProfile> = selected
        .iter()
        .map(|key| {
            let entry = env.glossary.entry(key);
            let transfer = env.glossary.transfer(key);
            let source = if Lift::from_name(key).is_some() {
                "rule"
            } else {
                match entry {
                    Some(entry) if !entry.lift_transfer_source.is_empty() => {
                        entry.lift_transfer_source.as_str()
                    }
                    Some(entry) if entry.lift_transfer.is_some() => "ai",
                    _ => "none",
                }
            };
            ExerciseProfile {
                name: names.get(key).cloned().unwrap_or_else(|| key.clone()),
                primary_muscles: entry
                    .map(|entry| entry.primary_muscles.clone())
                    .unwrap_or_default(),
                secondary_muscles: entry
                    .map(|entry| entry.secondary_muscles.clone())
                    .unwrap_or_default(),
                fatigue: Some(fatigue_dims(fatigue::profile_for(env, key), 2)),
                lift_transfer: Some(LiftTransferWeights {
                    squat: round(transfer.squat, 2),
                    bench: round(transfer.bench, 2),
                    deadlift: round(transfer.deadlift, 2),
                }),
                transfer_source: source.to_owned(),
            }
        })
        .collect();

    let mut movers: BTreeMap<Lift, BTreeSet<String>> = BTreeMap::new();
    for (key, entry) in env.glossary.entries().filter(|(_, entry)| !entry.archived) {
        let transfer = env.glossary.transfer(key);
        for lift in Lift::ALL {
            if transfer.get(lift) >= NARROW_TRANSFER {
                movers
                    .entry(lift)
                    .or_default()
                    .extend(entry.primary_muscles.iter().cloned());
            }
        }
    }
    let trained: BTreeSet<&String> = muscle_sets.keys().map(|(_, muscle)| muscle).collect();
    let muscles: BTreeSet<String> = trained
        .into_iter()
        .cloned()
        .chain(movers.values().flatten().cloned())
        .collect();
    let muscle_weeks: Vec<MuscleWeek> = muscle_sets
        .iter()
        .map(|((week, muscle), sets)| MuscleWeek {
            week_number: week_of(*week),
            muscle: muscle.clone(),
            weighted_sets: round(*sets, 1),
        })
        .collect();
    let muscle_landmarks: Vec<MuscleLandmark> = muscles
        .iter()
        .filter_map(|muscle| {
            muscle_volume::landmark(muscle).map(|landmark| MuscleLandmark {
                muscle: muscle.clone(),
                mev: landmark.mev,
                mav: landmark.mav_high,
                mrv: landmark.mrv,
            })
        })
        .collect();

    let refs: Vec<&Session> = completed.clone();
    let reference = refs
        .iter()
        .filter_map(|session| session.date)
        .max()
        .unwrap_or(env.today);
    let baseline = fatigue::chronic_baseline(env, &refs, &maxes, reference, program_start);
    let fatigue_weeks: Vec<FatigueWeek> =
        fatigue::weekly_by_dimension(env, &refs, program_start, &maxes)
            .into_iter()
            .map(|(week, dims)| FatigueWeek {
                week_number: week_of(week),
                ratio: Some(fatigue_dims(ratio(dims, baseline.weekly), 2)),
            })
            .collect();

    let daily = fatigue::daily_by_dimension(env, &refs, &maxes);
    let typical = typical_daily(&daily);
    let mut best: BTreeMap<Lift, Vec<f64>> = BTreeMap::new();
    let mut lift_rows: Vec<LiftRow> = Vec::new();
    for session in &refs {
        let Some(date) = session.date else {
            continue;
        };
        let window_start = date - Duration::days(PRIOR_DAYS);
        let mut prior = Dims::default();
        for (_, dims) in daily.range(window_start..date) {
            prior.add(*dims, 1.0);
        }
        let prior_ratio = ratio(prior, typical);
        let mut prior_muscles: HashMap<String, f64> = HashMap::new();
        for (_, by_muscle) in muscle_by_date.range(window_start..date) {
            for (muscle, sets) in by_muscle {
                *prior_muscles.entry(muscle.clone()).or_default() += sets;
            }
        }
        let prior_muscles: HashMap<String, f64> = prior_muscles
            .into_iter()
            .filter(|(_, sets)| *sets > 0.0)
            .map(|(muscle, sets)| (muscle, round(sets, 1)))
            .collect();
        for lift in Lift::ALL {
            let performed: Vec<&Exercise> = session
                .exercises
                .iter()
                .filter(|exercise| {
                    Lift::from_name(&exercise.key) == Some(lift) && exercise.executed_sets() > 0.0
                })
                .collect();
            let Some(top) = performed
                .iter()
                .filter_map(|exercise| estimate(exercise, session.session_rpe))
                .max_by(f64::total_cmp)
            else {
                continue;
            };
            let history = best.entry(lift).or_default();
            let trailing = history
                .iter()
                .rev()
                .take(TRAILING_SESSIONS)
                .copied()
                .max_by(f64::total_cmp);
            let rpes: Vec<f64> = performed
                .iter()
                .filter_map(|exercise| exercise.rpe.or(session.session_rpe))
                .filter(|rpe| *rpe > 0.0)
                .collect();
            let row = LiftSession {
                date: session.date_text.clone(),
                lift: lift.key().to_owned(),
                top_e1rm_kg: round(top, 1),
                e1rm_residual_pct: trailing
                    .filter(|best| *best > 0.0)
                    .map(|best| round((top - best) / best * 100.0, 2)),
                avg_rpe: (!rpes.is_empty()).then(|| round(mean(&rpes), 1)),
                prior48h_fatigue: Some(fatigue_dims(prior_ratio, 2)),
                prior48h_muscle_sets: prior_muscles.clone(),
            };
            history.push(top);
            lift_rows.push(LiftRow {
                lift,
                dims: prior_ratio,
                row,
            });
        }
    }

    let mut driver_stats = Vec::new();
    for lift in Lift::ALL {
        for key in &selected {
            if env.glossary.transfer(key).get(lift) < MIN_TRANSFER {
                continue;
            }
            let (xs, ys) = pairs_for(weekly_e1rm, lift, |week| {
                doses
                    .get(&(week, key.clone()))
                    .map_or(0.0, |dose| dose.sets)
            });
            let name = names.get(key).unwrap_or(key);
            driver_stats.extend(rho_stat("exercise", name, lift, &xs, &ys));
        }
        for muscle in movers.get(&lift).into_iter().flatten() {
            let (xs, ys) = pairs_for(weekly_e1rm, lift, |week| {
                muscle_sets
                    .get(&(week, muscle.clone()))
                    .copied()
                    .unwrap_or(0.0)
            });
            driver_stats.extend(rho_stat("muscle", muscle, lift, &xs, &ys));
        }
    }
    driver_stats.extend(sequence_stats(&lift_rows));

    Drivers {
        exercise_weeks,
        exercises,
        muscle_weeks,
        muscle_landmarks,
        fatigue_weeks,
        lift_sessions: lift_rows.into_iter().map(|row| row.row).collect(),
        driver_stats,
    }
}
