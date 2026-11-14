use chrono::{Duration, NaiveDate};

use super::Sessions;
use crate::constants;
use crate::model::{Competition, Lift, Maxes};
use crate::util::int_of;

pub fn estimate(weight: f64, reps: i64, rpe: Option<f64>) -> Option<f64> {
    if !weight.is_finite() || weight <= 0.0 {
        return None;
    }
    let pct = match rpe {
        Some(rpe) if (1..=10).contains(&reps) && (6.0..=10.0).contains(&rpe) => {
            constants::rpe_percent(reps, int_of(rpe))
        }
        None if (1..=10).contains(&reps) => constants::rpe_percent(reps, 10),
        _ => None,
    };
    pct.filter(|pct| *pct != 0.0).map(|pct| weight / pct)
}

pub fn from_competitions(competitions: &[&Competition], reference: NaiveDate) -> Maxes {
    let mut ordered: Vec<&&Competition> = competitions.iter().collect();
    ordered.sort_by(|a, b| b.date_text.cmp(&a.date_text));
    for competition in ordered {
        if competition.status == "skipped" {
            continue;
        }
        if competition.date.is_none_or(|date| date > reference) {
            continue;
        }
        if competition
            .results
            .as_ref()
            .is_none_or(|results| results.is_empty())
        {
            continue;
        }
        let mut best = Maxes::default();
        for (lift, key) in [
            (Lift::Squat, "squat_kg"),
            (Lift::Bench, "bench_kg"),
            (Lift::Deadlift, "deadlift_kg"),
        ] {
            if let Some(value) = competition.result_kg(key) {
                best.set(lift, value);
            }
        }
        if !best.is_empty() {
            return best;
        }
    }
    Maxes::default()
}

pub fn from_sessions(sessions: Sessions<'_>, lookback_days: i64, reference: NaiveDate) -> Maxes {
    let cutoff = reference - Duration::days(lookback_days);
    let mut estimates: [Vec<f64>; 3] = Default::default();
    for session in sessions {
        if session
            .date
            .is_none_or(|date| date < cutoff || date > reference)
        {
            continue;
        }
        if matches!(session.status.as_deref(), Some("planned" | "skipped")) {
            continue;
        }
        for exercise in &session.exercises {
            if exercise.failed_sets() > 0 || exercise.executed_sets() <= 0.0 {
                continue;
            }
            let (kg, reps) = (exercise.kg, exercise.reps_int());
            if kg <= 0.0 || reps <= 0 {
                continue;
            }
            let Some(lift) = Lift::from_name(&exercise.key) else {
                continue;
            };
            if let Some(value) = estimate(kg, reps, session.session_rpe) {
                estimates[lift as usize].push(value);
            }
        }
    }
    let mut maxes = Maxes::default();
    let mut found = 0;
    for lift in Lift::ALL {
        let values = &mut estimates[lift as usize];
        if values.len() >= 3 {
            values.sort_by(f64::total_cmp);
            let index = ((values.len() as f64 * 0.9) as usize).min(values.len() - 1);
            maxes.set(lift, values[index]);
            found += 1;
        }
    }
    if found >= 2 { maxes } else { Maxes::default() }
}

pub fn from_sessions_default(sessions: Sessions<'_>, reference: NaiveDate) -> Maxes {
    from_sessions(sessions, 42, reference)
}
