use chrono::Duration;
use serde_json::{Map, Value, json};

use super::Workspace;
use super::competitions::{has_results, results_of, window};
use super::flags::data_quality;
use super::goals::{self, Goal};
use super::index::fingerprint;
use super::strength::canonical_lift;
use super::types::BlockEntry;
use crate::js::{coerce_number, iso_date, number};
use crate::model::{ProgramData, Session};

pub fn copy_session(session: &Session) -> Session {
    Session::from_value(session.raw.clone())
}

pub fn analysis_end(entry: &BlockEntry) -> &str {
    entry
        .linked_competition
        .as_ref()
        .map_or(entry.end_date.as_str(), |link| link.date.as_str())
}

pub fn scoped_entry(workspace: &Workspace<'_>, entry: &BlockEntry) -> BlockEntry {
    if !entry.is_current {
        return entry.clone();
    }
    let today = workspace.today.to_string();
    let mut all = workspace.sessions_of(&entry.block);
    all.sort_by(|a, b| a.date_text.cmp(&b.date_text));
    let dated: Vec<&Session> = all
        .iter()
        .copied()
        .filter(|session| iso_date(&session.date_text).is_some())
        .collect();
    let in_scope: Vec<&Session> = dated
        .iter()
        .copied()
        .filter(|session| session.date_text <= today)
        .collect();
    let scoped: Vec<&Session> = if in_scope.is_empty() {
        dated.iter().copied().filter(|s| s.completed).collect()
    } else {
        in_scope
    };
    let end_date = scoped.last().map_or_else(
        || {
            if entry.start_date <= today {
                today.clone()
            } else {
                entry.start_date.clone()
            }
        },
        |session| session.date_text.clone(),
    );
    let weeks: Vec<i64> = scoped
        .iter()
        .map(|session| session.week_number.unwrap_or(0))
        .filter(|week| *week > 0)
        .collect();
    let week_start = weeks.iter().min().copied().unwrap_or(entry.week_start);
    let week_end = weeks.iter().max().copied().unwrap_or(week_start);
    let phases = workspace.phases_of(&entry.block);
    let flags = data_quality(
        workspace,
        &scoped,
        &entry.start_date,
        &end_date,
        None,
        &entry.block_key,
    );
    BlockEntry {
        end_date,
        week_start,
        week_end,
        week_count: (week_end - week_start + 1).max(1),
        completed_sessions: scoped.iter().filter(|s| s.completed).count() as i64,
        planned_sessions: scoped
            .iter()
            .filter(|s| !s.completed && s.status.as_deref() != Some("skipped"))
            .count() as i64,
        total_sessions: scoped.len() as i64,
        linked_competition: None,
        training_only: true,
        comparison_eligible: false,
        source_fingerprint: fingerprint(workspace, &entry.block, &scoped, &phases, &[], &[]),
        data_quality_flags: flags,
        ..entry.clone()
    }
}

fn has_sbd_on(sessions: &[&Session], date: &str) -> bool {
    let mut lifts = std::collections::BTreeSet::new();
    for session in sessions
        .iter()
        .filter(|session| session.date_text == date && session.completed)
    {
        lifts.extend(
            session
                .exercises
                .iter()
                .filter_map(|exercise| canonical_lift(&exercise.name)),
        );
    }
    lifts.len() == 3
}

fn synthetic_session(entry: &BlockEntry, sessions: &[&Session]) -> Option<Session> {
    let link = entry.linked_competition.as_ref()?;
    let competition = &link.competition;
    let results = results_of(competition).filter(|results| has_results(Some(results)))?;
    if has_sbd_on(sessions, &link.date) {
        return None;
    }
    let template_phase = sessions
        .iter()
        .rev()
        .find_map(|session| session.raw.get("phase").filter(|phase| !phase.is_null()))
        .or_else(|| {
            sessions
                .first()
                .and_then(|session| session.raw.get("phase"))
        })
        .cloned()
        .unwrap_or_else(|| {
            json!({
                "name": "Competition",
                "intent": "competition",
                "start_week": entry.week_end,
                "end_week": entry.week_end,
                "block": entry.block,
            })
        });
    let lift = |name: &str, key: &str| {
        json!({
            "name": name,
            "sets": 1,
            "reps": 1,
            "kg": results.get(key),
            "notes": "Synthetic competition result",
            "set_statuses": ["completed"],
        })
    };
    Some(Session::from_value(json!({
        "id": format!("synthetic_comp_{}_{}", entry.block_key, link.date),
        "date": link.date,
        "day": "Competition",
        "week": format!("W{} (Competition)", entry.week_end),
        "week_number": entry.week_end,
        "phase": template_phase,
        "block": entry.block,
        "status": "completed",
        "completed": true,
        "planned_exercises": [],
        "exercises": [
            lift("Squat", "squat_kg"),
            lift("Bench Press", "bench_kg"),
            lift("Deadlift", "deadlift_kg"),
        ],
        "session_notes": format!("Synthetic meet result imported from {}.", link.name),
        "session_rpe": 10,
        "body_weight_kg": competition.get("body_weight_kg"),
    })))
}

pub fn analysis_sessions(
    workspace: &Workspace<'_>,
    entry: &BlockEntry,
    include_synthetic: bool,
) -> Vec<Session> {
    let end = analysis_end(entry);
    let sessions: Vec<&Session> = workspace
        .sessions_of(&entry.block)
        .into_iter()
        .filter(|session| {
            !session.date_text.is_empty()
                && (entry.start_date.is_empty() || session.date_text >= entry.start_date)
                && (end.is_empty() || session.date_text.as_str() <= end)
        })
        .collect();
    let synthetic = include_synthetic
        .then(|| synthetic_session(entry, &sessions))
        .flatten();
    let mut copies: Vec<Session> = sessions.into_iter().map(copy_session).collect();
    if let Some(extra) = synthetic {
        copies.push(extra);
        copies.sort_by(|a, b| a.date_text.cmp(&b.date_text));
    }
    copies
}

pub fn projection_reference(entry: &BlockEntry) -> String {
    let Some(date) = entry
        .linked_competition
        .as_ref()
        .and_then(|link| iso_date(&link.date))
    else {
        return entry.end_date.clone();
    };
    let day_before = (date - Duration::days(1)).to_string();
    if !entry.end_date.is_empty() && entry.end_date < day_before {
        entry.end_date.clone()
    } else {
        day_before
    }
}

fn scoped_meta(
    workspace: &Workspace<'_>,
    entry: &BlockEntry,
    competitions: &[&Value],
    goals: &[Goal],
) -> Map<String, Value> {
    let mut meta = workspace.meta().clone();
    let link_date = entry
        .linked_competition
        .as_ref()
        .map(|link| link.date.as_str());
    let primary = competitions
        .iter()
        .find(|competition| {
            link_date.is_some() && competition.get("date").and_then(Value::as_str) == link_date
        })
        .or_else(|| competitions.first())
        .copied();
    let start = if entry.start_date.is_empty() {
        meta.get("program_start").cloned()
    } else {
        Some(Value::String(entry.start_date.clone()))
    };
    let set = |meta: &mut Map<String, Value>, key: &str, value: Option<Value>| match value {
        Some(value) => {
            meta.insert(key.to_owned(), value);
        }
        None => {
            meta.remove(key);
        }
    };
    set(&mut meta, "program_start", start);
    for (key, source) in [
        ("current_body_weight_kg", "body_weight_kg"),
        ("weight_class_kg", "weight_class_kg"),
    ] {
        let from_competition = primary
            .and_then(|competition| competition.get(source))
            .filter(|value| !value.is_null())
            .cloned();
        let value = from_competition.or_else(|| meta.get(key).cloned());
        set(&mut meta, key, value);
    }
    if !entry.is_current {
        match primary
            .and_then(|competition| competition.get("targets"))
            .filter(|targets| crate::js::truthy(Some(targets)))
        {
            Some(targets) => {
                for (target, key) in [
                    ("target_squat_kg", "squat_kg"),
                    ("target_bench_kg", "bench_kg"),
                    ("target_dl_kg", "deadlift_kg"),
                    ("target_total_kg", "total_kg"),
                ] {
                    set(&mut meta, target, targets.get(key).cloned());
                }
            }
            None => {
                for target in ["target_squat_kg", "target_bench_kg", "target_dl_kg"] {
                    meta.remove(target);
                }
                let total = goals.iter().find_map(|goal| goal.target_total_kg);
                set(
                    &mut meta,
                    "target_total_kg",
                    total.map(|total| json!(total)),
                );
            }
        }
    }
    meta
}

pub fn program_for_block(
    workspace: &Workspace<'_>,
    entry: &BlockEntry,
) -> (ProgramData, Vec<Goal>) {
    let sessions = analysis_sessions(workspace, entry, false);
    let end = analysis_end(entry).to_owned();
    let raw_end = workspace
        .sessions_of(&entry.block)
        .iter()
        .map(|session| session.date_text.as_str())
        .filter(|date| !date.is_empty())
        .max()
        .unwrap_or(&entry.end_date)
        .to_owned();
    let context_end = if entry.is_current && raw_end > entry.end_date {
        raw_end
    } else {
        entry.end_date.clone()
    };
    let competitions = window(
        workspace,
        &entry.start_date,
        &context_end,
        entry.linked_competition.as_ref(),
    );
    let scoped_goals = goals::for_competitions(&workspace.goals, &competitions);
    let mut meta = scoped_meta(workspace, entry, &competitions, &scoped_goals);
    meta.insert(
        "block_notes".to_owned(),
        Value::Array(workspace.block_notes(&entry.start_date, &end)),
    );
    let mut root = workspace.program.root.clone();
    root.insert("meta".to_owned(), Value::Object(meta));
    root.insert(
        "phases".to_owned(),
        Value::Array(
            workspace
                .phases_of(&entry.block)
                .into_iter()
                .cloned()
                .collect(),
        ),
    );
    root.insert(
        "competitions".to_owned(),
        Value::Array(competitions.into_iter().cloned().collect()),
    );
    root.insert(
        "diet_notes".to_owned(),
        Value::Array(
            workspace
                .diet_notes(&entry.start_date, &end)
                .into_iter()
                .cloned()
                .collect(),
        ),
    );
    let history = workspace
        .program
        .all_sessions()
        .iter()
        .map(|session| Session::from_value(session.raw.clone()))
        .collect();
    (
        ProgramData::from_value(&Value::Object(root), sessions).with_history(history),
        scoped_goals,
    )
}

pub fn latest_bodyweight(
    sessions: &[&Session],
    fallback: Option<f64>,
    max_date: &str,
    weight_log: &[Value],
) -> Option<f64> {
    let mut dated: Vec<(String, f64)> = Vec::new();
    let mut put = |date: &str, kg: f64| match dated.iter_mut().find(|(key, _)| key == date) {
        Some(slot) => slot.1 = kg,
        None => dated.push((date.to_owned(), kg)),
    };
    for entry in weight_log {
        let date = entry
            .get("date")
            .and_then(Value::as_str)
            .unwrap_or_default();
        if let Some(kg) = number(entry.get("kg")).filter(|kg| *kg > 0.0)
            && date <= max_date
        {
            put(date, kg);
        }
    }
    for session in sessions {
        let kg = number(session.raw.get("body_weight_kg")).filter(|kg| *kg > 0.0);
        if let Some(kg) = kg
            && session.status.as_deref() != Some("skipped")
            && session.date_text.as_str() <= max_date
        {
            put(&session.date_text, kg);
        }
    }
    dated.sort_by(|a, b| b.0.cmp(&a.0));
    dated.first().map(|(_, kg)| *kg).or(fallback)
}

pub fn exercise_volume(session: &Session) -> f64 {
    session
        .raw
        .get("exercises")
        .and_then(Value::as_array)
        .map_or(0.0, |items| {
            items
                .iter()
                .map(|exercise| {
                    coerce_number(exercise.get("sets"))
                        * coerce_number(exercise.get("reps"))
                        * coerce_number(exercise.get("kg"))
                })
                .sum()
        })
}
