use chrono::Duration;

use super::types::{StartMaxes, Strength};
use crate::calc::e1rm;
use crate::js::{iso_date, round_or_null};
use crate::model::Session;
use crate::util::round;

pub const LIFTS: [&str; 3] = ["squat", "bench", "deadlift"];

pub fn canonical_lift(name: &str) -> Option<&'static str> {
    let lower = name.to_lowercase();
    let lower = lower.trim();
    if lower.is_empty() {
        return None;
    }
    if lower.contains("squat") && !lower.contains("split") && !lower.contains("hack") {
        return Some("squat");
    }
    if lower == "bench" || lower == "bench press" {
        return Some("bench");
    }
    if lower.contains("deadlift") && !lower.contains("romanian") && !lower.contains("rdl") {
        return Some("deadlift");
    }
    None
}

pub fn set_e1rm(kg: f64, reps: f64, rpe: Option<f64>) -> Option<f64> {
    if reps.fract() != 0.0 || reps < 1.0 {
        return None;
    }
    e1rm::estimate(kg, reps as i64, rpe)
}

pub fn total_of(strength: &Strength) -> Option<f64> {
    let total = strength.squat.unwrap_or(0.0)
        + strength.bench.unwrap_or(0.0)
        + strength.deadlift.unwrap_or(0.0);
    (total > 0.0).then(|| round(total, 1))
}

fn delta(start: Option<f64>, end: Option<f64>) -> Option<f64> {
    match (start, end) {
        (Some(start), Some(end)) => round_or_null(Some(end - start), 1),
        _ => None,
    }
}

pub struct StrengthSummary {
    pub start: Strength,
    pub end: Strength,
    pub delta: Strength,
    pub manual: bool,
}

struct Record {
    lift: &'static str,
    date: String,
    e1rm: f64,
}

fn records(sessions: &[&Session]) -> Vec<Record> {
    let mut found = Vec::new();
    for session in sessions.iter().filter(|session| session.completed) {
        for exercise in &session.exercises {
            let Some(lift) = canonical_lift(&exercise.name) else {
                continue;
            };
            let rpe = exercise.rpe.or(session.session_rpe);
            if let Some(value) = set_e1rm(exercise.kg, exercise.reps, rpe) {
                found.push(Record {
                    lift,
                    date: session.date_text.clone(),
                    e1rm: value,
                });
            }
        }
    }
    found
}

pub fn estimate(
    sessions: &[&Session],
    start_date: &str,
    end_date: &str,
    manual: Option<&StartMaxes>,
) -> StrengthSummary {
    let all = records(sessions);
    let start_cutoff = iso_date(start_date).map_or_else(
        || start_date.to_owned(),
        |date| (date + Duration::days(21)).to_string(),
    );
    let end_cutoff = iso_date(end_date).map_or_else(
        || end_date.to_owned(),
        |date| (date - Duration::days(21)).to_string(),
    );
    let pick = |lift: &str, from_start: bool| -> Option<f64> {
        let mut lifted: Vec<&Record> = all.iter().filter(|record| record.lift == lift).collect();
        if lifted.is_empty() {
            return None;
        }
        lifted.sort_by(|a, b| a.date.cmp(&b.date));
        let windowed: Vec<&&Record> = lifted
            .iter()
            .filter(|record| {
                if from_start {
                    record.date <= start_cutoff
                } else {
                    record.date >= end_cutoff
                }
            })
            .collect();
        let best = if windowed.is_empty() {
            let edge = if from_start {
                lifted.first()
            } else {
                lifted.last()
            };
            edge.map_or(f64::NEG_INFINITY, |record| record.e1rm)
        } else {
            windowed
                .iter()
                .map(|record| record.e1rm)
                .fold(f64::NEG_INFINITY, f64::max)
        };
        round_or_null(Some(best), 1)
    };
    let manual_lift = |lift: &str| {
        manual.and_then(|maxes| match lift {
            "squat" => maxes.squat_kg,
            "bench" => maxes.bench_kg,
            _ => maxes.deadlift_kg,
        })
    };
    let mut start = Strength {
        squat: manual_lift("squat").or_else(|| pick("squat", true)),
        bench: manual_lift("bench").or_else(|| pick("bench", true)),
        deadlift: manual_lift("deadlift").or_else(|| pick("deadlift", true)),
        total: None,
    };
    start.total = total_of(&start);
    let mut end = Strength {
        squat: pick("squat", false),
        bench: pick("bench", false),
        deadlift: pick("deadlift", false),
        total: None,
    };
    end.total = total_of(&end);
    let delta = Strength {
        squat: delta(start.squat, end.squat),
        bench: delta(start.bench, end.bench),
        deadlift: delta(start.deadlift, end.deadlift),
        total: delta(start.total, end.total),
    };
    StrengthSummary {
        start,
        end,
        delta,
        manual: manual.is_some(),
    }
}

pub fn manual_start_maxes(workspace: &super::Workspace<'_>, block_key: &str) -> Option<StartMaxes> {
    let block_id = if block_key == super::DEFAULT_BLOCK {
        workspace
            .meta()
            .get("current_block_id")
            .filter(|value| !value.is_null())
            .and_then(serde_json::Value::as_str)
            .unwrap_or(super::DEFAULT_BLOCK)
    } else {
        block_key
    };
    let maxes = workspace
        .block_record(block_id)?
        .get("start_maxes_kg")?
        .as_object()?;
    let pick = |key: &str| maxes.get(key).and_then(serde_json::Value::as_f64);
    let (squat, bench, deadlift) = (pick("squat"), pick("bench"), pick("deadlift"));
    if squat.is_none() && bench.is_none() && deadlift.is_none() {
        return None;
    }
    let mut start = Strength {
        squat,
        bench,
        deadlift,
        total: None,
    };
    start.total = total_of(&start);
    Some(StartMaxes {
        squat_kg: squat,
        bench_kg: bench,
        deadlift_kg: deadlift,
        total_kg: start.total,
        source: "manual".to_owned(),
        updated_at: String::new(),
    })
}
