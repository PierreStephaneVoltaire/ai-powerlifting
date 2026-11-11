use serde_json::Value;

use crate::blocks::Workspace;
use crate::blocks::competitions;
use crate::blocks::goals::{self, Goal};
use crate::blocks::scope::{analysis_end, analysis_sessions, scoped_entry};
use crate::blocks::types::BlockEntry;
use crate::js::number;
use crate::model::Session;

pub struct Context {
    pub sessions: Vec<Session>,
    pub weight_log: Vec<Value>,
    pub competitions: Vec<Value>,
    pub goals: Vec<Goal>,
    pub sex: &'static str,
    pub fallback_bodyweight: Option<f64>,
}

pub fn build(workspace: &Workspace<'_>, raw: &BlockEntry) -> Context {
    let scoped = scoped_entry(workspace, raw);
    let window = competitions::window(
        workspace,
        &raw.start_date,
        &raw.end_date,
        raw.linked_competition.as_ref(),
    );
    let goals = goals::for_competitions(&workspace.goals, &window);
    let fallback = window
        .iter()
        .find_map(|competition| {
            number(competition.get("body_weight_kg")).filter(|kg| *kg > 0.0)
        })
        .or_else(|| number(workspace.meta().get("current_body_weight_kg")))
        .filter(|kg| *kg > 0.0);
    Context {
        sessions: analysis_sessions(workspace, &scoped, false),
        weight_log: workspace.weight_entries(&scoped.start_date, analysis_end(&scoped)),
        competitions: window.into_iter().cloned().collect(),
        goals,
        sex: workspace.sex(),
        fallback_bodyweight: fallback,
    }
}
