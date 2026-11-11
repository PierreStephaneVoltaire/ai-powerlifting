use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};
use serde_json::Value;
use utoipa::ToSchema;

use crate::blocks::types::Flag;

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "camelCase")]
pub struct CompetitionSummary {
    pub name: String,
    pub date: String,
    pub status: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    #[schema(value_type = Option<String>)]
    pub federation: Option<Value>,
    pub weight_class_kg: Option<f64>,
    pub bodyweight_kg: Option<f64>,
    pub target_total_kg: Option<f64>,
    pub result_total_kg: Option<f64>,
    pub projected_total_kg: Option<f64>,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "camelCase")]
pub struct GoalSummary {
    pub id: String,
    pub title: String,
    pub goal_type: String,
    pub priority: String,
    pub target_total_kg: Option<f64>,
    pub target_dots: Option<f64>,
    pub target_ipf_gl: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub target_date: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "camelCase")]
pub struct Row {
    pub block_key: String,
    pub label: String,
    pub start_date: String,
    pub end_date: String,
    pub training_only: bool,
    pub competition_name: Option<String>,
    pub competition_date: Option<String>,
    pub actual_total_kg: Option<f64>,
    pub actual_dots: Option<f64>,
    pub actual_ipf_gl: Option<f64>,
    pub estimated_dots: Option<f64>,
    pub start_total_kg: Option<f64>,
    pub end_total_kg: Option<f64>,
    pub e1rm_delta_kg: Option<f64>,
    pub compliance_pct: Option<f64>,
    pub fatigue_index: Option<f64>,
    pub acwr_composite: Option<f64>,
    pub total_volume_kg: f64,
    pub avg_inol: BTreeMap<String, f64>,
    pub projection_total_delta_kg: Option<f64>,
    pub data_quality_flags: Vec<Flag>,
    pub competitions: Vec<CompetitionSummary>,
    pub goals: Vec<GoalSummary>,
}

#[derive(Debug, Clone, Serialize, ToSchema)]
#[serde(rename_all = "camelCase")]
pub struct Point {
    pub block_key: String,
    pub label: String,
    pub value: Option<f64>,
}

#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct Trends {
    #[serde(rename = "actualTotal")]
    pub actual_total: Vec<Point>,
    pub dots: Vec<Point>,
    #[serde(rename = "ipfGl")]
    pub ipf_gl: Vec<Point>,
    #[serde(rename = "e1rmTotal")]
    pub e1rm_total: Vec<Point>,
    pub compliance: Vec<Point>,
    pub fatigue: Vec<Point>,
    pub volume: Vec<Point>,
}

#[derive(Debug, Clone, Serialize, ToSchema)]
#[serde(rename_all = "camelCase")]
pub struct RoiSignal {
    pub lift: String,
    pub avg_inol_per_week: Option<f64>,
    pub avg_strength_delta_kg: Option<f64>,
    pub interpretation: String,
}

#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct Correlation {
    pub lift: String,
    pub direction: String,
    pub strength: String,
}

#[derive(Debug, Clone, Serialize, ToSchema)]
#[serde(rename_all = "camelCase")]
pub struct RoiBlock {
    pub block_key: String,
    pub label: String,
    pub sets: i64,
    pub volume_kg: i64,
    pub correlations: Vec<Correlation>,
    pub lift_deltas_kg: BTreeMap<String, Option<f64>>,
}

#[derive(Debug, Clone, Serialize, ToSchema)]
#[serde(rename_all = "camelCase")]
pub struct ExerciseRoi {
    pub exercise: String,
    pub block_count: i64,
    pub total_sets: i64,
    pub total_volume_kg: i64,
    pub correlated_lifts: Vec<String>,
    pub positive_signals: i64,
    pub negative_signals: i64,
    pub unclear_signals: i64,
    pub confidence: String,
    pub summary: String,
    pub blocks: Vec<RoiBlock>,
}

#[derive(Debug, Clone, Serialize, ToSchema)]
#[serde(rename_all = "camelCase")]
pub struct Finding {
    pub block_key: String,
    pub label: String,
    pub exercise: String,
    pub lift: String,
    pub direction: String,
    pub strength: String,
    pub reasoning: String,
    pub caveat: String,
}

#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct Pattern {
    pub kind: String,
    pub finding: String,
    pub evidence: String,
    pub confidence: String,
}

#[derive(Debug, Clone, Serialize, ToSchema)]
#[serde(rename_all = "camelCase")]
pub struct DoseResponse {
    pub block_key: String,
    pub label: String,
    pub lift: String,
    pub avg_inol: Option<f64>,
    pub raw_avg_inol: Option<f64>,
    pub sets: i64,
    pub volume_kg: i64,
    pub strength_delta_kg: Option<f64>,
    pub response_per_set_kg: Option<f64>,
    pub response_per1000_kg: Option<f64>,
}

#[derive(Debug, Clone, Serialize, ToSchema)]
#[serde(rename_all = "camelCase")]
pub struct TrainingDays {
    pub block_key: String,
    pub label: String,
    pub completed_weeks: i64,
    pub total_training_days: i64,
    pub avg_training_days_per_week: Option<f64>,
    pub strength_delta_kg: Option<f64>,
    pub compliance_pct: Option<f64>,
}

#[derive(Debug, Clone, Serialize, ToSchema)]
#[serde(rename_all = "camelCase")]
pub struct TrendPoint {
    pub block_key: String,
    pub label: String,
    pub week_number: i64,
    pub week_start: String,
    pub squat_kg: Option<f64>,
    pub bench_kg: Option<f64>,
    pub deadlift_kg: Option<f64>,
    pub e1rm_total_kg: Option<f64>,
    pub estimated_dots: Option<f64>,
    pub volume_kg: i64,
    pub training_days: i64,
    pub strain: Option<f64>,
}

#[derive(Debug, Clone, Serialize, ToSchema)]
#[serde(rename_all = "camelCase")]
pub struct ToleranceLift {
    pub best_observed_avg_inol: Option<f64>,
    pub positive_delta_blocks: i64,
}

#[derive(Debug, Clone, Serialize, ToSchema)]
#[serde(rename_all = "camelCase")]
pub struct Tolerance {
    pub status: String,
    pub confidence: String,
    pub sample_size: i64,
    pub required_sample_size: i64,
    pub message: String,
    pub by_lift: BTreeMap<String, ToleranceLift>,
}

#[derive(Debug, Clone, Serialize, ToSchema)]
#[serde(rename_all = "camelCase")]
pub struct MissingData {
    pub block_key: String,
    pub label: String,
    pub flags: Vec<Flag>,
}

#[derive(Debug, Clone, Serialize, ToSchema)]
#[serde(rename_all = "camelCase")]
pub struct Comparison {
    pub schema_version: i64,
    pub generated_at: String,
    pub selected_block_keys: Vec<String>,
    pub rows: Vec<Row>,
    pub trends: Trends,
    pub roi_signals: Vec<RoiSignal>,
    pub exercise_roi: Vec<ExerciseRoi>,
    pub correlation_findings: Vec<Finding>,
    pub pattern_signals: Vec<Pattern>,
    pub lift_dose_response: Vec<DoseResponse>,
    pub training_day_response: Vec<TrainingDays>,
    pub trend_series: Vec<TrendPoint>,
    pub volume_tolerance: Tolerance,
    pub missing_data_summary: Vec<MissingData>,
}
