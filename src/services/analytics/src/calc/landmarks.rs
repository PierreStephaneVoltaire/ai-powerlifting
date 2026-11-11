use std::collections::BTreeMap;

use chrono::NaiveDate;
use serde::Serialize;

use super::weeks::infer_program_start;
use super::{Computed, Env, Sessions, deload, e1rm, fatigue, readiness};
use crate::model::{Lift, Maxes, ProgramData, Session};
use crate::util::round;

const MIN_WEEKS: usize = 12;

#[derive(Debug, Serialize)]
pub struct Landmark {
    pub mv: Option<f64>,
    pub mev: Option<f64>,
    pub mav: Option<f64>,
    pub mrv: Option<f64>,
    pub confidence: &'static str,
    pub history_weeks_used: usize,
}

#[derive(Debug, Serialize)]
pub struct Landmarks {
    pub squat: Computed<Landmark>,
    pub bench: Computed<Landmark>,
    pub deadlift: Computed<Landmark>,
}

struct Delta {
    sets: f64,
    delta: f64,
    next_fi: Option<f64>,
    next_readiness: Option<f64>,
}

struct Summary {
    avg_sets: f64,
    avg_delta: f64,
    prob_negative: f64,
    median_fi: Option<f64>,
    median_readiness: Option<f64>,
    count: usize,
}

fn lacking(lift: Lift) -> Computed<Landmark> {
    Computed::insufficient(format!(
        "Need at least {MIN_WEEKS} weeks of {} data",
        lift.key()
    ))
}

fn upper_median(mut values: Vec<f64>) -> Option<f64> {
    if values.is_empty() {
        return None;
    }
    values.sort_by(f64::total_cmp);
    Some(values[values.len() / 2])
}

fn synonyms(lift: Lift) -> &'static [&'static str] {
    match lift {
        Lift::Squat => &["squat"],
        Lift::Bench => &["bench press", "bench"],
        Lift::Deadlift => &["deadlift"],
    }
}

pub fn compute(
    env: Env<'_>,
    sessions: Sessions<'_>,
    maxes: &Maxes,
    program_start: &str,
    reference: NaiveDate,
) -> Landmarks {
    let eligible: Vec<&Session> = sessions
        .iter()
        .copied()
        .filter(|session| session.completed && session.date.is_some_and(|date| date <= reference))
        .collect();
    if eligible.is_empty() {
        return Landmarks {
            squat: lacking(Lift::Squat),
            bench: lacking(Lift::Bench),
            deadlift: lacking(Lift::Deadlift),
        };
    }
    let owned_start;
    let program_start = if program_start.is_empty() {
        owned_start = infer_program_start(sessions);
        owned_start.as_str()
    } else {
        program_start
    };
    let estimated;
    let maxes = if maxes.is_empty() {
        estimated = e1rm::from_sessions_default(&eligible, reference);
        &estimated
    } else {
        maxes
    };
    let excluded: Vec<i64> = deload::detect(&eligible, program_start)
        .iter()
        .filter(|load| load.excluded())
        .map(|load| load.week)
        .collect();
    Landmarks {
        squat: lift_landmark(env, &eligible, Lift::Squat, maxes, program_start, &excluded),
        bench: lift_landmark(env, &eligible, Lift::Bench, maxes, program_start, &excluded),
        deadlift: lift_landmark(
            env,
            &eligible,
            Lift::Deadlift,
            maxes,
            program_start,
            &excluded,
        ),
    }
}

fn lift_landmark(
    env: Env<'_>,
    eligible: &[&Session],
    lift: Lift,
    maxes: &Maxes,
    program_start: &str,
    excluded: &[i64],
) -> Computed<Landmark> {
    let names = synonyms(lift);
    let mut by_week: BTreeMap<i64, Vec<&Session>> = BTreeMap::new();
    for session in eligible.iter().copied().filter(|session| {
        session
            .exercises
            .iter()
            .any(|exercise| names.contains(&exercise.key.as_str()))
    }) {
        if let Some(week) = session.week(program_start) {
            by_week.entry(week).or_default().push(session);
        }
    }
    if by_week.is_empty() {
        return lacking(lift);
    }
    let mut weeks: BTreeMap<i64, (f64, Option<f64>)> = BTreeMap::new();
    for (week, members) in &by_week {
        if excluded.contains(week) {
            continue;
        }
        let sets: f64 = members
            .iter()
            .flat_map(|session| &session.exercises)
            .filter(|exercise| {
                names.contains(&exercise.key.as_str()) && exercise.kg > 0.0 && exercise.reps > 0.0
            })
            .map(|exercise| exercise.executed_sets())
            .sum();
        weeks.insert(*week, (sets, deload::best_primary_e1rm(members)));
    }
    let history_weeks = weeks.len();
    if history_weeks < MIN_WEEKS {
        return lacking(lift);
    }
    let mut records: Vec<Delta> = Vec::new();
    let mut previous: Option<f64> = None;
    for (week, (sets, best)) in &weeks {
        let Some(best) = best else {
            previous = None;
            continue;
        };
        let delta = previous.map(|previous| best - previous);
        let (mut next_fi, mut next_readiness) = (None, None);
        if let Some(next) = by_week.get(&(week + 1))
            && let Some(reference) = next.iter().filter_map(|session| session.date).max()
        {
            next_fi = fatigue::fatigue_index(
                env,
                next,
                fatigue::FatigueWindow {
                    days: 7,
                    reference: Some(reference),
                    ..Default::default()
                },
                maxes,
                program_start,
            )
            .ready()
            .map(|result| result.score);
            next_readiness = Some(
                readiness::compute(
                    env,
                    next,
                    ProgramData::empty(),
                    program_start,
                    Some(reference),
                )
                .score,
            );
        }
        if let Some(delta) = delta {
            records.push(Delta {
                sets: *sets,
                delta,
                next_fi,
                next_readiness,
            });
        }
        previous = Some(*best);
    }
    if records.is_empty() {
        return lacking(lift);
    }
    let mut bins: Vec<(i64, Vec<&Delta>)> = Vec::new();
    for record in &records {
        let key = ((record.sets / 2.0).floor() * 2.0) as i64;
        match bins.iter_mut().find(|(bin, _)| *bin == key) {
            Some((_, rows)) => rows.push(record),
            None => bins.push((key, vec![record])),
        }
    }
    let mut summaries: Vec<Summary> = bins
        .iter()
        .map(|(_, rows)| {
            let count = rows.len();
            let deltas: Vec<f64> = rows.iter().map(|row| row.delta).collect();
            Summary {
                avg_sets: round(
                    rows.iter().map(|row| row.sets).sum::<f64>() / count as f64,
                    1,
                ),
                avg_delta: round(deltas.iter().sum::<f64>() / deltas.len() as f64, 3),
                prob_negative: deltas.iter().filter(|delta| **delta < 0.0).count() as f64
                    / deltas.len() as f64,
                median_fi: upper_median(rows.iter().filter_map(|row| row.next_fi).collect()),
                median_readiness: upper_median(
                    rows.iter().filter_map(|row| row.next_readiness).collect(),
                ),
                count,
            }
        })
        .collect();
    summaries.sort_by(|a, b| a.avg_sets.total_cmp(&b.avg_sets));
    let mv = summaries
        .iter()
        .find(|row| row.avg_delta >= 0.0)
        .map(|row| row.avg_sets);
    let mev = summaries
        .iter()
        .find(|row| row.avg_delta > 0.0)
        .map(|row| row.avg_sets);
    let mav = summaries
        .iter()
        .fold(None::<&Summary>, |best, row| match best {
            Some(best) if best.avg_delta >= row.avg_delta => Some(best),
            _ => Some(row),
        })
        .map(|row| row.avg_sets);
    let mut mrv = summaries
        .iter()
        .find(|row| {
            let flagged = row.median_fi.is_some_and(|fi| fi >= 0.55)
                || row.prob_negative >= 0.60
                || row.median_readiness.is_some_and(|score| score < 60.0);
            row.count >= 3 && flagged
        })
        .map(|row| row.avg_sets);
    if mrv.is_none() {
        let max_count = summaries.iter().map(|row| row.count).max().unwrap_or(0);
        mrv = summaries
            .iter()
            .find(|row| row.count == max_count && row.prob_negative >= 0.60)
            .map(|row| row.avg_sets);
    }
    Computed::Ready(Landmark {
        mv: mv.map(|value| round(value, 1)),
        mev: mev.map(|value| round(value, 1)),
        mav: mav.map(|value| round(value, 1)),
        mrv: mrv.map(|value| round(value, 1)),
        confidence: if history_weeks <= 17 {
            "low"
        } else if history_weeks <= 25 {
            "medium"
        } else {
            "high"
        },
        history_weeks_used: history_weeks,
    })
}
