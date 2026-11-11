use std::collections::HashMap;

use chrono::NaiveDate;
use serde::{Serialize, Serializer};
use serde_json::{Map, Value};

use crate::util::{int_of, num, num_of, parse_date, present, text, truthy_of};

pub const DEFAULT_BLOCK: &str = "current";

#[derive(Debug)]
pub struct Exercise {
    pub name: String,
    pub lower: String,
    pub key: String,
    pub kg: f64,
    pub reps: f64,
    pub declared_sets: f64,
    pub rpe: Option<f64>,
    statuses: Vec<String>,
}

impl Exercise {
    fn from_value(value: &Value) -> Self {
        let name = value
            .get("name")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_owned();
        let lower = name.to_lowercase();
        let key = lower.trim().to_owned();
        let statuses = value
            .get("set_statuses")
            .and_then(Value::as_array)
            .map(|items| {
                items
                    .iter()
                    .map(|item| item.as_str().unwrap_or_default().to_owned())
                    .collect()
            })
            .unwrap_or_default();
        Self {
            name,
            lower,
            key,
            kg: num_of(value.get("kg")),
            reps: num_of(value.get("reps")),
            declared_sets: num_of(value.get("sets")),
            rpe: present(value.get("rpe")).map(num),
            statuses,
        }
    }

    pub fn failed_sets(&self) -> i64 {
        self.statuses
            .iter()
            .filter(|status| status.as_str() == "failed")
            .count() as i64
    }

    pub fn executed_sets(&self) -> f64 {
        if self.statuses.is_empty() {
            return self.declared_sets;
        }
        self.statuses
            .iter()
            .filter(|status| matches!(status.as_str(), "completed" | "failed"))
            .count() as f64
    }

    pub fn executed_volume(&self) -> f64 {
        self.executed_sets() * self.reps * self.kg
    }

    pub fn reps_int(&self) -> i64 {
        int_of(self.reps)
    }

    pub fn sets_int(&self) -> i64 {
        int_of(self.executed_sets())
    }
}

#[derive(Debug)]
pub struct Session {
    pub raw: Value,
    pub date_text: String,
    pub date: Option<NaiveDate>,
    pub week_number: Option<i64>,
    pub completed: bool,
    pub status: Option<String>,
    pub session_rpe: Option<f64>,
    pub body_weight_kg: Option<f64>,
    pub block: String,
    pub block_key: String,
    pub exercises: Vec<Exercise>,
    pub wellness: Vec<f64>,
    pub inferred_skipped: bool,
}

impl Serialize for Session {
    fn serialize<S: Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        self.raw.serialize(serializer)
    }
}

fn week_of(value: Option<&Value>) -> Option<i64> {
    match present(value)? {
        Value::Number(number) => number
            .as_i64()
            .or_else(|| number.as_f64().map(|float| float.trunc() as i64)),
        Value::String(text) => text.trim().parse().ok(),
        Value::Bool(flag) => Some(i64::from(*flag)),
        _ => None,
    }
}

impl Session {
    pub fn from_value(raw: Value) -> Self {
        let date_text = raw
            .get("date")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_owned();
        let status = present(raw.get("status"))
            .and_then(Value::as_str)
            .map(str::to_owned);
        let completed = truthy_of(raw.get("completed"))
            || matches!(status.as_deref(), Some("logged" | "completed"));
        let block = match present(raw.get("block")) {
            Some(Value::String(text)) if !text.is_empty() => text.clone(),
            _ => String::new(),
        };
        let block_id = match present(raw.get("block_id")) {
            Some(Value::String(text)) if !text.is_empty() => text.clone(),
            _ => String::new(),
        };
        let block_key = if block_id.is_empty() {
            block.clone()
        } else {
            block_id
        };
        let exercises = raw
            .get("exercises")
            .and_then(Value::as_array)
            .map(|items| items.iter().map(Exercise::from_value).collect())
            .unwrap_or_default();
        let wellness = raw
            .get("wellness")
            .and_then(Value::as_object)
            .map(|map| {
                ["sleep", "soreness", "mood", "stress", "energy"]
                    .iter()
                    .filter_map(|key| present(map.get(*key)))
                    .map(num)
                    .filter(|value| (1.0..=5.0).contains(value))
                    .collect()
            })
            .unwrap_or_default();
        Self {
            date: parse_date(&date_text),
            date_text,
            week_number: week_of(raw.get("week_number")),
            completed,
            status,
            session_rpe: present(raw.get("session_rpe")).map(num),
            body_weight_kg: present(raw.get("body_weight_kg")).map(num),
            block,
            block_key,
            exercises,
            wellness,
            inferred_skipped: truthy_of(raw.get("_inferred_skipped")),
            raw,
        }
    }

    pub fn week(&self, program_start: &str) -> Option<i64> {
        if self.week_number.is_some() {
            return self.week_number;
        }
        let start = parse_date(program_start)?;
        let date = self.date?;
        Some(((date - start).num_days().div_euclid(7) + 1).max(1))
    }

    pub fn planned_exercises(&self) -> &[Value] {
        self.raw
            .get("planned_exercises")
            .and_then(Value::as_array)
            .map_or(&[], Vec::as_slice)
    }

    pub fn exercise_values(&self) -> &[Value] {
        self.raw
            .get("exercises")
            .and_then(Value::as_array)
            .map_or(&[], Vec::as_slice)
    }
}

#[derive(Debug, Clone, Default)]
pub struct Phase {
    pub name: String,
    pub intent: String,
    pub block: String,
    pub start_week: f64,
    pub end_week: f64,
    pub target_rpe_min: Option<f64>,
    pub target_rpe_max: Option<f64>,
}

impl Phase {
    pub fn from_value(value: &Value) -> Option<Self> {
        let map = value.as_object()?;
        Some(Self {
            name: text(map, "name"),
            intent: text(map, "intent"),
            block: text(map, "block"),
            start_week: num_of(map.get("start_week")),
            end_week: num_of(map.get("end_week")),
            target_rpe_min: present(map.get("target_rpe_min")).map(num),
            target_rpe_max: present(map.get("target_rpe_max")).map(num),
        })
    }

    pub fn target_midpoint(&self) -> Option<f64> {
        Some((self.target_rpe_min? + self.target_rpe_max?) / 2.0)
    }

    pub fn text(&self) -> String {
        format!("{} {}", self.name, self.intent).to_lowercase()
    }
}

#[derive(Debug)]
pub struct Competition {
    pub raw: Value,
    pub date_text: String,
    pub date: Option<NaiveDate>,
    pub status: String,
    pub name: Option<String>,
    pub notes: String,
    pub results: Option<Map<String, Value>>,
    pub block_key: String,
}

impl Competition {
    pub fn from_value(raw: Value) -> Self {
        let map = raw.as_object().cloned().unwrap_or_default();
        let date_text = text(&map, "date");
        Self {
            date: parse_date(&date_text),
            date_text,
            status: text(&map, "status"),
            name: present(map.get("name")).map(|value| {
                value
                    .as_str()
                    .map_or_else(|| value.to_string(), str::to_owned)
            }),
            notes: text(&map, "notes"),
            results: map.get("results").and_then(Value::as_object).cloned(),
            block_key: crate::scope::block_key(&map),
            raw,
        }
    }

    pub fn result_kg(&self, key: &str) -> Option<f64> {
        present(self.results.as_ref()?.get(key)).map(num)
    }

    pub fn prr_total(&self) -> Option<f64> {
        let prr = self.results.as_ref()?.get("prr")?.as_object()?;
        present(prr.get("total")).map(num)
    }

    pub fn qualifying_total(&self) -> Option<f64> {
        let totals = self.raw.get("qualifying_totals")?.as_object()?;
        let total = num_of(totals.get("total_kg"));
        (total > 0.0).then(|| crate::util::round(total, 1))
    }
}

#[derive(Debug, Default)]
pub struct LiftProfile {
    pub lift: String,
    pub stimulus_coefficient: Option<f64>,
    pub e1rm_multiplier: Option<f64>,
    pub inol_low_threshold: Option<f64>,
    pub inol_high_threshold: Option<f64>,
}

impl LiftProfile {
    pub fn from_value(value: &Value) -> Option<Self> {
        let map = value.as_object()?;
        Some(Self {
            lift: text(map, "lift").to_lowercase().trim().to_owned(),
            stimulus_coefficient: present(map.get("stimulus_coefficient")).map(num),
            e1rm_multiplier: map.get("e1rm_multiplier").map(num),
            inol_low_threshold: present(map.get("inol_low_threshold")).map(num),
            inol_high_threshold: present(map.get("inol_high_threshold")).map(num),
        })
    }
}

#[derive(Debug)]
pub struct BlockMeta {
    pub id: String,
    pub status: String,
    pub start_date: String,
    pub completed_at: String,
    pub week_start_day: Option<String>,
}

#[derive(Debug, Default)]
pub struct Meta {
    pub map: Map<String, Value>,
    pub blocks: Vec<BlockMeta>,
}

impl Meta {
    pub fn from_value(value: Option<&Value>) -> Self {
        let map = value
            .and_then(Value::as_object)
            .cloned()
            .unwrap_or_default();
        let blocks = map
            .get("blocks")
            .and_then(Value::as_array)
            .map(|items| {
                items
                    .iter()
                    .filter_map(Value::as_object)
                    .map(|block| BlockMeta {
                        id: block_id(block),
                        status: text(block, "status"),
                        start_date: text(block, "start_date"),
                        completed_at: text(block, "completed_at"),
                        week_start_day: block
                            .get("week_start_day")
                            .and_then(Value::as_str)
                            .map(str::to_owned),
                    })
                    .collect()
            })
            .unwrap_or_default();
        Self { map, blocks }
    }

    pub fn program_start(&self) -> String {
        text(&self.map, "program_start")
    }

    pub fn get(&self, key: &str) -> Option<&Value> {
        self.map.get(key)
    }
}

fn block_id(block: &Map<String, Value>) -> String {
    let id = text(block, "id");
    if id.is_empty() {
        text(block, "block_id")
    } else {
        id
    }
}

#[derive(Debug, Default)]
pub struct Glossary {
    entries: HashMap<String, GlossaryEntry>,
    categories: HashMap<String, String>,
    count: usize,
}

#[derive(Debug)]
pub struct GlossaryEntry {
    pub profile: Option<[f64; 4]>,
    pub e1rm: Option<f64>,
    pub category: String,
}

impl Glossary {
    pub fn from_values(items: &[Value]) -> Self {
        let mut glossary = Self {
            count: items.len(),
            ..Self::default()
        };
        for item in items.iter().filter_map(Value::as_object) {
            let key = text(item, "name").to_lowercase().trim().to_owned();
            let entry = GlossaryEntry::from_map(item);
            glossary
                .categories
                .insert(key.clone(), text(item, "category"));
            glossary.entries.entry(key).or_insert(entry);
        }
        glossary
    }

    pub fn is_empty(&self) -> bool {
        self.count == 0
    }

    pub fn entry(&self, key: &str) -> Option<&GlossaryEntry> {
        self.entries.get(key)
    }

    pub fn category(&self, key: &str) -> &str {
        self.categories.get(key).map_or("", String::as_str)
    }
}

impl GlossaryEntry {
    fn from_map(map: &Map<String, Value>) -> Self {
        let profile = map
            .get("fatigue_profile")
            .and_then(Value::as_object)
            .and_then(|profile| {
                Some([
                    num(profile.get("axial")?),
                    num(profile.get("neural")?),
                    num(profile.get("peripheral")?),
                    num(profile.get("systemic")?),
                ])
            });
        let raw = map.get("e1rm_estimate").or_else(|| map.get("e1rm"));
        let e1rm = raw.and_then(|value| match value {
            Value::Object(inner) => ["kg", "e1rm_kg", "estimate_kg", "value_kg"]
                .iter()
                .filter_map(|key| inner.get(*key))
                .find(|candidate| crate::util::truthy(candidate))
                .map(num),
            other => crate::util::truthy(other).then(|| num(other)),
        });
        let category = match map.get("category") {
            None => "isolation".to_owned(),
            Some(_) => text(map, "category"),
        };
        Self {
            profile,
            e1rm: e1rm.filter(|value| *value > 0.0),
            category,
        }
    }
}

#[derive(Debug, Default, Clone, Copy, PartialEq)]
pub struct Maxes {
    pub squat: Option<f64>,
    pub bench: Option<f64>,
    pub deadlift: Option<f64>,
}

impl Maxes {
    pub fn is_empty(&self) -> bool {
        self.squat.is_none() && self.bench.is_none() && self.deadlift.is_none()
    }

    pub fn get(&self, lift: Lift) -> Option<f64> {
        match lift {
            Lift::Squat => self.squat,
            Lift::Bench => self.bench,
            Lift::Deadlift => self.deadlift,
        }
    }

    pub fn set(&mut self, lift: Lift, value: f64) {
        match lift {
            Lift::Squat => self.squat = Some(value),
            Lift::Bench => self.bench = Some(value),
            Lift::Deadlift => self.deadlift = Some(value),
        }
    }

    pub fn by_name(&self, key: &str) -> Option<f64> {
        Lift::from_name(key).and_then(|lift| self.get(lift))
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub enum Lift {
    Squat,
    Bench,
    Deadlift,
}

impl Lift {
    pub const ALL: [Self; 3] = [Self::Squat, Self::Bench, Self::Deadlift];

    pub fn from_name(key: &str) -> Option<Self> {
        match key {
            "squat" => Some(Self::Squat),
            "bench press" | "bench" => Some(Self::Bench),
            "deadlift" => Some(Self::Deadlift),
            _ => None,
        }
    }

    pub fn key(self) -> &'static str {
        match self {
            Self::Squat => "squat",
            Self::Bench => "bench",
            Self::Deadlift => "deadlift",
        }
    }
}

#[derive(Debug, Default)]
pub struct ProgramData {
    pub meta: Meta,
    pub phases: Vec<Phase>,
    pub competitions: Vec<Competition>,
    pub lift_profiles: Vec<LiftProfile>,
    pub sessions: Vec<Session>,
    pub settings_sex: String,
    pub root: Map<String, Value>,
}

static EMPTY: std::sync::LazyLock<ProgramData> = std::sync::LazyLock::new(ProgramData::default);

impl ProgramData {
    pub fn empty() -> &'static Self {
        &EMPTY
    }

    pub fn from_value(program: &Value, sessions: Vec<Session>) -> Self {
        let list = |key: &str| {
            program
                .get(key)
                .and_then(Value::as_array)
                .map_or(&[][..], Vec::as_slice)
        };
        let settings_sex = program
            .get("settings")
            .and_then(Value::as_object)
            .map(|settings| text(settings, "sex"))
            .unwrap_or_default();
        Self {
            meta: Meta::from_value(program.get("meta")),
            phases: list("phases")
                .iter()
                .filter_map(Phase::from_value)
                .collect(),
            competitions: list("competitions")
                .iter()
                .cloned()
                .map(Competition::from_value)
                .collect(),
            lift_profiles: list("lift_profiles")
                .iter()
                .filter_map(LiftProfile::from_value)
                .collect(),
            sessions,
            settings_sex,
            root: program.as_object().cloned().unwrap_or_default(),
        }
    }
}
