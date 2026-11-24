use std::collections::HashMap;

use chrono::NaiveDate;
use serde_json::Value;

#[derive(Debug, PartialEq, Eq)]
pub struct MergeCounts {
    pub applied: usize,
    pub skipped: usize,
}

pub fn shift_dates(sessions: &mut [Value], start_date: Option<&str>) -> Result<(), String> {
    let Some(start_date) = start_date else {
        return Ok(());
    };
    if sessions.is_empty() {
        return Ok(());
    }
    let target = parse_date(start_date)?;
    let mut dates = Vec::with_capacity(sessions.len());
    for session in sessions.iter() {
        let date = session
            .get("date")
            .and_then(Value::as_str)
            .filter(|date| !date.is_empty());
        dates.push(date.map(parse_date).transpose()?);
    }
    let Some(first) = dates.iter().flatten().min() else {
        return Ok(());
    };
    let offset = target.signed_duration_since(*first);
    for (session, date) in sessions.iter_mut().zip(dates) {
        if let Some(date) = date {
            let shifted = date
                .checked_add_signed(offset)
                .ok_or("shifted date out of range")?;
            session["date"] = Value::String(shifted.format("%Y-%m-%d").to_string());
        }
    }
    Ok(())
}

fn parse_date(date: &str) -> Result<NaiveDate, String> {
    NaiveDate::parse_from_str(date, "%Y-%m-%d").map_err(|_| format!("invalid session date: {date}"))
}

pub fn merge_sessions(
    existing: &mut Vec<Value>,
    staged: Vec<Value>,
    strategy: &str,
    resolutions: &HashMap<String, String>,
) -> Result<MergeCounts, String> {
    let default_action = match strategy {
        "append" | "overwrite" => strategy,
        "overwrite_future" => "overwrite",
        "selective" => "skip",
        _ => return Err("invalid merge strategy".into()),
    };
    if resolutions.values().any(|action| {
        !matches!(
            action.as_str(),
            "skip" | "overwrite" | "merge" | "replace_planned" | "append"
        )
    }) {
        return Err("invalid conflict resolution".into());
    }
    let mut by_date = HashMap::new();
    for (index, session) in existing.iter().enumerate() {
        if let Some(date) = session
            .get("date")
            .and_then(Value::as_str)
            .filter(|date| !date.is_empty())
        {
            by_date.insert(date.to_owned(), index);
        }
    }
    let mut counts = MergeCounts {
        applied: 0,
        skipped: 0,
    };
    for session in staged {
        let Some(date) = session
            .get("date")
            .and_then(Value::as_str)
            .filter(|date| !date.is_empty())
            .map(str::to_owned)
        else {
            continue;
        };
        let Some(&index) = by_date.get(&date) else {
            by_date.insert(date, existing.len());
            existing.push(session);
            counts.applied += 1;
            continue;
        };
        let action = resolutions
            .get(&date)
            .map(String::as_str)
            .unwrap_or(default_action);
        match action {
            "skip" => counts.skipped += 1,
            "overwrite" | "replace_planned" => {
                let updates = session.as_object().ok_or("session must be an object")?;
                existing[index]
                    .as_object_mut()
                    .ok_or("session must be an object")?
                    .extend(updates.clone());
                counts.applied += 1;
            }
            "merge" | "append" => {
                for field in ["exercises", "planned_exercises"] {
                    let additions = match session.get(field) {
                        Some(value) => value
                            .as_array()
                            .ok_or("session exercises must be an array")?
                            .clone(),
                        None => Vec::new(),
                    };
                    let current = existing[index]
                        .as_object_mut()
                        .ok_or("session must be an object")?
                        .entry(field)
                        .or_insert_with(|| Value::Array(Vec::new()));
                    current
                        .as_array_mut()
                        .ok_or("session exercises must be an array")?
                        .extend(additions);
                }
                counts.applied += 1;
            }
            _ => unreachable!(),
        }
    }
    existing.sort_by(|left, right| {
        left.get("date")
            .and_then(Value::as_str)
            .unwrap_or("")
            .cmp(right.get("date").and_then(Value::as_str).unwrap_or(""))
    });
    Ok(counts)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn shifts_from_earliest_date_and_preserves_gaps() {
        let mut sessions = vec![
            json!({"date":"2026-09-03"}),
            json!({"date":"2026-09-01"}),
            json!({}),
        ];
        shift_dates(&mut sessions, Some("2026-09-20")).unwrap();
        assert_eq!(
            sessions,
            vec![
                json!({"date":"2026-09-22"}),
                json!({"date":"2026-09-20"}),
                json!({})
            ]
        );
    }

    #[test]
    fn merges_existing_and_new_dates_with_overrides() {
        let mut existing = vec![
            json!({"date":"2026-09-20", "exercises":[{"name":"Squat"}]}),
            json!({"date":"2026-09-21"}),
        ];
        let staged = vec![
            json!({"date":"2026-09-20", "exercises":[{"name":"Bench"}]}),
            json!({"date":"2026-09-21"}),
            json!({"date":"2026-09-22"}),
        ];
        let resolutions = HashMap::from([("2026-09-21".to_owned(), "skip".to_owned())]);
        let counts = merge_sessions(&mut existing, staged, "append", &resolutions).unwrap();
        assert_eq!(
            counts,
            MergeCounts {
                applied: 2,
                skipped: 1
            }
        );
        assert_eq!(
            existing[0]["exercises"],
            json!([{"name":"Squat"}, {"name":"Bench"}])
        );
        assert_eq!(existing.len(), 3);
    }

    #[test]
    fn invalid_dates_and_resolutions_are_rejected() {
        assert!(shift_dates(&mut [json!({"date":"not-a-date"})], Some("2026-09-20")).is_err());
        assert!(
            merge_sessions(
                &mut vec![],
                vec![],
                "append",
                &HashMap::from([("x".into(), "bad".into())])
            )
            .is_err()
        );
    }
}
