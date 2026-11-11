use std::cmp::Ordering;

use serde_json::{Map, Value, json};

use crate::error::Error;
use crate::model::{DEFAULT_BLOCK, Glossary, Meta, ProgramData, Session};
use crate::scope::{ALL_BLOCKS, BlockScope, block_key, record_day};
use crate::source::RawData;
use crate::util::{present, text, truthy_of};

const STRIPPED_SESSION_KEYS: [&str; 11] = [
    "pk",
    "sk",
    "entity_type",
    "source_pk",
    "source_table",
    "program_sk",
    "program_version",
    "program_version_number",
    "source_index",
    "same_day_ordinal",
    "phase_ref",
];

#[derive(Clone, Copy, Debug)]
pub enum Scope<'a> {
    Everything,
    Stored,
    Block(&'a str),
}

pub struct Loaded {
    pub program: ProgramData,
    pub glossary: Glossary,
    pub weight_log: Vec<Value>,
    pub goals: Vec<Value>,
}

fn int_value(value: Option<&Value>, default: i64) -> i64 {
    match value {
        Some(Value::Number(number)) => number
            .as_i64()
            .or_else(|| number.as_f64().map(|float| float.trunc() as i64))
            .unwrap_or(default),
        Some(Value::String(text)) => text.trim().parse().unwrap_or(default),
        _ => default,
    }
}

fn parse_week_number(session: &Map<String, Value>) -> i64 {
    let parsed = int_value(session.get("week_number"), -1);
    if parsed >= 0 {
        return parsed;
    }
    match session.get("week") {
        Some(Value::String(week)) => week
            .to_uppercase()
            .find('W')
            .and_then(|at| {
                let digits: String = week[at + 1..]
                    .chars()
                    .take_while(char::is_ascii_digit)
                    .collect();
                digits.parse().ok()
            })
            .unwrap_or(0),
        other => int_value(other, 0),
    }
}

fn unscheduled(week: i64, block: &str) -> Value {
    json!({
        "name": "Unscheduled",
        "intent": "",
        "start_week": week,
        "end_week": week,
        "block": block,
    })
}

fn resolve_phase(session: &Map<String, Value>, phases: &[Value]) -> Value {
    let week = parse_week_number(session);
    let block = match present(session.get("block")) {
        Some(Value::String(text)) if !text.is_empty() => text.clone(),
        _ => DEFAULT_BLOCK.to_owned(),
    };
    phases
        .iter()
        .filter_map(Value::as_object)
        .find(|phase| {
            let phase_block = match present(phase.get("block")) {
                Some(Value::String(text)) if !text.is_empty() => text.clone(),
                _ => DEFAULT_BLOCK.to_owned(),
            };
            phase_block == block
                && int_value(phase.get("start_week"), 0) <= week
                && week <= int_value(phase.get("end_week"), 0)
        })
        .map_or_else(
            || unscheduled(week, &block),
            |phase| Value::Object(phase.clone()),
        )
}

fn public_session(item: Value, phases: &[Value]) -> Value {
    let Value::Object(mut session) = item else {
        return item;
    };
    if session.contains_key("session_id") && !session.contains_key("id") {
        let id = text(&session, "session_id");
        session.insert("id".to_owned(), Value::String(id));
    }
    session.remove("session_id");
    for key in STRIPPED_SESSION_KEYS {
        session.remove(key);
    }
    let phase = resolve_phase(&session, phases);
    let week = parse_week_number(&session);
    let block = match present(session.get("block")) {
        Some(Value::String(text)) if !text.is_empty() => text.clone(),
        _ => DEFAULT_BLOCK.to_owned(),
    };
    let block_id = match present(session.get("block_id")) {
        Some(Value::String(text)) if !text.is_empty() => text.clone(),
        _ => block.clone(),
    };
    let phase_name = phase
        .get("name")
        .and_then(Value::as_str)
        .filter(|name| !name.is_empty())
        .unwrap_or("Unscheduled")
        .to_owned();
    session.insert("week_number".to_owned(), json!(week));
    session.insert("block".to_owned(), json!(block));
    session.insert("block_id".to_owned(), json!(block_id));
    session.insert("phase".to_owned(), phase);
    session.insert("phase_name".to_owned(), json!(phase_name));
    Value::Object(session)
}

fn field(item: &Value, key: &str) -> String {
    item.as_object()
        .map(|map| text(map, key))
        .unwrap_or_default()
}

fn session_order(a: &Value, b: &Value) -> Ordering {
    let key = |item: &Value| {
        (
            field(item, "date"),
            int_value(item.get("same_day_ordinal"), 0),
            int_value(item.get("source_index"), 0),
            field(item, "sk"),
        )
    };
    key(a).cmp(&key(b))
}

fn normalize_entries(entries: Vec<Value>) -> Vec<Value> {
    let mut normalized: Vec<Value> = entries
        .into_iter()
        .filter_map(|entry| {
            let Value::Object(source) = entry else {
                return None;
            };
            let status = ["user_status", "status"]
                .iter()
                .find(|key| truthy_of(source.get(**key)))
                .map(|key| source[*key].clone())?;
            if status == "available" {
                return None;
            }
            let mut current = source.clone();
            for key in ["pk", "sk", "test_seed_source_pk"] {
                current.remove(key);
            }
            let master = if truthy_of(source.get("master_id")) {
                source["master_id"].clone()
            } else {
                json!(text(&source, "sk").trim_start_matches("COMP#"))
            };
            let date = ["start_date", "date"]
                .iter()
                .find(|key| truthy_of(source.get(**key)))
                .map_or(Value::Null, |key| source[*key].clone());
            let federation = ["federation_label", "federation"]
                .iter()
                .find(|key| truthy_of(source.get(**key)))
                .map_or(Value::Null, |key| source[*key].clone());
            let units = if truthy_of(source.get("units")) {
                source["units"].clone()
            } else {
                json!("kg")
            };
            current.insert("master_id".to_owned(), master);
            current.insert("date".to_owned(), date);
            current.insert("status".to_owned(), status);
            current.insert("federation".to_owned(), federation);
            current.insert(
                "body_weight_kg".to_owned(),
                source.get("body_weight_kg").cloned().unwrap_or(Value::Null),
            );
            current.insert("units".to_owned(), units);
            Some(Value::Object(current))
        })
        .collect();
    normalized.sort_by_key(|entry| (field(entry, "date"), field(entry, "master_id")));
    normalized
}

fn scope_records(records: Vec<Value>, scope: &BlockScope, target: &str) -> Vec<Value> {
    records
        .into_iter()
        .filter(|record| {
            record
                .as_object()
                .is_some_and(|map| scope.record_block(record_day(map), &block_key(map)) == target)
        })
        .collect()
}

pub fn build(raw: RawData, mode: Scope<'_>) -> Result<Loaded, Error> {
    let RawData {
        mut program,
        sessions,
        competitions,
        glossary,
        weight_log,
        goals,
        ..
    } = raw;
    let Some(root) = program.as_object_mut() else {
        return Err(Error::NotFound("Program not found".to_owned()));
    };
    let scope = BlockScope::new(&Meta::from_value(root.get("meta")));
    let mut phases = root
        .remove("phases")
        .and_then(|phases| {
            if let Value::Array(items) = phases {
                Some(items)
            } else {
                None
            }
        })
        .unwrap_or_default();
    let mut competitions = match mode {
        Scope::Stored => match root.get_mut("competitions").map(Value::take) {
            Some(Value::Array(items)) => items,
            _ => Vec::new(),
        },
        _ => normalize_entries(competitions),
    };
    let target = match mode {
        Scope::Block(block) if block != ALL_BLOCKS => Some((block, scope.resolve(block))),
        _ => None,
    };
    if let Some((_, target)) = &target {
        phases = scope_records(phases, &scope, target);
        competitions = scope_records(competitions, &scope, target);
    }
    let mut items = sessions;
    items.sort_by(session_order);
    let mut public: Vec<Value> = items
        .into_iter()
        .map(|item| public_session(item, &phases))
        .collect();
    if let Some((block, target)) = &target {
        public.retain(|session| {
            session.as_object().is_some_and(|map| {
                let in_python_scope = scope.in_block(&block_key(map), block);
                in_python_scope && scope.record_block(record_day(map), &block_key(map)) == *target
            })
        });
    }
    root.insert("phases".to_owned(), Value::Array(phases));
    root.insert("competitions".to_owned(), Value::Array(competitions));
    let sessions = public.into_iter().map(Session::from_value).collect();
    Ok(Loaded {
        program: ProgramData::from_value(&program, sessions),
        glossary: Glossary::from_values(&take_list(glossary, "exercises")),
        weight_log: scoped_weight_log(
            take_list(weight_log, "entries"),
            &scope,
            target.as_ref().map(|(_, id)| id.as_str()),
        ),
        goals,
    })
}

fn take_list(mut item: Value, key: &str) -> Vec<Value> {
    match item.get_mut(key).map(Value::take) {
        Some(Value::Array(items)) => items,
        _ => Vec::new(),
    }
}

fn scoped_weight_log(entries: Vec<Value>, scope: &BlockScope, target: Option<&str>) -> Vec<Value> {
    match target {
        None => entries,
        Some(target) => scope_records(entries, scope, target),
    }
}

pub fn glossary(item: Value) -> Glossary {
    Glossary::from_values(&take_list(item, "exercises"))
}
