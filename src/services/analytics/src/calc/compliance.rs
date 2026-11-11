use chrono::NaiveDate;
use serde::Serialize;

use super::Sessions;
use super::weeks::{find_phase, phase_label};
use crate::model::{Phase, Session};
use crate::util::{num_of, round};

#[derive(Debug, Serialize)]
pub struct Compliance {
    pub phase: String,
    pub planned: usize,
    pub completed: usize,
    pub missed: usize,
    pub pct: f64,
    pub planned_sets: f64,
    pub completed_sets: f64,
    pub set_pct: f64,
    pub planned_reps: f64,
    pub completed_reps: f64,
    pub rep_pct: f64,
    pub planned_volume: f64,
    pub completed_volume: f64,
    pub vol_pct: f64,
}

#[derive(Default)]
struct Totals {
    planned_sets: f64,
    completed_sets: f64,
    planned_reps: f64,
    completed_reps: f64,
    planned_volume: f64,
    completed_volume: f64,
}

impl Totals {
    fn add(&mut self, session: &Session) {
        let planned = session.planned_exercises();
        if planned.is_empty() && session.completed {
            let sets: f64 = session.exercises.iter().map(|ex| ex.executed_sets()).sum();
            let reps: f64 = session
                .exercises
                .iter()
                .map(|ex| ex.executed_sets() * ex.reps)
                .sum();
            let volume: f64 = session
                .exercises
                .iter()
                .map(|ex| ex.executed_volume())
                .sum();
            self.planned_sets += sets;
            self.completed_sets += sets;
            self.planned_reps += reps;
            self.completed_reps += reps;
            self.planned_volume += volume;
            self.completed_volume += volume;
            return;
        }
        for item in planned {
            let sets = num_of(item.get("sets"));
            let reps = num_of(item.get("reps"));
            self.planned_sets += sets;
            self.planned_reps += sets * reps;
            self.planned_volume += sets * reps * num_of(item.get("kg"));
        }
        for exercise in &session.exercises {
            self.completed_sets += exercise.executed_sets();
            self.completed_reps += exercise.executed_sets() * exercise.reps;
            self.completed_volume += exercise.executed_volume();
        }
    }
}

fn ratio(done: f64, planned: f64, any_completed: bool) -> f64 {
    if planned > 0.0 {
        round(done / planned * 100.0, 1)
    } else if any_completed {
        100.0
    } else {
        0.0
    }
}

fn summarize(window: &[&Session], phase: String, reference: NaiveDate) -> Compliance {
    let planned_count = window.len();
    let completed = window.iter().filter(|session| session.completed).count();
    let missed = window
        .iter()
        .filter(|session| {
            session.status.as_deref() == Some("skipped")
                || session.inferred_skipped
                || (!session.completed && session.date.is_some_and(|date| date < reference))
        })
        .count();
    let mut totals = Totals::default();
    for session in window {
        totals.add(session);
    }
    Compliance {
        phase,
        planned: planned_count,
        completed,
        missed,
        pct: if planned_count > 0 {
            round(completed as f64 / planned_count as f64 * 100.0, 1)
        } else {
            0.0
        },
        planned_sets: totals.planned_sets,
        completed_sets: totals.completed_sets,
        set_pct: ratio(totals.completed_sets, totals.planned_sets, completed > 0),
        planned_reps: totals.planned_reps,
        completed_reps: totals.completed_reps,
        rep_pct: ratio(totals.completed_reps, totals.planned_reps, completed > 0),
        planned_volume: totals.planned_volume,
        completed_volume: totals.completed_volume,
        vol_pct: ratio(
            totals.completed_volume,
            totals.planned_volume,
            completed > 0,
        ),
    }
}

fn status_listed(session: &Session) -> bool {
    session
        .status
        .as_deref()
        .is_none_or(|status| matches!(status, "" | "planned" | "logged" | "completed" | "skipped"))
}

pub fn for_week_window(
    sessions: Sessions<'_>,
    phases: &[Phase],
    start: i64,
    end: i64,
    reference: NaiveDate,
) -> Compliance {
    let window: Vec<&Session> = sessions
        .iter()
        .copied()
        .filter(|session| status_listed(session))
        .filter(|session| {
            session.week_number.unwrap_or(0) >= start && session.week_number.unwrap_or(0) <= end
        })
        .collect();
    let phase = if start == end {
        phase_label(find_phase(phases, end))
    } else {
        let names: Vec<&str> = phases
            .iter()
            .filter(|phase| {
                !phase.name.is_empty()
                    && phase.start_week <= end as f64
                    && phase.end_week >= start as f64
            })
            .map(|phase| phase.name.as_str())
            .collect();
        match names.last() {
            None => "Unknown".to_owned(),
            Some(last) if names.iter().all(|name| name == last) => (*last).to_owned(),
            Some(_) => "Mixed".to_owned(),
        }
    };
    summarize(&window, phase, reference)
}

pub fn for_trailing_weeks(
    sessions: Sessions<'_>,
    phases: &[Phase],
    program_start: &str,
    weeks: i64,
    reference: NaiveDate,
) -> Compliance {
    let current = super::weeks::current_week(program_start, sessions, reference);
    let cutoff = (current - weeks + 1).max(1);
    let window: Vec<&Session> = sessions
        .iter()
        .copied()
        .filter(|session| status_listed(session))
        .filter(|session| {
            session.week_number.unwrap_or(0) >= cutoff
                && session.week_number.unwrap_or(0) <= current
        })
        .collect();
    summarize(&window, phase_label(find_phase(phases, current)), reference)
}
