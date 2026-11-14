use serde_json::{Map, Value, json};

use crate::caller::Caller;
use crate::error::Error;
use crate::operations::{Operation, Ownership};

fn truthy(value: &Value) -> bool {
    match value {
        Value::Null => false,
        Value::Bool(flag) => *flag,
        Value::Number(number) => number.as_f64() != Some(0.0),
        Value::String(text) => !text.is_empty(),
        Value::Array(items) => !items.is_empty(),
        Value::Object(map) => !map.is_empty(),
    }
}

fn conflicts(arguments: &Map<String, Value>, key: &str, expected: &str) -> bool {
    arguments
        .get(key)
        .is_some_and(|value| truthy(value) && value.as_str() != Some(expected))
}

pub fn scope(
    operation: &Operation,
    arguments: &Map<String, Value>,
    caller: &Caller,
    access: &Value,
) -> Result<Map<String, Value>, Error> {
    if operation.ownership != Ownership::Public && caller.athlete.is_empty() {
        return Err(Error::Forbidden("Athlete scope required"));
    }
    let mut scoped = arguments.clone();
    if conflicts(&scoped, "actor_pk", &caller.person) {
        return Err(Error::Forbidden(
            "Acting Person differs from authenticated identity",
        ));
    }
    if scoped.contains_key("actor_pk") {
        scoped.insert("actor_pk".to_owned(), json!(caller.person));
    }
    let settings_pk = access
        .get("settings_pk")
        .and_then(Value::as_str)
        .unwrap_or_default();
    if conflicts(&scoped, "viewer_username", settings_pk) {
        return Err(Error::Forbidden("Viewer differs from authenticated Person"));
    }
    if operation.has_input("viewer_username") {
        if settings_pk.is_empty() {
            scoped.remove("viewer_username");
        } else {
            scoped.insert("viewer_username".to_owned(), json!(settings_pk));
        }
    }
    for key in ["pk", "user_pk", "mapped_pk", "_user_pk"] {
        if conflicts(&scoped, key, &caller.athlete) {
            return Err(Error::Forbidden(
                "Operation ownership conflicts with authenticated scope",
            ));
        }
    }
    if operation.ownership != Ownership::Public {
        scoped.insert("pk".to_owned(), json!(caller.athlete));
    }
    Ok(scoped)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn truthiness_follows_python() {
        assert!(!truthy(&json!("")));
        assert!(!truthy(&json!(0)));
        assert!(truthy(&json!("x")));
        assert!(!truthy(&Value::Null));
    }
}
