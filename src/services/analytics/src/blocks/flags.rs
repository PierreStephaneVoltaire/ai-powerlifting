use serde_json::Value;

use super::Workspace;
use super::competitions::{flag_truthy, has_results, results_of};
use super::strength::{self, manual_start_maxes};
use super::types::{Flag, Link};
use crate::js::truthy;
use crate::model::Session;

fn sparse(sessions: &[&Session], present: impl Fn(&Session) -> bool) -> bool {
    !sessions.is_empty()
        && (sessions.iter().filter(|session| present(session)).count() as f64)
            / (sessions.len() as f64)
            < 0.5
}

fn incomplete_profile(workspace: &Workspace<'_>, lift: &str) -> bool {
    let profile = workspace
        .root_list("lift_profiles")
        .iter()
        .find(|entry| entry.get("lift").and_then(Value::as_str) == Some(lift));
    let Some(profile) = profile else {
        return true;
    };
    let options = profile
        .get("options")
        .and_then(Value::as_object)
        .is_some_and(|map| !map.is_empty());
    profile
        .get("stimulus_coefficient")
        .is_none_or(Value::is_null)
        || !options
        || !truthy(profile.get("volume_tolerance"))
}

pub fn data_quality(
    workspace: &Workspace<'_>,
    sessions: &[&Session],
    start: &str,
    end: &str,
    linked: Option<&Link>,
    block_key: &str,
) -> Vec<Flag> {
    let mut flags = Vec::new();
    let completed: Vec<&Session> = sessions
        .iter()
        .copied()
        .filter(|session| session.completed)
        .collect();
    match linked {
        None => flags.push(Flag::info(
            "training_only",
            "No completed competition linked",
        )),
        Some(link) => {
            let competition = &link.competition;
            if !has_results(results_of(competition)) {
                flags.push(Flag::critical(
                    "missing_comp_results",
                    "Missing competition results",
                ));
            }
            let bodyweight = competition
                .get("body_weight_kg")
                .and_then(Value::as_f64)
                .unwrap_or(0.0);
            if bodyweight <= 0.0 {
                flags.push(Flag::warning(
                    "missing_comp_bodyweight",
                    "Missing competition bodyweight",
                ));
            }
            if !flag_truthy(competition, "post_meet_report") {
                flags.push(Flag::warning(
                    "missing_post_meet_report",
                    "Missing post-meet report",
                ));
            }
            let nested =
                results_of(competition).and_then(|results| results.get("projected_at_t_minus_1w"));
            if !flag_truthy(competition, "projected_at_t_minus_1w") && !truthy(nested) {
                flags.push(Flag::warning(
                    "missing_t_minus_1_projection",
                    "Missing T-minus-1 projection",
                ));
            }
            if !truthy(results_of(competition).and_then(|results| results.get("prr"))) {
                flags.push(Flag::warning("missing_prr", "Missing PRR calibration"));
            }
        }
    }
    let manual = manual_start_maxes(workspace, block_key);
    let summary = strength::estimate(sessions, start, end, manual.as_ref());
    if summary.start.squat.is_none()
        || summary.start.bench.is_none()
        || summary.start.deadlift.is_none()
    {
        flags.push(Flag::warning(
            "missing_start_maxes",
            "Missing complete start maxes",
        ));
    }
    if !completed.is_empty() {
        if sparse(&completed, |session| {
            session
                .raw
                .get("body_weight_kg")
                .and_then(Value::as_f64)
                .is_some_and(|kg| kg > 0.0)
        }) {
            flags.push(Flag::info("sparse_bodyweight", "Sparse bodyweight logging"));
        }
        if sparse(&completed, |session| truthy(session.raw.get("wellness"))) {
            flags.push(Flag::info("sparse_wellness", "Sparse wellness logging"));
        }
    }
    if workspace.diet_notes(start, end).is_empty() {
        flags.push(Flag::info("sparse_diet", "No diet notes inside block"));
    }
    if strength::LIFTS
        .iter()
        .any(|lift| incomplete_profile(workspace, lift))
    {
        flags.push(Flag::info(
            "missing_glossary_fatigue_metadata",
            "Missing muscle or fatigue metadata",
        ));
    }
    flags
}
