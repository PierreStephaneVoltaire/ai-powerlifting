use serde_json::{Value, json};

use super::competitions::{has_results, link_for_block, results_of, window};
use super::flags::data_quality;
use super::goals::{self, Goal};
use super::strength::manual_start_maxes;
use super::types::BlockEntry;
use super::{Workspace, block_key_for, normalize_block};
use crate::js::{iso_date, sha256_hex};
use crate::model::Session;

pub fn fingerprint(
    workspace: &Workspace<'_>,
    block: &str,
    sessions: &[&Session],
    phases: &[&Value],
    competitions: &[&Value],
    goals: &[Goal],
) -> String {
    let mut dated: Vec<Value> = sessions
        .iter()
        .map(|session| {
            let raw = &session.raw;
            json!({
                "id": raw.get("id"),
                "date": session.date_text,
                "week": raw.get("week"),
                "week_number": session.week_number,
                "block": normalize_block(&session.block),
                "status": session.status,
                "completed": session.completed,
                "session_rpe": session.session_rpe,
                "body_weight_kg": raw.get("body_weight_kg"),
                "wellness": raw.get("wellness"),
                "exercises": raw.get("exercises"),
                "planned_exercises": raw.get("planned_exercises"),
            })
        })
        .collect();
    let key = |value: &Value| {
        format!(
            "{}:{}",
            value["date"].as_str().unwrap_or_default(),
            value["id"].as_str().unwrap_or_default()
        )
    };
    dated.sort_by_key(key);
    let first = dated
        .iter()
        .filter_map(|session| session["date"].as_str())
        .find(|date| !date.is_empty());
    let last = dated
        .iter()
        .filter_map(|session| session["date"].as_str())
        .rfind(|date| !date.is_empty());
    let (block_notes, diet_notes) = match first.zip(last) {
        Some((start, end)) => (
            workspace.block_notes(start, end),
            workspace.diet_notes(start, end),
        ),
        None => (Vec::new(), Vec::new()),
    };
    let meta = workspace.meta();
    sha256_hex(&json!({
        "block": block,
        "block_start_maxes": manual_start_maxes(workspace, &block_key_for(block)),
        "meta": {
            "sex": meta.get("sex"),
            "manual_maxes": meta.get("manual_maxes"),
            "current_body_weight_kg": meta.get("current_body_weight_kg"),
            "target_squat_kg": meta.get("target_squat_kg"),
            "target_bench_kg": meta.get("target_bench_kg"),
            "target_dl_kg": meta.get("target_dl_kg"),
            "target_total_kg": meta.get("target_total_kg"),
        },
        "competitions": competitions,
        "goals": goals,
        "block_notes": block_notes,
        "diet_notes": diet_notes,
        "lift_profiles": workspace.root_list("lift_profiles"),
        "phases": phases,
        "sessions": dated,
    }))
}

fn phase_summary(phase: &Value) -> Value {
    let mut summary = serde_json::Map::new();
    for key in ["name", "intent", "start_week", "end_week"] {
        if let Some(value) = phase.get(key) {
            summary.insert(key.to_owned(), value.clone());
        }
    }
    Value::Object(summary)
}

fn label_of(workspace: &Workspace<'_>, block: &str, is_current: bool, start: &str) -> String {
    let record = workspace.block_record(block);
    let custom = |key: &str| {
        record
            .and_then(|map| map.get(key))
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|name| !name.is_empty() && name.to_lowercase() != "current")
            .map(str::to_owned)
    };
    custom("name")
        .or_else(|| custom("label"))
        .unwrap_or_else(|| {
            if is_current {
                "Current".to_owned()
            } else if start.is_empty() {
                format!("Block {block}")
            } else {
                start.to_owned()
            }
        })
}

pub fn build(workspace: &Workspace<'_>) -> Vec<BlockEntry> {
    let current = workspace.current_block_id();
    let mut groups: Vec<(String, Vec<&Session>)> = Vec::new();
    for session in &workspace.program.sessions {
        let block = normalize_block(&session.block);
        match groups.iter_mut().find(|(name, _)| *name == block) {
            Some((_, members)) => members.push(session),
            None => groups.push((block, vec![session])),
        }
    }
    let competitions: Vec<&Value> = workspace
        .program
        .competitions
        .iter()
        .map(|competition| &competition.raw)
        .collect();
    groups
        .into_iter()
        .map(|(block, mut sessions)| {
            sessions.sort_by(|a, b| a.date_text.cmp(&b.date_text));
            let dated: Vec<&&Session> = sessions
                .iter()
                .filter(|session| iso_date(&session.date_text).is_some())
                .collect();
            let start = dated
                .first()
                .map(|session| session.date_text.clone())
                .or_else(|| sessions.first().map(|session| session.date_text.clone()))
                .unwrap_or_default();
            let end = dated
                .last()
                .map(|session| session.date_text.clone())
                .or_else(|| sessions.last().map(|session| session.date_text.clone()))
                .unwrap_or_default();
            let weeks: Vec<i64> = sessions
                .iter()
                .map(|session| session.week_number.unwrap_or(0))
                .filter(|week| *week > 0)
                .collect();
            let week_start = weeks.iter().min().copied().unwrap_or(1);
            let week_end = weeks.iter().max().copied().unwrap_or(week_start);
            let phases = workspace.phases_of(&block);
            let block_key = block_key_for(&block);
            let linked = link_for_block(&start, &end, &competitions);
            let scoped = window(workspace, &start, &end, linked.as_ref());
            let scoped_goals = goals::for_competitions(&workspace.goals, &scoped);
            let source_fingerprint = fingerprint(
                workspace,
                &block,
                &sessions,
                &phases,
                &scoped,
                &scoped_goals,
            );
            let flags = data_quality(
                workspace,
                &sessions,
                &start,
                &end,
                linked.as_ref(),
                &block_key,
            );
            let comparison_eligible = linked
                .as_ref()
                .is_some_and(|link| has_results(results_of(&link.competition)));
            let is_current = current
                .as_deref()
                .is_some_and(|id| block == id || block == super::DEFAULT_BLOCK);
            let label = label_of(workspace, &block, is_current, &start);
            BlockEntry {
                block_key,
                label,
                is_current,
                start_date: start,
                end_date: end,
                week_start,
                week_end,
                week_count: (week_end - week_start + 1).max(1),
                completed_sessions: sessions.iter().filter(|s| s.completed).count() as i64,
                planned_sessions: sessions
                    .iter()
                    .filter(|s| !s.completed && s.status.as_deref() != Some("skipped"))
                    .count() as i64,
                total_sessions: sessions.len() as i64,
                phases: phases.iter().map(|phase| phase_summary(phase)).collect(),
                source_fingerprint,
                training_only: linked.is_none(),
                comparison_eligible,
                linked_competition: linked,
                data_quality_flags: flags,
                cache_status: None,
                stored: None,
                stored_at: None,
                block,
            }
        })
        .collect()
}
