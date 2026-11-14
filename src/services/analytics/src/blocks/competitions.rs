use chrono::{Duration, NaiveDate};
use serde_json::Value;

use super::Workspace;
use super::types::Link;
use crate::js::{coerce_number, iso_date, truthy};

pub fn has_results(results: Option<&Value>) -> bool {
    results
        .and_then(Value::as_object)
        .is_some_and(|map| coerce_number(map.get("total_kg")) > 0.0)
}

pub fn results_of(competition: &Value) -> Option<&Value> {
    competition.get("results").filter(|value| !value.is_null())
}

fn str_field<'a>(competition: &'a Value, key: &str) -> &'a str {
    competition
        .get(key)
        .and_then(Value::as_str)
        .unwrap_or_default()
}

pub fn link_for_block(start: &str, end: &str, competitions: &[&Value]) -> Option<Link> {
    let (start, end) = (iso_date(start)?, iso_date(end)?);
    let completed: Vec<(&Value, NaiveDate)> = competitions
        .iter()
        .copied()
        .filter(|competition| str_field(competition, "status") == "completed")
        .filter_map(|competition| {
            iso_date(str_field(competition, "date")).map(|date| (competition, date))
        })
        .collect();
    let in_range: Vec<(&Value, i64, &str)> = completed
        .iter()
        .filter(|(_, date)| *date >= start && *date <= end)
        .map(|(competition, date)| (*competition, (end - *date).num_days().abs(), "in_range"))
        .collect();
    let after_end = end + Duration::days(30);
    let after: Vec<(&Value, i64, &str)> = completed
        .iter()
        .filter(|(_, date)| *date > end && *date <= after_end)
        .map(|(competition, date)| {
            (
                *competition,
                (*date - end).num_days(),
                "within_30_days_after",
            )
        })
        .collect();
    let mut candidates = if in_range.is_empty() { after } else { in_range };
    candidates.sort_by_key(|candidate| candidate.1);
    let (competition, distance, mapping) = candidates.into_iter().next()?;
    Some(Link {
        name: str_field(competition, "name").to_owned(),
        date: str_field(competition, "date").to_owned(),
        status: str_field(competition, "status").to_owned(),
        mapping: mapping.to_owned(),
        distance_days: distance,
        competition: competition.clone(),
    })
}

pub fn window<'a>(
    workspace: &'a Workspace<'_>,
    start: &str,
    end: &str,
    linked: Option<&'a Link>,
) -> Vec<&'a Value> {
    let start = iso_date(start);
    let end = iso_date(linked.map_or(end, |link| link.date.as_str()));
    let mut keyed: Vec<(String, &Value)> = Vec::new();
    let mut put = |key: String, value: &'a Value| match keyed.iter_mut().find(|(k, _)| *k == key) {
        Some(slot) => slot.1 = value,
        None => keyed.push((key, value)),
    };
    if let (Some(start), Some(end)) = (start, end) {
        for competition in &workspace.program.competitions {
            let Some(date) = iso_date(str_field(&competition.raw, "date")) else {
                continue;
            };
            if date < start || date > end {
                continue;
            }
            put(key_of(&competition.raw), &competition.raw);
        }
    }
    if let Some(link) = linked {
        put(key_of(&link.competition), &link.competition);
    }
    let mut values: Vec<&Value> = keyed.into_iter().map(|(_, value)| value).collect();
    values.sort_by(|a, b| str_field(a, "date").cmp(str_field(b, "date")));
    values
}

fn key_of(competition: &Value) -> String {
    format!(
        "{}:{}",
        str_field(competition, "date"),
        str_field(competition, "name")
    )
}

pub fn flag_truthy(competition: &Value, key: &str) -> bool {
    truthy(competition.get(key))
}
