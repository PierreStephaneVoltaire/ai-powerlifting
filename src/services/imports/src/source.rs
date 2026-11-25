use aws_sdk_dynamodb::{Client, types::AttributeValue};
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet, HashSet};

type Result<T> = std::result::Result<T, Box<dyn std::error::Error + Send + Sync>>;

pub struct Source {
    pub db: Client,
    pub health: String,
    pub sessions: String,
    pub glossary: String,
}

impl Source {
    async fn get(&self, table: &str, pk: &str, sk: &str) -> Result<Option<Value>> {
        let result = self
            .db
            .get_item()
            .table_name(table)
            .key("pk", AttributeValue::S(pk.into()))
            .key("sk", AttributeValue::S(sk.into()))
            .send()
            .await?;
        Ok(result.item.map(serde_dynamo::from_item).transpose()?)
    }
    async fn query(&self, table: &str, pk: &str, prefix: &str) -> Result<Vec<Value>> {
        let mut result = Vec::new();
        let mut cursor = None;
        loop {
            let output = self
                .db
                .query()
                .table_name(table)
                .key_condition_expression("pk = :pk AND begins_with(sk, :prefix)")
                .expression_attribute_values(":pk", AttributeValue::S(pk.into()))
                .expression_attribute_values(":prefix", AttributeValue::S(prefix.into()))
                .set_exclusive_start_key(cursor)
                .send()
                .await?;
            for item in output.items.unwrap_or_default() {
                result.push(serde_dynamo::from_item(item)?);
            }
            cursor = output.last_evaluated_key.filter(|key| !key.is_empty());
            if cursor.is_none() {
                return Ok(result);
            }
        }
    }
    pub async fn glossary(&self, athlete: &str) -> Result<Vec<Value>> {
        let catalog = self.query(&self.glossary, "CATALOG", "EXERCISE#").await?;
        let overlay = self
            .query(&self.glossary, &format!("ATHLETE#{athlete}"), "EXERCISE#")
            .await?;
        Ok(merge_glossary(catalog, overlay))
    }
    pub async fn program_context(&self, athlete: &str) -> Result<Value> {
        let pointer = self.get(&self.health, athlete, "program#current").await?;
        let mut sk = pointer
            .as_ref()
            .and_then(|v| v.get("ref_sk"))
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_owned();
        if sk.is_empty() {
            let versions = self.query(&self.health, athlete, "program#").await?;
            sk = versions
                .iter()
                .filter(|item| item["published"] != false)
                .filter_map(|item| item.get("sk")?.as_str())
                .filter(|sk| *sk != "program#current")
                .max()
                .unwrap_or("")
                .to_owned();
        }
        if sk.is_empty() {
            return Err("program not found".into());
        }
        let program = self
            .get(&self.health, athlete, &sk)
            .await?
            .ok_or("program not found")?;
        if program["published"] == false {
            return Err("program not found".into());
        }
        let sessions = self
            .query(&self.sessions, athlete, &format!("session#{sk}#"))
            .await?;
        let weeks: HashSet<i64> = sessions
            .iter()
            .filter_map(session_week)
            .filter(|week| *week != 0)
            .collect();
        Ok(
            json!({"current_maxes":program.get("current_maxes").cloned().unwrap_or_else(|| json!({})), "current_program_weeks":weeks.len()}),
        )
    }
}

fn session_week(session: &Value) -> Option<i64> {
    fn number(value: &Value) -> Option<i64> {
        value
            .as_i64()
            .or_else(|| value.as_str().and_then(|s| s.parse().ok()))
    }
    if let Some(week) = session
        .get("week_number")
        .and_then(number)
        .filter(|week| *week >= 0)
    {
        return Some(week);
    }
    let week = session.get("week")?;
    if let Some(text) = week.as_str() {
        static WEEK: std::sync::OnceLock<regex::Regex> = std::sync::OnceLock::new();
        if let Some(value) = WEEK
            .get_or_init(|| regex::Regex::new(r"(?i)W(\d+)").unwrap())
            .captures(text)
            .and_then(|c| c.get(1))
            .and_then(|m| m.as_str().parse().ok())
        {
            return Some(value);
        }
    }
    number(week)
}

fn merge_glossary(catalog: Vec<Value>, overlay: Vec<Value>) -> Vec<Value> {
    let mut by_id: BTreeMap<String, (Option<Value>, Option<Value>)> = BTreeMap::new();
    for (items, personal) in [(catalog, false), (overlay, true)] {
        for item in items {
            let Some(id) = item
                .get("sk")
                .and_then(Value::as_str)
                .and_then(|sk| sk.strip_prefix("EXERCISE#"))
            else {
                continue;
            };
            let id = id.to_owned();
            let entry = by_id.entry(id).or_default();
            if personal {
                entry.1 = Some(item);
            } else {
                entry.0 = Some(item);
            }
        }
    }
    let fields: BTreeSet<&str> = "name category fatigue_category equipment video_url lift_transfer description how_to_perform why_do_it primary_muscles secondary_muscles tertiary_muscles fatigue_profile fatigue_profile_source fatigue_profile_reasoning e1rm_estimate archived custom".split_whitespace().collect();
    let mut result = Vec::new();
    for (id, (catalog, overlay)) in by_id {
        if overlay.as_ref().is_some_and(|v| v["hidden"] == true) {
            continue;
        }
        let mut entry = serde_json::Map::new();
        let exercise_id = overlay
            .as_ref()
            .and_then(|v| v.get("id"))
            .filter(|v| !v.is_null() && *v != "")
            .or_else(|| catalog.as_ref().and_then(|v| v.get("id")))
            .cloned()
            .unwrap_or_else(|| json!(id));
        for source in [catalog, overlay].into_iter().flatten() {
            if let Some(object) = source.as_object() {
                for (key, value) in object {
                    if fields.contains(key.as_str()) {
                        entry.insert(key.clone(), value.clone());
                    }
                }
            }
        }
        entry.insert("id".into(), exercise_id);
        result.push(Value::Object(entry));
    }
    result.sort_by_key(|item| item["name"].as_str().unwrap_or("").to_lowercase());
    result
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn merges_catalog_and_athlete_overlay_and_hides_items() {
        let catalog = vec![
            json!({"sk":"EXERCISE#1", "name":"Squat", "category":"squat"}),
            json!({"sk":"EXERCISE#2","name":"Bench"}),
        ];
        let overlay = vec![
            json!({"sk":"EXERCISE#1","name":"Personal Squat"}),
            json!({"sk":"EXERCISE#2","hidden":true}),
        ];
        let items = merge_glossary(catalog, overlay);
        assert_eq!(items.len(), 1);
        assert_eq!(items[0]["name"], "Personal Squat");
        assert_eq!(items[0]["category"], "squat");
        assert_eq!(items[0]["id"], "1");
    }

    #[test]
    fn reads_legacy_and_normal_week_numbers() {
        assert_eq!(session_week(&json!({"week_number":"3"})), Some(3));
        assert_eq!(session_week(&json!({"week":"W4D2"})), Some(4));
        assert_eq!(
            session_week(&json!({"week_number":0, "week":"W4"})),
            Some(0)
        );
    }
}
