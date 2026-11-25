use std::collections::HashMap;

use jsonschema::Validator;
use serde::Deserialize;
use serde_json::{Map, Value, json};

use crate::identity::Identity;

#[derive(Deserialize)]
struct Record {
    name: String,
    description: String,
    input_schema: Value,
    result_schema: Value,
    execution: String,
}

pub struct Operation {
    pub name: String,
    pub description: String,
    pub input_schema: Value,
    pub result_schema: Value,
    pub ai: bool,
    input: Validator,
    result: Validator,
}

pub struct Registry {
    pub operations: HashMap<String, Operation>,
}

fn conflicts(value: Option<&Value>, expected: &str) -> bool {
    match value {
        None | Some(Value::Null) | Some(Value::Bool(false)) => false,
        Some(Value::String(value)) => !value.is_empty() && value != expected,
        Some(Value::Number(value)) => value.as_f64() != Some(0.0),
        Some(Value::Array(value)) => !value.is_empty(),
        Some(Value::Object(value)) => !value.is_empty(),
        Some(Value::Bool(true)) => true,
    }
}

impl Registry {
    pub fn load() -> Result<Self, String> {
        let records: Vec<Record> =
            serde_json::from_str(include_str!("../../operations/imports.json"))
                .map_err(|e| format!("{e}"))?;
        let permissions: Value =
            serde_json::from_str(include_str!("../../runtime/permissions.json"))
                .map_err(|e| format!("{e}"))?;
        let mut operations = HashMap::new();
        for record in records {
            if permissions.get(&record.name).is_none() {
                return Err(format!("No permission mapping for {}", record.name));
            }
            let compile = |schema: &Value| {
                jsonschema::draft202012::options()
                    .should_validate_formats(true)
                    .build(schema)
                    .map_err(|e| format!("{e}"))
            };
            let operation = Operation {
                input: compile(&record.input_schema)?,
                result: compile(&record.result_schema)?,
                name: record.name,
                description: record.description,
                input_schema: record.input_schema,
                result_schema: record.result_schema,
                ai: record.execution == "ai",
            };
            if operations
                .insert(operation.name.clone(), operation)
                .is_some()
            {
                return Err("duplicate operation".into());
            }
        }
        Ok(Self { operations })
    }
}

impl Operation {
    pub fn scope(
        &self,
        mut args: Map<String, Value>,
        identity: &Identity,
    ) -> Result<Map<String, Value>, String> {
        if identity.person.is_empty() || identity.athlete.is_empty() {
            return Err("Person and Athlete required".into());
        }
        if ["_person_pk", "_access", "_if_job_id"]
            .iter()
            .any(|key| args.contains_key(*key))
        {
            return Err("Reserved authorization fields cannot be supplied".into());
        }
        if conflicts(args.get("actor_pk"), &identity.person) {
            return Err("Acting Person differs from authenticated identity".into());
        }
        if args.contains_key("actor_pk") {
            args.insert("actor_pk".into(), json!(identity.person));
        }
        for key in ["pk", "user_pk", "mapped_pk", "_user_pk"] {
            if conflicts(args.get(key), &identity.athlete) {
                return Err("Operation ownership conflicts with authenticated scope".into());
            }
        }
        args.insert("pk".into(), json!(identity.athlete));
        self.input
            .validate(&Value::Object(args.clone()))
            .map_err(|e| format!("{e}"))?;
        Ok(args)
    }

    pub fn validate_result(&self, value: &Value) -> Result<(), String> {
        self.result.validate(value).map_err(|e| format!("{e}"))
    }
}

pub async fn authorize(
    client: &reqwest::Client,
    profile_url: &str,
    operation: &str,
    args: &Map<String, Value>,
    identity: &Identity,
) -> Result<Value, String> {
    if identity.person.is_empty() {
        return Err("Person required".into());
    }
    let response = client
        .post(format!(
            "{}/operations/access_context",
            profile_url.trim_end_matches('/')
        ))
        .header("X-Person-Pk", &identity.person)
        .header("X-Athlete-Pk", &identity.athlete)
        .timeout(std::time::Duration::from_secs(10))
        .json(&json!({"operation": operation, "arguments": args}))
        .send()
        .await
        .map_err(|_| "access unavailable")?;
    if !response.status().is_success() {
        return Err("access denied".into());
    }
    response
        .json()
        .await
        .map_err(|_| "access unavailable".into())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn scopes_athlete_and_rejects_forged_or_invalid_fields() {
        let registry = Registry::load().unwrap();
        let op = &registry.operations["import_list"];
        let identity = Identity {
            person: "person".into(),
            athlete: "athlete".into(),
            source: String::new(),
        };
        let empty = Map::new();
        assert_eq!(op.scope(empty, &identity).unwrap()["pk"], "athlete");
        assert!(
            op.scope(
                json!({"pk":"other"}).as_object().unwrap().clone(),
                &identity
            )
            .is_err()
        );
        assert!(
            op.scope(
                json!({"_person_pk":"other"}).as_object().unwrap().clone(),
                &identity
            )
            .is_err()
        );
        assert!(
            op.scope(json!({"limit":501}).as_object().unwrap().clone(), &identity)
                .is_err()
        );
    }
}
