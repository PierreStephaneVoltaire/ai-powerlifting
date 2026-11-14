use chrono::NaiveDate;
use serde_json::{Map, Value};

use crate::model::{ProgramData, Session};

pub mod bundle;
pub mod competitions;
pub mod flags;
pub mod goals;
pub mod index;
pub mod outcome;
pub mod scope;
pub mod strength;
pub mod types;

use goals::Goal;
use types::BlockEntry;

pub const DEFAULT_BLOCK: &str = "current";

pub struct Workspace<'a> {
    pub program: &'a ProgramData,
    pub weight_log: &'a [Value],
    pub goals: Vec<Goal>,
    pub today: NaiveDate,
}

pub fn normalize_block(block: &str) -> String {
    let trimmed = block.trim();
    if trimmed.is_empty() {
        DEFAULT_BLOCK.to_owned()
    } else {
        trimmed.to_owned()
    }
}

pub fn block_key_for(block: &str) -> String {
    if block == DEFAULT_BLOCK {
        DEFAULT_BLOCK.to_owned()
    } else {
        format!("block_{}", crate::js::sha1_prefix(block, 14))
    }
}

pub fn is_completed(session: &Session) -> bool {
    session.completed
}

impl Workspace<'_> {
    pub fn meta(&self) -> &Map<String, Value> {
        &self.program.meta.map
    }

    pub fn sessions_of(&self, block: &str) -> Vec<&Session> {
        self.program
            .sessions
            .iter()
            .filter(|session| normalize_block(&session.block) == block)
            .collect()
    }

    pub fn phases_of(&self, block: &str) -> Vec<&Value> {
        self.root_list("phases")
            .iter()
            .filter(|phase| {
                normalize_block(
                    phase
                        .get("block")
                        .and_then(Value::as_str)
                        .unwrap_or_default(),
                ) == block
            })
            .collect()
    }

    pub fn root_list(&self, key: &str) -> &[Value] {
        self.program
            .root
            .get(key)
            .and_then(Value::as_array)
            .map_or(&[], Vec::as_slice)
    }

    pub fn current_block_id(&self) -> Option<String> {
        let meta = self.meta();
        if let Some(configured) = meta.get("current_block_id") {
            return configured.as_str().map(normalize_block);
        }
        if let Some(blocks) = meta.get("blocks").and_then(Value::as_array) {
            let active = blocks
                .iter()
                .find(|item| item.get("status").and_then(Value::as_str) == Some("active"))?;
            let id = active
                .get("id")
                .filter(|value| !value.is_null())
                .or_else(|| active.get("block_id"))
                .and_then(Value::as_str)
                .map(str::trim)
                .filter(|id| !id.is_empty())?;
            return Some(normalize_block(id));
        }
        Some(DEFAULT_BLOCK.to_owned())
    }

    pub fn block_record(&self, block: &str) -> Option<&Map<String, Value>> {
        self.meta()
            .get("blocks")
            .and_then(Value::as_array)?
            .iter()
            .filter_map(Value::as_object)
            .find(|candidate| {
                let id = candidate
                    .get("id")
                    .filter(|value| !value.is_null())
                    .or_else(|| candidate.get("block_id"));
                id.and_then(Value::as_str).unwrap_or_default() == block
            })
    }

    pub fn diet_notes(&self, start: &str, end: &str) -> Vec<&Value> {
        self.root_list("diet_notes")
            .iter()
            .filter(|note| {
                note.get("date")
                    .and_then(Value::as_str)
                    .is_some_and(|date| date >= start && date <= end)
            })
            .collect()
    }

    pub fn block_notes(&self, start: &str, end: &str) -> Vec<Value> {
        let mut notes: Vec<Value> = self
            .meta()
            .get("block_notes")
            .and_then(Value::as_array)
            .map_or(&[][..], Vec::as_slice)
            .iter()
            .filter_map(|note| {
                let map = note.as_object()?;
                let date = note_date(map);
                (date.as_str() >= start && date.as_str() <= end).then(|| {
                    let mut copy = map.clone();
                    copy.insert(
                        "date".to_owned(),
                        Value::String(if date.is_empty() {
                            start.to_owned()
                        } else {
                            date
                        }),
                    );
                    Value::Object(copy)
                })
            })
            .collect();
        notes.sort_by(|a, b| {
            a.get("date")
                .and_then(Value::as_str)
                .cmp(&b.get("date").and_then(Value::as_str))
        });
        notes
    }

    pub fn weight_entries(&self, start: &str, end: &str) -> Vec<Value> {
        let mut entries: Vec<&Value> = self
            .weight_log
            .iter()
            .filter(|entry| {
                let date = entry.get("date").and_then(Value::as_str);
                let kg = entry.get("kg").and_then(Value::as_f64);
                matches!((date, kg), (Some(date), Some(kg))
                    if kg.is_finite() && kg > 0.0 && date >= start && date <= end)
            })
            .collect();
        entries.sort_by(|a, b| {
            a.get("date")
                .and_then(Value::as_str)
                .cmp(&b.get("date").and_then(Value::as_str))
        });
        entries.into_iter().cloned().collect()
    }

    pub fn sex(&self) -> &'static str {
        if self.meta().get("sex").and_then(Value::as_str) == Some("female") {
            "female"
        } else {
            "male"
        }
    }

    pub fn entry_for(&self, key: &str, entries: &[BlockEntry]) -> Option<BlockEntry> {
        entries.iter().find(|entry| entry.block_key == key).cloned()
    }
}

fn note_date(map: &Map<String, Value>) -> String {
    let date = map.get("date").and_then(Value::as_str).unwrap_or_default();
    if !date.is_empty() {
        return date.to_owned();
    }
    map.get("updated_at")
        .and_then(Value::as_str)
        .map(|stamp| stamp.chars().take(10).collect())
        .unwrap_or_default()
}
