use serde::Serialize;
use serde_json::Value;

use super::Context;
use crate::calc::alerts::{ProjectionEntry, rounded_maxes};
use crate::calc::compliance::{self, Compliance};
use crate::calc::projection::{self, AttemptSelection, Calibration, Projection, meet_projection};
use crate::calc::{deload, scoring};
use crate::model::{Lift, Maxes, Session};
use crate::util::truthy_of;

#[derive(Debug, Serialize)]
pub struct CurrentMaxes {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub squat: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub bench: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub deadlift: Option<f64>,
    pub method: &'static str,
}

#[derive(Debug, Serialize)]
pub struct DeloadInfo {
    pub deload_weeks: Vec<i64>,
    pub break_weeks: Vec<i64>,
    pub effective_training_weeks: usize,
}

#[derive(Debug, Serialize)]
pub struct Overview<'a> {
    pub week: i64,
    pub selected_week_start: Option<i64>,
    pub selected_week_end: Option<i64>,
    pub selected_week_count: i64,
    pub window_start: Option<&'a str>,
    pub window_end: Option<&'a str>,
    pub selected_session_context: &'a [&'a Session],
    pub block: &'a str,
    pub compliance: Compliance,
    pub current_maxes: CurrentMaxes,
    pub estimated_dots: Option<f64>,
    pub estimated_dots_reason: Option<&'static str>,
    pub projections: Vec<ProjectionEntry>,
    pub projection_reason: Option<String>,
    pub projection_calibration: Calibration,
    pub attempt_selection: Option<AttemptSelection>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub requested_projection: Option<Projection>,
    pub sessions_analyzed: usize,
    pub deload_info: DeloadInfo,
}

pub struct Projections {
    pub estimated_dots: Option<f64>,
    pub estimated_dots_reason: Option<&'static str>,
    pub entries: Vec<ProjectionEntry>,
    pub reason: Option<String>,
    pub calibration: Calibration,
    pub attempt_selection: Option<AttemptSelection>,
}

pub fn current_maxes(context: &Context<'_>) -> CurrentMaxes {
    let rounded = rounded_maxes(&context.maxes);
    CurrentMaxes {
        squat: rounded.squat,
        bench: rounded.bench,
        deadlift: rounded.deadlift,
        method: context.maxes_method,
    }
}

pub fn projections(context: &Context<'_>) -> Projections {
    let program = context.program;
    let meta = &program.meta;
    let rounded = rounded_maxes(&context.maxes);
    let bodyweight = projection::first_number(
        &meta.map,
        &["current_body_weight_kg", "bodyweight_kg", "body_weight_kg"],
    );
    let sex = {
        let from_meta = meta.get("sex").filter(|value| truthy_of(Some(*value)));
        match from_meta {
            Some(value) => value.as_str().unwrap_or_default().to_lowercase(),
            None => program.settings_sex.to_lowercase(),
        }
    };
    let all_present = Lift::ALL
        .iter()
        .all(|lift| rounded.get(*lift).is_some_and(|value| value != 0.0));
    let (mut estimated_dots, mut estimated_dots_reason) = (None, None);
    if bodyweight > 0.0 && matches!(sex.as_str(), "male" | "female") && all_present {
        let total: f64 = Lift::ALL
            .iter()
            .map(|lift| rounded.get(*lift).unwrap_or(0.0))
            .sum();
        if total > 0.0 {
            estimated_dots = scoring::dots(total, bodyweight, &sex);
        }
    } else {
        estimated_dots_reason = Some("Missing sex or bodyweight");
    }

    let mut eligible: Vec<&crate::model::Competition> = program
        .competitions
        .iter()
        .filter(|competition| {
            matches!(
                competition.status.as_str(),
                "confirmed" | "optional" | "completed"
            )
        })
        .filter(|competition| competition.date.is_some_and(|date| date > context.end))
        .collect();
    eligible.sort_by(|a, b| a.date_text.cmp(&b.date_text));
    let chosen: Vec<&crate::model::Competition> = match eligible.as_slice() {
        [first, .., last] => vec![*first, *last],
        [only] => vec![*only],
        [] => Vec::new(),
    };
    let mut entries = Vec::new();
    let mut reason = None;
    for competition in chosen {
        match meet_projection(
            context.env,
            program,
            &context.sessions,
            &competition.date_text,
            context.end,
        ) {
            crate::calc::Computed::Ready(projection) => entries.push(ProjectionEntry {
                comp_name: competition.name.clone(),
                projection,
            }),
            crate::calc::Computed::Insufficient(insufficient) => reason = Some(insufficient.reason),
        }
    }
    if !entries.is_empty() {
        reason = None;
    }
    let attempt_selection = entries.first().and_then(|first| {
        let mut projected = Maxes::default();
        for lift in Lift::ALL {
            if let Some(value) = first.projection.lifts.get(lift.key()) {
                projected.set(lift, value.projected);
            }
        }
        projection::attempt_selection(
            &projected,
            meta.get("attempt_pct").and_then(Value::as_object),
        )
    });
    Projections {
        estimated_dots,
        estimated_dots_reason,
        entries,
        reason,
        calibration: projection::calibration(&program.competitions, context.end),
        attempt_selection,
    }
}

fn requested_projection(context: &Context<'_>) -> Option<Projection> {
    let date = context.projection_date.as_deref()?;
    match meet_projection(
        context.env,
        context.program,
        &context.sessions,
        date,
        context.end,
    ) {
        crate::calc::Computed::Ready(projection) => Some(projection),
        crate::calc::Computed::Insufficient(_) => None,
    }
}

pub fn deload_info(context: &Context<'_>) -> DeloadInfo {
    let loads = deload::detect(&context.sessions, &context.program_start);
    DeloadInfo {
        deload_weeks: loads
            .iter()
            .filter(|load| load.is_deload)
            .map(|load| load.week)
            .collect(),
        break_weeks: loads
            .iter()
            .filter(|load| load.is_break)
            .map(|load| load.week)
            .collect(),
        effective_training_weeks: loads
            .iter()
            .filter(|load| load.effective_index.is_some())
            .count(),
    }
}

pub fn compliance_of(context: &Context<'_>) -> Compliance {
    match (context.selected_week_start, context.selected_week_end) {
        (Some(start), Some(end)) => {
            compliance::for_week_window(&context.sessions, &context.phases, start, end, context.end)
        }
        _ => compliance::for_trailing_weeks(
            &context.sessions,
            &context.phases,
            &context.program_start,
            context.selected_week_count,
            context.end,
        ),
    }
}

pub fn build<'a>(context: &'a Context<'a>) -> Overview<'a> {
    let computed = projections(context);
    Overview {
        week: context.current_week,
        selected_week_start: context.selected_week_start,
        selected_week_end: context.selected_week_end,
        selected_week_count: context.selected_week_count,
        window_start: context.window_start.as_deref(),
        window_end: context.window_end.as_deref(),
        selected_session_context: &context.recent_sessions,
        block: &context.phase_name,
        compliance: compliance_of(context),
        current_maxes: current_maxes(context),
        estimated_dots: computed.estimated_dots,
        estimated_dots_reason: computed.estimated_dots_reason,
        projections: computed.entries,
        projection_reason: computed.reason,
        projection_calibration: computed.calibration,
        attempt_selection: computed.attempt_selection,
        requested_projection: requested_projection(context),
        sessions_analyzed: context.completed_in_window.len(),
        deload_info: deload_info(context),
    }
}
