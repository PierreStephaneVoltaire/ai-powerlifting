use serde::Deserialize;
use utoipa::ToSchema;
use serde_json::{Map, Value};

use crate::error::Error;

pub fn parse<T: for<'de> Deserialize<'de>>(arguments: Map<String, Value>) -> Result<T, Error> {
    serde_json::from_value(Value::Object(arguments))
        .map_err(|error| Error::Validation(error.to_string()))
}

fn default_weeks() -> i64 {
    1
}

fn default_block() -> String {
    "current".to_owned()
}

fn default_drift_weeks() -> i64 {
    4
}

#[derive(Debug, Deserialize, ToSchema)]
pub struct SectionArgs {
    pub pk: String,
    #[serde(default)]
    pub section: String,
    #[serde(default = "default_weeks")]
    pub weeks: i64,
    #[serde(default = "default_block")]
    pub block: String,
    pub window_start: Option<String>,
    pub window_end: Option<String>,
    pub ref_date: Option<String>,
    pub week_start: Option<i64>,
    pub week_end: Option<i64>,
    #[schema(value_type = Option<Object>)]
    pub program: Option<Value>,
    #[schema(value_type = Option<Vec<Object>>)]
    pub sessions: Option<Value>,
}

#[derive(Debug, Deserialize, ToSchema)]
pub struct ExerciseArgs {
    pub pk: String,
    pub exercise_name: String,
    #[serde(default = "default_drift_weeks")]
    pub window_weeks: i64,
    #[schema(value_type = Option<Object>)]
    pub program: Option<Value>,
    #[schema(value_type = Option<Vec<Object>>)]
    pub sessions: Option<Value>,
    pub reference_date: Option<String>,
    pub ref_date: Option<String>,
}

#[derive(Debug, Deserialize, ToSchema)]
pub struct SuggestArgs {
    pub pk: String,
    #[schema(value_type = Option<Object>)]
    pub program: Option<Value>,
    #[schema(value_type = Option<Vec<Object>>)]
    pub max_history: Option<Vec<Value>>,
    pub reference_date: Option<String>,
}

#[derive(Debug, Deserialize, ToSchema)]
#[serde(rename_all = "camelCase")]
pub struct WindowArgs {
    pub pk: String,
    pub as_of_date: Option<String>,
    pub window: Option<String>,
    pub section_key: Option<String>,
    pub sections: Option<Vec<String>>,
    pub windows: Option<Vec<String>>,
    pub refresh: Option<bool>,
}

#[derive(Debug, Deserialize, ToSchema)]
#[serde(rename_all = "camelCase")]
pub struct WeeklyArgs {
    pub pk: String,
    #[serde(default = "default_weeks")]
    pub weeks: i64,
    #[serde(default = "default_block")]
    pub block: String,
    pub window_start: Option<String>,
    pub window_end: Option<String>,
    pub ref_date: Option<String>,
    pub week_start: Option<i64>,
    pub week_end: Option<i64>,
}

#[derive(Debug, Deserialize, ToSchema)]
pub struct PkArgs {
    pub pk: String,
}

#[derive(Debug, Deserialize, ToSchema)]
#[serde(rename_all = "camelCase")]
pub struct BlockArgs {
    pub pk: String,
    pub block_key: String,
    pub refresh: Option<bool>,
    pub cache_only: Option<bool>,
}

#[derive(Debug, Deserialize, ToSchema)]
#[serde(rename_all = "camelCase")]
pub struct CompareArgs {
    pub pk: String,
    pub block_keys: Option<Vec<String>>,
}

#[derive(Debug, Deserialize, ToSchema)]
pub struct LifetimeArgs {
    pub pk: String,
    pub refresh: Option<bool>,
    pub cache_only: Option<bool>,
}
