use serde_json::{Value, json};

pub fn payload(parsed: &Value, pending: &Value, overrides: Option<&Value>) -> Value {
    let mut sessions = parsed
        .get("sessions")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    for session in &mut sessions {
        let Some(session) = session.as_object_mut() else {
            continue;
        };
        session.remove("date");
        let Some(exercises) = session.get_mut("exercises").and_then(Value::as_array_mut) else {
            continue;
        };
        for exercise in exercises.iter_mut().filter_map(Value::as_object_mut) {
            if let Some(id) = exercise
                .get("name")
                .and_then(Value::as_str)
                .and_then(|name| overrides.and_then(|map| map.get(name)))
                .and_then(Value::as_str)
                .filter(|id| !id.is_empty())
            {
                exercise.insert("glossary_id".into(), json!(id));
            }
            let timed = exercise
                .get("rep_unit")
                .and_then(Value::as_str)
                .is_some_and(|unit| unit == "seconds" || unit == "minutes")
                || exercise
                    .get("duration_minutes")
                    .is_some_and(|value| !value.is_null());
            let load_missing = exercise
                .get("load_type")
                .and_then(Value::as_str)
                .is_none_or(|load| {
                    !matches!(
                        load.to_ascii_lowercase().as_str(),
                        "rpe" | "percentage" | "absolute" | "duration"
                    )
                })
                || exercise
                    .get("load_value")
                    .is_none_or(|value| value.is_null() || value == "");
            let has_reps = exercise
                .get("reps")
                .is_some_and(|value| !value.is_null() && value != 0 && value != "")
                || exercise.get("rep_mode").is_some_and(|mode| mode == "amrap");
            let has_sets = exercise
                .get("sets")
                .is_some_and(|value| !value.is_null() && value != 0 && value != "");
            if load_missing && has_reps && has_sets && !timed {
                let target = exercise
                    .get("rpe_target")
                    .filter(|value| !value.is_null() && **value != 0)
                    .cloned()
                    .unwrap_or(json!(8));
                exercise.insert("load_type".into(), json!("rpe"));
                exercise.insert("load_value".into(), target.clone());
                exercise.insert("rpe_target".into(), target);
            }
        }
    }
    json!({"meta":{
        "name":parsed.get("program_name"), "description":"", "program_context":"",
        "source_filename":pending.get("source_filename"), "source_file_hash":pending.get("source_file_hash")
    }, "phases":parsed.get("phases").cloned().unwrap_or_else(|| json!([])), "sessions":sessions})
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn template_drops_dates_defaults_lifting_load_and_retains_timed_work() {
        let parsed = json!({"program_name":"Example", "sessions":[{"date":"2026-09-20", "exercises":[
            {"name":"Squat","sets":3,"reps":5}, {"name":"Plank","sets":2,"reps":30,"rep_unit":"seconds"},
            {"name":"Bench","sets":2,"reps":4,"load_type":"absolute","load_value":100}
        ]}]});
        let result = payload(
            &parsed,
            &json!({"source_filename":"test.csv"}),
            Some(&json!({"Squat":"g1"})),
        );
        assert!(result["sessions"][0].get("date").is_none());
        assert_eq!(result["sessions"][0]["exercises"][0]["load_value"], 8);
        assert_eq!(result["sessions"][0]["exercises"][0]["glossary_id"], "g1");
        assert!(
            result["sessions"][0]["exercises"][1]
                .get("load_type")
                .is_none()
        );
        assert_eq!(result["sessions"][0]["exercises"][2]["load_value"], 100);
    }
}
