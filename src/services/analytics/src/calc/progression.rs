use std::collections::BTreeMap;

use chrono::{Duration, NaiveDate};
use serde::Serialize;

use super::weeks::infer_program_start;
use super::{Computed, Sessions, deload, e1rm};
use crate::model::{Glossary, Lift, Phase};
use crate::util::{clamp, int_of, kendall_tau, mad, parse_date, round, theil_sen};

const LOOKBACK_DAYS: i64 = 90;

#[derive(Debug, Serialize)]
pub struct Progression {
    pub slope_kg_per_week: f64,
    pub kendall_tau: f64,
    pub fit_quality: f64,
    pub r2: f64,
    pub r_squared: f64,
    pub points: Vec<(f64, f64)>,
    pub method: &'static str,
    pub deload_weeks_excluded: usize,
}

#[derive(Debug, Serialize)]
pub struct RpeDrift {
    pub slope: f64,
    pub drift_direction: &'static str,
    pub flag: Option<&'static str>,
    pub kendall_tau: f64,
    pub fit_quality: f64,
    pub r2: f64,
    pub r_squared: f64,
    pub mode: &'static str,
}

pub fn fit_quality(xs: &[f64], ys: &[f64], slope: f64, intercept: f64) -> (f64, f64) {
    if xs.len() < 2 {
        return (0.0, 0.0);
    }
    let tau = kendall_tau(xs, ys);
    let tau = if tau.is_nan() { 0.0 } else { tau };
    let residuals: Vec<f64> = xs
        .iter()
        .zip(ys)
        .map(|(x, y)| y - (intercept + slope * x))
        .collect();
    let series_mad = mad(ys);
    let residual_mad = mad(&residuals);
    let quality = if series_mad <= 1e-12 {
        if residual_mad <= 1e-12 { 1.0 } else { 0.0 }
    } else {
        clamp(1.0 - residual_mad / series_mad, 0.0, 1.0)
    };
    (round(tau, 3), round(quality, 3))
}

fn exercise_sessions<'a>(
    sessions: Sessions<'a>,
    matches: &dyn Fn(&str) -> bool,
) -> Vec<&'a crate::model::Session> {
    sessions
        .iter()
        .copied()
        .filter(|session| {
            session.completed
                && session
                    .exercises
                    .iter()
                    .any(|exercise| matches(&exercise.key))
        })
        .collect()
}

pub fn progression_rate(
    sessions: Sessions<'_>,
    exercise: &str,
    program_start: &str,
    reference: NaiveDate,
) -> Computed<Progression> {
    let name_lower = crate::util::normalize_name(exercise);
    progression_by(sessions, exercise, program_start, reference, &|key| {
        key == name_lower
    })
}

pub fn lift_progression_rate(
    sessions: Sessions<'_>,
    lift: Lift,
    glossary: &Glossary,
    program_start: &str,
    reference: NaiveDate,
) -> Computed<Progression> {
    progression_by(sessions, lift.key(), program_start, reference, &|key| {
        glossary.narrow_lift(key) == Some(lift)
    })
}

fn progression_by(
    sessions: Sessions<'_>,
    exercise: &str,
    program_start: &str,
    reference: NaiveDate,
    matches: &dyn Fn(&str) -> bool,
) -> Computed<Progression> {
    let owned_start;
    let program_start = if program_start.is_empty() {
        owned_start = infer_program_start(sessions);
        owned_start.as_str()
    } else {
        program_start
    };
    let cutoff = reference - Duration::days(LOOKBACK_DAYS);
    let in_range: Vec<&crate::model::Session> = exercise_sessions(sessions, matches)
        .into_iter()
        .filter(|session| {
            session
                .date
                .is_some_and(|date| cutoff <= date && date <= reference)
        })
        .collect();
    let loads = deload::detect(sessions, program_start);
    let excluded = loads.iter().filter(|load| load.excluded()).count();
    let effective: BTreeMap<i64, usize> = loads
        .iter()
        .filter_map(|load| Some((load.week, load.effective_index?)))
        .collect();
    let mut by_week: BTreeMap<usize, Vec<f64>> = BTreeMap::new();
    for session in in_range {
        let Some(index) = session
            .week(program_start)
            .and_then(|week| effective.get(&week).copied())
        else {
            continue;
        };
        for item in session.exercises.iter().filter(|item| matches(&item.key)) {
            if item.failed_sets() > 0
                || item.executed_sets() <= 0.0
                || item.kg <= 0.0
                || item.reps_int() <= 0
            {
                continue;
            }
            if let Some(value) = e1rm::estimate(item.kg, item.reps_int(), session.session_rpe) {
                by_week.entry(index).or_default().push(value);
            }
        }
    }
    if by_week.is_empty() {
        return Computed::insufficient(format!("No qualifying e1RM estimates for {exercise}"));
    }
    let xs: Vec<f64> = by_week.keys().map(|week| *week as f64).collect();
    let ys: Vec<f64> = by_week
        .values()
        .map(|values| values.iter().copied().fold(f64::MIN, f64::max))
        .collect();
    if xs.len() < 2 {
        return Computed::insufficient(format!(
            "Need at least 2 effective training weeks with {exercise} data"
        ));
    }
    let fit = theil_sen(&ys, &xs);
    let (tau, quality) = fit_quality(&xs, &ys, fit.slope, fit.intercept);
    Computed::Ready(Progression {
        slope_kg_per_week: round(fit.slope, 2),
        kendall_tau: tau,
        fit_quality: quality,
        r2: quality,
        r_squared: quality,
        points: xs
            .iter()
            .zip(&ys)
            .map(|(x, y)| (round(*x, 1), round(*y, 1)))
            .collect(),
        method: "theilsen",
        deload_weeks_excluded: excluded,
    })
}

pub struct Series {
    pub volume: Vec<f64>,
    pub intensity: Vec<f64>,
}

pub fn volume_intensity(
    sessions: Sessions<'_>,
    exercise: &str,
    program_start: &str,
) -> Option<Series> {
    let owned_start;
    let program_start = if program_start.is_empty() {
        owned_start = infer_program_start(sessions);
        owned_start.as_str()
    } else {
        program_start
    };
    let name_lower = crate::util::normalize_name(exercise);
    let mut weekly: BTreeMap<i64, (f64, f64, i64)> = BTreeMap::new();
    for session in sessions.iter().filter(|session| session.completed) {
        let Some(week) = session.week(program_start) else {
            continue;
        };
        for item in session
            .exercises
            .iter()
            .filter(|item| item.key == name_lower)
        {
            let entry = weekly.entry(week).or_default();
            entry.0 += item.executed_sets() * item.reps * item.kg;
            entry.1 += item.kg;
            entry.2 += 1;
        }
    }
    if weekly.len() < 3 {
        return None;
    }
    Some(Series {
        volume: weekly
            .values()
            .map(|(volume, _, _)| round(*volume, 0))
            .collect(),
        intensity: weekly
            .values()
            .map(|(_, kg, count)| round(kg / *count as f64, 1))
            .collect(),
    })
}

pub fn rpe_drift(
    sessions: Sessions<'_>,
    exercise: &str,
    program_start: &str,
    window_weeks: i64,
    phases: &[Phase],
) -> Computed<RpeDrift> {
    let owned_start;
    let program_start = if program_start.is_empty() {
        owned_start = infer_program_start(sessions);
        owned_start.as_str()
    } else {
        program_start
    };
    let name_lower = crate::util::normalize_name(exercise);
    let in_exercise = exercise_sessions(sessions, &|key| key == name_lower);
    if in_exercise.len() < 3 {
        return Computed::insufficient(format!(
            "Need at least 3 completed sessions with {exercise}"
        ));
    }
    let window_start = parse_date(program_start)
        .filter(|_| !program_start.is_empty())
        .map(|start| {
            let span = ((sessions.len() as i64) / 3 - window_weeks).max(0);
            start + Duration::weeks(span)
        });
    let mut points: Vec<(i64, f64)> = Vec::new();
    for session in in_exercise {
        if let (Some(window), Some(date)) = (window_start, session.date)
            && date < window
        {
            continue;
        }
        let Some(week) = session.week(program_start) else {
            continue;
        };
        let rpe = match session.session_rpe {
            Some(rpe) => Some(rpe),
            None => session
                .exercises
                .iter()
                .find(|item| item.key == name_lower)
                .and_then(|item| item.rpe),
        };
        if let Some(rpe) = rpe {
            points.push((week, rpe));
        }
    }
    if points.len() < 3 {
        return Computed::insufficient(format!("Need at least 3 RPE data points for {exercise}"));
    }
    let mut targets: BTreeMap<i64, f64> = BTreeMap::new();
    for phase in phases {
        if let Some(midpoint) = phase.target_midpoint() {
            for week in int_of(phase.start_week)..=int_of(phase.end_week) {
                targets.insert(week, midpoint);
            }
        }
    }
    let mut use_residual = !targets.is_empty();
    let (mut xs, mut ys): (Vec<f64>, Vec<f64>) = points
        .iter()
        .map(|(week, rpe)| (*week as f64, *rpe))
        .unzip();
    if use_residual {
        let residuals: Vec<(f64, f64)> = points
            .iter()
            .filter_map(|(week, rpe)| Some((*week as f64, rpe - targets.get(week)?)))
            .collect();
        if residuals.len() >= 3 {
            (xs, ys) = residuals.into_iter().unzip();
        } else {
            use_residual = false;
        }
    }
    let (slope, tau, quality) = if xs.len() >= 2 {
        let fit = theil_sen(&ys, &xs);
        let (tau, quality) = fit_quality(&xs, &ys, fit.slope, fit.intercept);
        (fit.slope, tau, quality)
    } else {
        (0.0, 0.0, 0.0)
    };
    let direction = if slope >= 0.1 {
        "up"
    } else if slope <= -0.1 {
        "down"
    } else {
        "stable"
    };
    let flag = if slope >= 0.1 {
        Some("fatigue")
    } else if slope <= -0.1 {
        Some("adaptation")
    } else {
        None
    };
    Computed::Ready(RpeDrift {
        slope: round(slope, 3),
        drift_direction: direction,
        flag,
        kendall_tau: tau,
        fit_quality: quality,
        r2: quality,
        r_squared: quality,
        mode: if use_residual { "residual" } else { "raw" },
    })
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::*;
    use crate::model::Session;

    fn sessions(names: [&str; 5]) -> Vec<Session> {
        names
            .iter()
            .enumerate()
            .map(|(index, name)| {
                Session::from_value(json!({
                    "date": format!("2027-02-{:02}", 1 + index * 7),
                    "week_number": index + 1,
                    "completed": true,
                    "exercises": [{"name": name, "kg": 100 + (index + 1) * 5, "reps": 5, "sets": 3}],
                }))
            })
            .collect()
    }

    fn slope(sessions: &[Session], lift: Lift, glossary: &Glossary) -> Option<f64> {
        let refs: Vec<&Session> = sessions.iter().collect();
        let reference = NaiveDate::from_ymd_opt(2027, 3, 10).unwrap();
        match lift_progression_rate(&refs, lift, glossary, "2027-02-01", reference) {
            Computed::Ready(result) => Some(result.slope_kg_per_week),
            Computed::Insufficient(_) => None,
        }
    }

    #[test]
    fn lift_progression_resolves_bench_press_naming() {
        let glossary = Glossary::default();
        let named = sessions(["Bench Press"; 5]);
        assert!(slope(&named, Lift::Bench, &glossary).is_some_and(|value| value > 0.0));
        let mixed = sessions([
            "Bench",
            "Bench Press",
            "bench press (pause)",
            "Bench",
            "Bench Press",
        ]);
        assert!(slope(&mixed, Lift::Bench, &glossary).is_some_and(|value| value > 0.0));
        assert!(slope(&named, Lift::Deadlift, &glossary).is_none());
    }

    #[test]
    fn lift_progression_uses_glossary_lift_transfer_for_variants() {
        let variants = sessions(["Back Squat"; 5]);
        assert!(slope(&variants, Lift::Squat, &Glossary::default()).is_none());
        let glossary = Glossary::from_values(&[json!({
            "name": "Back Squat",
            "lift_transfer": {"squat": 0.95, "bench": 0.0, "deadlift": 0.2},
        })]);
        assert!(slope(&variants, Lift::Squat, &glossary).is_some_and(|value| value > 0.0));
        let weak = Glossary::from_values(&[json!({
            "name": "Back Squat",
            "lift_transfer": {"squat": 0.85},
        })]);
        assert!(slope(&variants, Lift::Squat, &weak).is_none());
    }
}
