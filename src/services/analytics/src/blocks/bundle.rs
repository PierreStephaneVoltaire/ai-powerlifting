use std::collections::BTreeMap;

use serde_json::Value;

use super::Workspace;
use super::outcome::{projection_results, summarize};
use super::scope::{
    analysis_end, analysis_sessions, program_for_block, projection_reference, scoped_entry,
};
use super::strength::{estimate, manual_start_maxes};
use super::types::{BlockEntry, Bundle, CacheStatus, Historical, Summary};
use crate::calc::Env;
use crate::error::Error;
use crate::js::{number, round_digits};
use crate::records::timestamp;
use crate::sections::{self, Params};
use crate::windows::CACHE_SCHEMA_VERSION;

pub fn summary_from_weekly(weekly: &Value) -> Summary {
    let at = |path: &str| weekly.pointer(path);
    let total_volume: f64 = at("/exercise_stats")
        .and_then(Value::as_object)
        .map_or(0.0, |stats| {
            stats
                .values()
                .filter_map(|entry| entry.get("total_volume").and_then(Value::as_f64))
                .sum()
        });
    let avg_inol: BTreeMap<String, f64> = at("/inol/avg_inol")
        .and_then(Value::as_object)
        .map(|map| {
            map.iter()
                .filter_map(|(lift, value)| Some((lift.clone(), value.as_f64()?)))
                .collect()
        })
        .unwrap_or_default();
    let muscle = at("/muscle_volume/muscles")
        .filter(|value| value.is_object())
        .cloned()
        .unwrap_or_else(|| Value::Object(serde_json::Map::new()));
    Summary {
        sessions_analyzed: weekly
            .get("sessions_analyzed")
            .and_then(Value::as_f64)
            .unwrap_or(0.0),
        compliance_pct: number(at("/compliance/pct")),
        fatigue_index: number(weekly.get("fatigue_index")),
        acwr_composite: number(at("/acwr/composite")),
        avg_inol,
        total_volume_kg: round_digits(total_volume, 0),
        muscle_map: muscle,
    }
}

pub fn historical(workspace: &Workspace<'_>, entry: &BlockEntry, weekly: &Value) -> Historical {
    let sessions = analysis_sessions(workspace, entry, true);
    let refs: Vec<&crate::model::Session> = sessions.iter().collect();
    let manual = manual_start_maxes(workspace, &entry.block_key);
    let strength = estimate(
        &refs,
        &entry.start_date,
        analysis_end(entry),
        manual.as_ref(),
    );
    let fallback = projection_results(weekly, entry.linked_competition.as_ref());
    Historical {
        start_strength: strength.start,
        end_strength: strength.end,
        strength_delta: strength.delta,
        start_maxes_source: if strength.manual {
            "manual"
        } else {
            "session_estimated"
        }
        .to_owned(),
        manual_start_maxes: manual,
        competition_outcome: summarize(
            workspace.sex(),
            entry.linked_competition.as_ref(),
            fallback,
        ),
        analytics_summary: summary_from_weekly(weekly),
        missing_data: entry.data_quality_flags.clone(),
    }
}

pub fn compute(workspace: &Workspace<'_>, env: Env<'_>, raw: &BlockEntry) -> Result<Bundle, Error> {
    let entry = scoped_entry(workspace, raw);
    let (program, _) = program_for_block(workspace, &entry);
    let reference = projection_reference(&entry);
    let params = Params {
        weeks: entry.week_count,
        block: Some(entry.block.clone()),
        window_start: Some(entry.start_date.clone()),
        window_end: Some(reference.clone()),
        ref_date: Some(reference),
        week_start: Some(entry.week_start),
        week_end: Some(entry.week_end),
        ..Params::default()
    };
    let weekly = Value::Object(sections::compute_all(env, &program, &params)?);
    let now = timestamp();
    let historical = historical(workspace, &entry, &weekly);
    Ok(Bundle {
        schema_version: CACHE_SCHEMA_VERSION,
        generated_at: now.clone(),
        cached: false,
        source_fingerprint: entry.source_fingerprint.clone(),
        block: BlockEntry {
            cache_status: Some(CacheStatus {
                cached: true,
                generated_at: Some(now),
            }),
            ..entry
        },
        weekly,
        historical,
    })
}
