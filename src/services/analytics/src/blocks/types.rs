use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use utoipa::ToSchema;

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema, PartialEq)]
pub struct Flag {
    pub code: String,
    pub label: String,
    pub severity: String,
}

impl Flag {
    pub fn warning(code: &str, label: &str) -> Self {
        Self::with(code, label, "warning")
    }

    pub fn info(code: &str, label: &str) -> Self {
        Self::with(code, label, "info")
    }

    pub fn critical(code: &str, label: &str) -> Self {
        Self::with(code, label, "critical")
    }

    fn with(code: &str, label: &str, severity: &str) -> Self {
        Self {
            code: code.to_owned(),
            label: label.to_owned(),
            severity: severity.to_owned(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "camelCase")]
pub struct Link {
    pub name: String,
    pub date: String,
    pub status: String,
    pub mapping: String,
    pub distance_days: i64,
    #[schema(value_type = Object)]
    pub competition: Value,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "camelCase")]
pub struct CacheStatus {
    pub cached: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub generated_at: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "camelCase")]
pub struct BlockEntry {
    pub block_key: String,
    pub block: String,
    pub label: String,
    pub is_current: bool,
    pub start_date: String,
    pub end_date: String,
    pub week_start: i64,
    pub week_end: i64,
    pub week_count: i64,
    pub completed_sessions: i64,
    pub planned_sessions: i64,
    pub total_sessions: i64,
    #[schema(value_type = Vec<Object>)]
    pub phases: Vec<Value>,
    pub source_fingerprint: String,
    pub linked_competition: Option<Link>,
    pub training_only: bool,
    pub comparison_eligible: bool,
    pub data_quality_flags: Vec<Flag>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub cache_status: Option<CacheStatus>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub stored: Option<bool>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub stored_at: Option<String>,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize, ToSchema, PartialEq)]
pub struct Strength {
    pub squat: Option<f64>,
    pub bench: Option<f64>,
    pub deadlift: Option<f64>,
    pub total: Option<f64>,
}

impl Strength {
    pub fn lift(&self, lift: &str) -> Option<f64> {
        match lift {
            "squat" => self.squat,
            "bench" => self.bench,
            "deadlift" => self.deadlift,
            _ => self.total,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct StartMaxes {
    pub squat_kg: Option<f64>,
    pub bench_kg: Option<f64>,
    pub deadlift_kg: Option<f64>,
    pub total_kg: Option<f64>,
    pub source: String,
    pub updated_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "camelCase")]
pub struct Outcome {
    pub competition_name: String,
    pub competition_date: String,
    pub bodyweight_kg: Option<f64>,
    #[schema(value_type = Option<Object>)]
    pub results: Option<Value>,
    pub dots: Option<f64>,
    pub ipf_gl: Option<f64>,
    pub ipf_gl_mode: Option<String>,
    #[schema(value_type = Option<Object>)]
    pub projected_at_t_minus1w: Option<Value>,
    #[schema(value_type = Option<Object>)]
    pub projection_accuracy: Option<Map<String, Value>>,
    #[schema(value_type = Option<Object>)]
    pub prr: Option<Value>,
    pub post_meet_report_captured: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "camelCase")]
pub struct Summary {
    pub sessions_analyzed: f64,
    pub compliance_pct: Option<f64>,
    pub fatigue_index: Option<f64>,
    pub acwr_composite: Option<f64>,
    pub avg_inol: std::collections::BTreeMap<String, f64>,
    pub total_volume_kg: f64,
    #[schema(value_type = Object)]
    pub muscle_map: Value,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "camelCase")]
pub struct Historical {
    pub start_strength: Strength,
    pub end_strength: Strength,
    pub strength_delta: Strength,
    pub start_maxes_source: String,
    pub manual_start_maxes: Option<StartMaxes>,
    pub competition_outcome: Option<Outcome>,
    pub analytics_summary: Summary,
    pub missing_data: Vec<Flag>,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "camelCase")]
pub struct Bundle {
    pub schema_version: i64,
    pub generated_at: String,
    pub cached: bool,
    pub source_fingerprint: String,
    pub block: BlockEntry,
    #[schema(value_type = Object)]
    pub weekly: Value,
    pub historical: Historical,
}
