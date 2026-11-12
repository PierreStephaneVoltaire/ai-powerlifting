use chrono::{Duration, NaiveDate};
use serde_json::Value;

use crate::calc::weeks::{current_week, date_bounds, find_phase, in_week_window, resolve_window};
use crate::calc::{Env, e1rm};
use crate::error::Error;
use crate::model::{Maxes, Phase, ProgramData, Session};
use crate::scope::BlockScope;
use crate::util::parse_date;

pub mod alerts;
pub mod fatigue_readiness;
pub mod overview;
pub mod peaking;
pub mod workload;

pub const DETERMINISTIC: [&str; 5] = [
    "overview",
    "fatigue_readiness",
    "peaking",
    "workload",
    "alerts",
];

#[derive(Debug, Clone, Default)]
pub struct Params {
    pub weeks: i64,
    pub block: Option<String>,
    pub window_start: Option<String>,
    pub window_end: Option<String>,
    pub ref_date: Option<String>,
    pub week_start: Option<i64>,
    pub week_end: Option<i64>,
    pub provided_maxes: Maxes,
    pub projection_date: Option<String>,
}

pub struct Context<'a> {
    pub env: Env<'a>,
    pub program: &'a ProgramData,
    pub sessions: Vec<&'a Session>,
    pub phases: &'a [Phase],
    pub program_start: String,
    pub current_week: i64,
    pub current_phase: Option<&'a Phase>,
    pub phase_name: String,
    pub end: NaiveDate,
    pub window_start: Option<String>,
    pub window_end: Option<String>,
    pub selected_week_start: Option<i64>,
    pub selected_week_end: Option<i64>,
    pub selected_week_count: i64,
    pub recent_sessions: Vec<&'a Session>,
    pub completed_in_window: Vec<&'a Session>,
    pub all_to_ref: Vec<&'a Session>,
    pub completed_history: Vec<&'a Session>,
    pub maxes: Maxes,
    pub maxes_method: &'static str,
    pub projection_date: Option<String>,
}

fn sorted_desc(mut sessions: Vec<&Session>) -> Vec<&Session> {
    sessions.sort_by(|a, b| b.date_text.cmp(&a.date_text));
    sessions
}

fn date_of(text: &str) -> Result<NaiveDate, Error> {
    parse_date(text).ok_or_else(|| Error::Validation(format!("Invalid date: {text}")))
}

impl<'a> Context<'a> {
    pub fn build(env: Env<'a>, program: &'a ProgramData, params: &Params) -> Result<Self, Error> {
        let program_start = program.meta.program_start();
        let scope = BlockScope::new(&program.meta);
        let sessions: Vec<&Session> =
            match params.block.as_deref().filter(|block| !block.is_empty()) {
                Some(block) => program
                    .sessions
                    .iter()
                    .filter(|session| scope.in_block(&session.block_key, block))
                    .collect(),
                None => program.sessions.iter().collect(),
            };
        let week = current_week(&program_start, &sessions, env.today);
        let current_phase = find_phase(&program.phases, week);
        let phase_name =
            current_phase.map_or_else(|| "Unknown".to_owned(), |phase| phase.name.clone());
        let window_end = params.window_end.clone().filter(|text| !text.is_empty());
        let end = match (&window_end, &params.ref_date) {
            (Some(text), _) => date_of(text)?,
            (None, Some(text)) if !text.is_empty() => date_of(text)?,
            _ => env.today,
        };
        let start = match params
            .window_start
            .as_deref()
            .filter(|text| !text.is_empty())
        {
            Some(text) => Some(date_of(text)?),
            None => None,
        };
        let weeks = params.weeks.max(1);
        let use_week_window =
            params.week_start.is_some() || params.week_end.is_some() || start.is_none();
        let mut window_start = params.window_start.clone().filter(|text| !text.is_empty());
        let mut window_end_out = window_end;
        let all_to_ref: Vec<&Session> = sessions
            .iter()
            .copied()
            .filter(|session| session.date.is_some_and(|date| date <= end))
            .collect();
        let completed_history: Vec<&Session> = all_to_ref
            .iter()
            .copied()
            .filter(|session| session.completed)
            .collect();
        let (selected_start, selected_end, count, recent, completed);
        if use_week_window {
            let (first, last) = resolve_window(
                &sessions,
                week,
                params.weeks,
                &program_start,
                params.week_start,
                params.week_end,
            );
            let selected = in_week_window(&sessions, &program_start, first, last);
            let inferred = date_bounds(&selected).map(|(first, _)| first);
            if start.is_none() {
                let fallback = inferred.unwrap_or(end - Duration::days((weeks * 7).max(7) - 1));
                window_start = Some(fallback.to_string());
            }
            if window_end_out.is_none() {
                window_end_out = Some(end.to_string());
            }
            let in_range: Vec<&Session> = selected
                .into_iter()
                .filter(|session| {
                    session.date.is_none_or(|date| date <= end) || session.date_text.is_empty()
                })
                .collect();
            recent = sorted_desc(in_range);
            completed = recent
                .iter()
                .copied()
                .filter(|session| session.completed)
                .collect::<Vec<_>>();
            selected_start = Some(first);
            selected_end = Some(last);
            count = (last - first + 1).max(1);
        } else {
            let cutoff = start.unwrap_or(end);
            recent = sorted_desc(
                all_to_ref
                    .iter()
                    .copied()
                    .filter(|session| {
                        session
                            .date
                            .is_some_and(|date| date >= cutoff && date <= end)
                    })
                    .collect(),
            );
            completed = sorted_desc(
                completed_history
                    .iter()
                    .copied()
                    .filter(|session| {
                        session
                            .date
                            .is_some_and(|date| cutoff <= date && date <= end)
                    })
                    .collect(),
            );
            let numbers: Vec<i64> = completed
                .iter()
                .filter_map(|session| session.week(&program_start))
                .collect();
            selected_start = numbers.iter().min().copied();
            selected_end = numbers.iter().max().copied();
            count = weeks;
        }
        let competitions: Vec<&crate::model::Competition> = program.competitions.iter().collect();
        let from_competitions = e1rm::from_competitions(&competitions, end);
        let from_sessions = e1rm::from_sessions(&completed_history, 42, end);
        let (maxes, method) = if !params.provided_maxes.is_empty() {
            (params.provided_maxes, "provided")
        } else if !from_competitions.is_empty() {
            (from_competitions, "comp_results")
        } else if !from_sessions.is_empty() {
            (from_sessions, "session_estimated")
        } else {
            (Maxes::default(), "none")
        };
        Ok(Self {
            env,
            program,
            sessions,
            phases: &program.phases,
            program_start,
            current_week: week,
            current_phase,
            phase_name,
            end,
            window_start,
            window_end: window_end_out,
            selected_week_start: selected_start,
            selected_week_end: selected_end,
            selected_week_count: count,
            recent_sessions: recent,
            completed_in_window: completed,
            all_to_ref,
            completed_history,
            maxes,
            maxes_method: method,
            projection_date: params
                .projection_date
                .clone()
                .filter(|text| !text.is_empty()),
        })
    }

    pub fn target_rpe_midpoint(&self) -> Option<f64> {
        self.current_phase.and_then(Phase::target_midpoint)
    }
}

pub fn compute(
    env: Env<'_>,
    program: &ProgramData,
    section: &str,
    params: &Params,
) -> Result<Value, Error> {
    let context = Context::build(env, program, params)?;
    let to_value = |value: Result<Value, serde_json::Error>| {
        value.map_err(|error| Error::Internal(error.to_string()))
    };
    match section.trim() {
        "overview" => to_value(serde_json::to_value(overview::build(&context))),
        "workload" => to_value(serde_json::to_value(workload::build(&context).0)),
        "fatigue_readiness" => to_value(serde_json::to_value(fatigue_readiness::build(&context))),
        "peaking" => to_value(serde_json::to_value(peaking::build(&context))),
        "alerts" => to_value(serde_json::to_value(alerts::build(&context))),
        other => Err(Error::Validation(format!(
            "Unknown weekly analysis section: {other}"
        ))),
    }
}

pub fn compute_all(
    env: Env<'_>,
    program: &ProgramData,
    params: &Params,
) -> Result<serde_json::Map<String, Value>, Error> {
    let mut merged = serde_json::Map::new();
    for section in DETERMINISTIC {
        if let Value::Object(payload) = compute(env, program, section, params)? {
            merged.extend(payload);
        }
    }
    Ok(merged)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::model::{Glossary, Lift};
    use serde_json::json;

    fn fixture() -> ProgramData {
        let mut sessions = Vec::new();
        for week in 1..=8_i64 {
            let day = chrono::NaiveDate::from_ymd_opt(2027, 1, 4).unwrap()
                + Duration::days((week - 1) * 7);
            let bump = week as f64 * 2.5;
            sessions.push(Session::from_value(json!({
                "date": day.to_string(),
                "week_number": week,
                "completed": true,
                "block": "current",
                "exercises": [
                    {"name": "Squat", "sets": 3, "reps": 3, "kg": 140.0 + bump},
                    {"name": "Bench Press", "sets": 3, "reps": 3, "kg": 100.0 + bump},
                    {"name": "Deadlift", "sets": 3, "reps": 3, "kg": 170.0 + bump},
                ],
            })));
        }
        ProgramData::from_value(
            &json!({"meta": {"program_start": "2027-01-04", "sex": "male", "current_body_weight_kg": 90.0}}),
            sessions,
        )
    }

    fn params() -> Params {
        Params {
            weeks: 8,
            block: Some(String::new()),
            ref_date: Some("2027-03-01".to_owned()),
            week_start: Some(1),
            week_end: Some(8),
            ..Params::default()
        }
    }

    fn today() -> NaiveDate {
        NaiveDate::from_ymd_opt(2027, 3, 1).unwrap()
    }

    #[test]
    fn provided_maxes_replace_the_estimates_and_name_their_method() {
        let program = fixture();
        let glossary = Glossary::default();
        let env = Env {
            today: today(),
            glossary: &glossary,
        };
        let mut provided = Maxes::default();
        provided.set(Lift::Squat, 185.0);
        provided.set(Lift::Bench, 122.5);
        let overview = compute(
            env,
            &program,
            "overview",
            &Params {
                provided_maxes: provided,
                ..params()
            },
        )
        .unwrap();
        assert_eq!(overview["current_maxes"]["method"], "provided");
        assert_eq!(overview["current_maxes"]["squat"], 185.0);
        assert!(overview["current_maxes"]["deadlift"].is_null());
        let estimated = compute(env, &program, "overview", &params()).unwrap();
        assert_eq!(estimated["current_maxes"]["method"], "session_estimated");
    }

    #[test]
    fn projection_date_adds_the_requested_meet_projection_only_when_asked() {
        let program = fixture();
        let glossary = Glossary::default();
        let env = Env {
            today: today(),
            glossary: &glossary,
        };
        let plain = compute(env, &program, "overview", &params()).unwrap();
        assert!(plain.get("requested_projection").is_none());
        let asked = compute(
            env,
            &program,
            "overview",
            &Params {
                projection_date: Some("2027-03-08".to_owned()),
                ..params()
            },
        )
        .unwrap();
        let projection = &asked["requested_projection"];
        assert!(projection["total"].as_f64().unwrap() > 0.0);
        assert!(projection["lifts"]["squat"]["projected"].as_f64().unwrap() > 0.0);
        let past = compute(
            env,
            &program,
            "overview",
            &Params {
                projection_date: Some("2027-02-01".to_owned()),
                ..params()
            },
        )
        .unwrap();
        assert!(past.get("requested_projection").is_none());
    }
}
