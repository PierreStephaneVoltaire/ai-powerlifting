use std::collections::{HashMap, HashSet};

use regex::Regex;
use serde_json::{Value, json};

fn key(text: &str) -> String {
    text.split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
        .to_lowercase()
}

fn canonical(name: &str) -> String {
    let words: Vec<String> = name
        .to_lowercase()
        .split(|c: char| !c.is_ascii_alphanumeric())
        .filter(|word| !word.is_empty())
        .map(str::to_owned)
        .collect();
    let (lift, used) = if words.first().is_some_and(|w| w == "bench")
        && words.get(1).is_some_and(|w| w == "press")
    {
        ("Bench Press", 2)
    } else if words.first().is_some_and(|w| w == "bench") {
        ("Bench Press", 1)
    } else if words.first().is_some_and(|w| w == "squat") {
        ("Squat", 1)
    } else if words.first().is_some_and(|w| w == "deadlift") {
        ("Deadlift", 1)
    } else {
        return name.trim().to_owned();
    };
    let allowed = [
        "heavy",
        "light",
        "single",
        "singles",
        "double",
        "triple",
        "backoff",
        "backoffs",
        "back",
        "off",
        "top",
        "set",
        "test",
        "deload",
        "opener",
        "second",
        "third",
        "attempt",
        "work",
        "working",
        "volume",
        "intensity",
        "comp",
        "competition",
    ];
    if words[used..]
        .iter()
        .all(|word| allowed.contains(&word.as_str()) || word.chars().all(|ch| ch.is_ascii_digit()))
    {
        lift.to_owned()
    } else {
        name.trim().to_owned()
    }
}

fn token_score(a: &str, b: &str) -> f64 {
    fn sorted(value: &str) -> Vec<char> {
        let value = value.to_lowercase();
        let mut tokens = value.split_whitespace().collect::<Vec<_>>();
        tokens.sort_unstable();
        tokens.join(" ").chars().collect()
    }
    let left = sorted(a);
    let right = sorted(b);
    if left.is_empty() && right.is_empty() {
        return 1.0;
    }
    if 2 * left.len().min(right.len()) * 100 < 92 * (left.len() + right.len()) {
        return 0.0;
    }
    let mut prev = vec![0usize; right.len() + 1];
    for a in &left {
        let mut next = vec![0usize; right.len() + 1];
        for (index, b) in right.iter().enumerate() {
            next[index + 1] = if a == b {
                prev[index] + 1
            } else {
                prev[index + 1].max(next[index])
            };
        }
        prev = next;
    }
    (2 * prev[right.len()]) as f64 / (left.len() + right.len()) as f64
}

fn unilateral(name: &str) -> bool {
    static UNILATERAL: std::sync::OnceLock<Regex> = std::sync::OnceLock::new();
    UNILATERAL
        .get_or_init(|| {
            Regex::new(r"(?i)\b(?:unilateral|(?:single|one)[ -]?(?:arm|leg))\b").unwrap()
        })
        .is_match(name)
}

fn row_value<'a>(row: &'a Value, names: &[&str]) -> Option<&'a Value> {
    let row = row.as_object()?;
    row.iter()
        .find(|(key, _)| {
            let norm = key.to_lowercase().replace(['_', '-'], " ");
            let norm = norm.split_whitespace().collect::<Vec<_>>().join(" ");
            names.iter().any(|candidate| norm == *candidate)
        })
        .map(|(_, value)| value)
}

fn row_context(row: &Value) -> (Option<String>, Option<String>) {
    let week = row_value(
        row,
        &["week number", "week", "training week", "relative week"],
    )
    .and_then(|v| {
        v.as_i64().map(|n| n.to_string()).or_else(|| {
            v.as_str()
                .and_then(|s| s.parse::<i64>().ok())
                .map(|n| n.to_string())
        })
    })
    .or_else(|| {
        static WEEK: std::sync::OnceLock<Regex> = std::sync::OnceLock::new();
        let pattern = WEEK.get_or_init(|| Regex::new(r"(?i)\bweek\s*#?\s*(\d+)\b").unwrap());
        row_value(row, &["sheet"])
            .and_then(Value::as_str)
            .and_then(|sheet| pattern.captures(sheet))
            .and_then(|captures| captures.get(1))
            .map(|week| week.as_str().to_owned())
    });
    let day = row_value(row, &["day of week", "day", "weekday"])
        .and_then(Value::as_str)
        .map(key)
        .filter(|s| !s.is_empty());
    (week, day)
}

pub fn reconcile(parsed: &mut Value, rows: &[Value], glossary: &[Value], template: bool) {
    let mut source = Vec::new();
    for row in rows {
        let Some(name) = row_value(row, &["exercise", "exercise name", "lift", "movement"])
            .and_then(Value::as_str)
            .filter(|v| !v.is_empty())
        else {
            continue;
        };
        let Some(note) = row_value(row, &["exercise notes", "notes", "note"])
            .and_then(Value::as_str)
            .filter(|v| !v.is_empty())
        else {
            continue;
        };
        let (week, day) = row_context(row);
        source.push((
            HashSet::from([key(name), key(&canonical(name))]),
            week,
            day,
            note.to_owned(),
        ));
    }
    let mut exercises = Vec::new();
    let sessions = parsed.get_mut("sessions").and_then(Value::as_array_mut);
    if let Some(sessions) = sessions {
        for (session_index, session) in sessions.iter_mut().enumerate() {
            let (week, day) = row_context(session);
            if let Some(items) = session.get_mut("exercises").and_then(Value::as_array_mut) {
                for (exercise_index, item) in items.iter_mut().enumerate() {
                    let Some(object) = item.as_object_mut() else {
                        continue;
                    };
                    let name = object
                        .get("name")
                        .and_then(Value::as_str)
                        .unwrap_or("")
                        .trim()
                        .to_owned();
                    let normalized = canonical(&name);
                    object.insert("name".into(), json!(normalized));
                    object.insert("notes".into(), json!(""));
                    exercises.push((
                        session_index,
                        exercise_index,
                        HashSet::from([key(&name), key(&normalized)]),
                        week.clone(),
                        day.clone(),
                    ));
                }
            }
        }
        let mut notes: HashMap<usize, Vec<String>> = HashMap::new();
        for (names, week, day, note) in source {
            let matches = exercises
                .iter()
                .enumerate()
                .filter(|(_, (_, _, candidate, cw, cd))| {
                    !names.is_disjoint(candidate)
                        && (week.is_none() || week == *cw)
                        && (day.is_none() || day == *cd)
                })
                .map(|(i, _)| i)
                .collect::<Vec<_>>();
            if matches.len() == 1 {
                notes.entry(matches[0]).or_default().push(note);
            }
        }
        for (index, values) in notes {
            if values.len() == 1 {
                let (session, exercise, ..) = exercises[index];
                sessions[session]["exercises"][exercise]["notes"] = json!(values[0]);
            }
        }
        for session in sessions.iter_mut() {
            let Some(items) = session.get_mut("exercises").and_then(Value::as_array_mut) else {
                continue;
            };
            for item in items {
                let Some(object) = item.as_object_mut() else {
                    continue;
                };
                let name = object
                    .get("name")
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .trim()
                    .to_owned();
                let proposed = object.remove("glossary_id");
                let best = glossary
                    .iter()
                    .filter_map(|entry| {
                        let candidate = entry.get("name")?.as_str()?;
                        let id = entry.get("id")?.as_str()?;
                        Some((token_score(&name, candidate), candidate, id))
                    })
                    .max_by(|a, b| a.0.total_cmp(&b.0));
                let resolved = best.filter(|(score, _, _)| *score >= 0.92);
                let exact = glossary.iter().find(|entry| {
                    entry
                        .get("name")
                        .and_then(Value::as_str)
                        .is_some_and(|candidate| candidate.eq_ignore_ascii_case(&name))
                        && entry.get("id").and_then(Value::as_str).is_some()
                });
                if template {
                    let suggested = proposed
                        .as_ref()
                        .and_then(Value::as_str)
                        .and_then(|id| glossary.iter().find(|entry| entry["id"] == id));
                    let selected = exact
                        .or_else(|| {
                            suggested.filter(|entry| {
                                entry["name"].as_str().is_some_and(|candidate| {
                                    unilateral(&name) == unilateral(candidate)
                                })
                            })
                        })
                        .or_else(|| {
                            resolved.and_then(|(_, candidate, id)| {
                                if unilateral(&name) == unilateral(candidate) {
                                    glossary.iter().find(|entry| entry["id"] == id)
                                } else {
                                    None
                                }
                            })
                        });
                    if let Some(entry) = selected {
                        object.insert("glossary_id".into(), entry["id"].clone());
                        object.insert("name".into(), entry["name"].clone());
                    }
                } else if let Some((_, _, id)) = resolved {
                    object.insert("glossary_id".into(), json!(id));
                }
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn notes_require_unambiguous_source_and_suggested_ids_cannot_change_variation() {
        let rows = vec![json!({"week":1,"day":"Monday","exercise":"Bench heavy","notes":"Pause"})];
        let glossary = vec![
            json!({"id":"bench","name":"Bench Press"}),
            json!({"id":"single","name":"Single Arm Row"}),
        ];
        let mut parsed = json!({"sessions":[{"week":1,"day":"Monday","exercises":[{"name":"Bench heavy","notes":"invented"},{"name":"Barbell Row","glossary_id":"single"}]}]});
        reconcile(&mut parsed, &rows, &glossary, true);
        assert_eq!(parsed["sessions"][0]["exercises"][0]["notes"], "Pause");
        assert_eq!(
            parsed["sessions"][0]["exercises"][0]["glossary_id"],
            "bench"
        );
        assert!(
            parsed["sessions"][0]["exercises"][1]
                .get("glossary_id")
                .is_none()
        );
    }
}
