use serde::Serialize;
use serde_json::Value;
use utoipa::ToSchema;

use crate::js::{number, text};

const GOAL_TYPES: [&str; 8] = [
    "hit_total",
    "qualify_for_federation",
    "peak_for_meet",
    "conservative_pr",
    "competition_exposure",
    "improve_dots",
    "improve_ipf_gl",
    "custom",
];
const GOAL_PRIORITIES: [&str; 3] = ["primary", "secondary", "optional"];

#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct Goal {
    pub id: String,
    pub title: String,
    pub goal_type: String,
    pub priority: String,
    pub target_date: Option<String>,
    pub target_total_kg: Option<f64>,
    pub target_dots: Option<f64>,
    pub target_ipf_gl: Option<f64>,
}

fn positive(value: Option<&Value>) -> Option<f64> {
    number(value).filter(|number| *number > 0.0)
}

pub fn normalize(raw: &Value) -> Option<Goal> {
    let map = raw.as_object()?;
    let id = text(map, "id");
    let goal_type = text(map, "goal_type");
    let priority = text(map, "priority");
    Some(Goal {
        id: if id.is_empty() {
            "goal-unassigned".to_owned()
        } else {
            id.to_owned()
        },
        title: text(map, "title").to_owned(),
        goal_type: if GOAL_TYPES.contains(&goal_type) {
            goal_type.to_owned()
        } else {
            "custom".to_owned()
        },
        priority: if GOAL_PRIORITIES.contains(&priority) {
            priority.to_owned()
        } else {
            "secondary".to_owned()
        },
        target_date: Some(text(map, "target_date"))
            .filter(|date| !date.is_empty())
            .map(str::to_owned),
        target_total_kg: positive(map.get("target_total_kg")),
        target_dots: positive(map.get("target_dots")),
        target_ipf_gl: positive(map.get("target_ipf_gl")),
    })
}

pub fn normalize_all(raw: &[Value]) -> Vec<Goal> {
    raw.iter().filter_map(normalize).collect()
}

pub fn for_competitions(goals: &[Goal], competitions: &[&Value]) -> Vec<Goal> {
    let field = |key: &str| -> Vec<&str> {
        competitions
            .iter()
            .filter_map(|competition| competition.get(key).and_then(Value::as_str))
            .filter(|value| !value.trim().is_empty())
            .collect()
    };
    let dates = field("date");
    let names = field("name");
    if dates.is_empty() && names.is_empty() {
        return goals.to_vec();
    }
    goals
        .iter()
        .filter(|goal| {
            goal.target_date
                .as_deref()
                .map(str::trim)
                .is_some_and(|date| !date.is_empty() && dates.contains(&date))
        })
        .cloned()
        .collect()
}
