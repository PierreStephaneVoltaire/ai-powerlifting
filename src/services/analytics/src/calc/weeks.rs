use chrono::{Duration, NaiveDate};

use super::Sessions;
use crate::model::Phase;
use crate::util::{parse_date, text_of};

pub fn current_week(program_start: &str, sessions: Sessions<'_>, today: NaiveDate) -> i64 {
    if !sessions.is_empty() {
        let started: Vec<i64> = sessions
            .iter()
            .filter(|session| session.completed || session.date.is_some_and(|date| date <= today))
            .filter_map(|session| session.week_number)
            .collect();
        if let Some(week) = started.into_iter().max() {
            return week;
        }
        if let Some(week) = sessions
            .iter()
            .filter_map(|session| session.week_number)
            .min()
        {
            return week;
        }
    }
    parse_date(program_start).map_or(1, |start| {
        ((today - start).num_days().div_euclid(7) + 1).max(1)
    })
}

pub fn find_phase(phases: &[Phase], week: i64) -> Option<&Phase> {
    phases
        .iter()
        .find(|phase| phase.start_week <= week as f64 && (week as f64) <= phase.end_week)
}

pub fn infer_program_start(sessions: Sessions<'_>) -> String {
    sessions
        .iter()
        .filter_map(|session| session.date)
        .min()
        .map(|date| date.to_string())
        .unwrap_or_default()
}

pub fn calendar_week(day: NaiveDate, start: NaiveDate) -> i64 {
    ((day - start).num_days().div_euclid(7) + 1).max(1)
}

pub fn week_start_for(day: NaiveDate, start: NaiveDate) -> NaiveDate {
    let offset = (day - start).num_days();
    start + Duration::days(offset.div_euclid(7) * 7)
}

pub fn week_bound(value: Option<i64>) -> Option<i64> {
    value.filter(|week| *week > 0)
}

pub fn resolve_window(
    sessions: Sessions<'_>,
    current_week: i64,
    weeks: i64,
    program_start: &str,
    week_start: Option<i64>,
    week_end: Option<i64>,
) -> (i64, i64) {
    let span = weeks.max(1);
    let (mut start, mut end) = match (week_bound(week_start), week_bound(week_end)) {
        (None, None) => (((current_week - span + 1).max(1)), current_week),
        (None, Some(end)) => ((end - span + 1).max(1), end),
        (Some(start), None) => (start, start + span - 1),
        (Some(start), Some(end)) => (start, end),
    };
    if start > end {
        std::mem::swap(&mut start, &mut end);
    }
    let available: Vec<i64> = sessions
        .iter()
        .filter_map(|session| session.week(program_start))
        .collect();
    if let (Some(first), Some(last)) = (available.iter().min(), available.iter().max()) {
        start = start.max(*first);
        end = end.min(*last);
        if start > end {
            end = start;
        }
    }
    (start, end)
}

pub fn in_week_window<'a>(
    sessions: &[&'a crate::model::Session],
    program_start: &str,
    start: i64,
    end: i64,
) -> Vec<&'a crate::model::Session> {
    sessions
        .iter()
        .copied()
        .filter(|session| {
            session
                .week(program_start)
                .is_some_and(|week| start <= week && week <= end)
        })
        .collect()
}

pub fn date_bounds(sessions: &[&crate::model::Session]) -> Option<(NaiveDate, NaiveDate)> {
    let mut dates: Vec<NaiveDate> = sessions.iter().filter_map(|session| session.date).collect();
    dates.sort();
    Some((*dates.first()?, *dates.last()?))
}

pub fn planned_overreach(
    phases: &[Phase],
    week: Option<i64>,
    program_start: &str,
    today: NaiveDate,
) -> bool {
    if phases.is_empty() {
        return false;
    }
    let week = week.unwrap_or_else(|| current_week(program_start, &[], today));
    find_phase(phases, week).is_some_and(|phase| {
        phase.intent.to_lowercase().contains("overreach")
            || phase.target_rpe_max.unwrap_or(0.0) >= 9.0
    })
}

pub fn phase_label(phase: Option<&Phase>) -> String {
    phase.map_or_else(
        || "Unknown".to_owned(),
        |phase| text_of(&phase.name, "Unknown"),
    )
}
