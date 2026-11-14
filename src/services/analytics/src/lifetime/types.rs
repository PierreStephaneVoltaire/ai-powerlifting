use std::collections::BTreeMap;

use serde::Serialize;
use utoipa::ToSchema;

use crate::blocks::types::Flag;
use crate::compare::types::{DoseResponse, ExerciseRoi, Pattern, TrainingDays};

#[derive(Debug, Clone, Default, Serialize, ToSchema)]
pub struct Bands {
    pub heavy_pct: Option<f64>,
    pub moderate_pct: Option<f64>,
    pub light_pct: Option<f64>,
}

#[derive(Debug, Clone, Default, Serialize, ToSchema)]
pub struct LiftExposure {
    pub weekly_hard_sets: f64,
    pub weekly_tonnage_kg: f64,
    pub weekly_frequency: f64,
    pub avg_rpe: Option<f64>,
    pub avg_inol: Option<f64>,
    pub peak_inol: Option<f64>,
    pub total_sets: f64,
    pub intensity_bands: Bands,
}

#[derive(Debug, Clone, Default, Serialize, ToSchema)]
pub struct CategoryExposure {
    pub weekly_hard_sets: f64,
    pub weekly_tonnage_kg: f64,
    pub weekly_frequency: f64,
    pub avg_rpe: Option<f64>,
    pub total_sets: f64,
}

#[derive(Debug, Clone, Default, Serialize, ToSchema)]
pub struct DimensionStat {
    pub axial: Option<f64>,
    pub neural: Option<f64>,
    pub peripheral: Option<f64>,
    pub systemic: Option<f64>,
}

#[derive(Debug, Clone, Default, Serialize, ToSchema)]
pub struct Fatigue {
    pub index: Option<f64>,
    pub dimension_mean: DimensionStat,
    pub dimension_peak: DimensionStat,
}

#[derive(Debug, Clone, Default, Serialize, ToSchema)]
pub struct Spread {
    pub mean: Option<f64>,
    pub peak: Option<f64>,
}

#[derive(Debug, Clone, Default, Serialize, ToSchema)]
pub struct Deload {
    pub weeks: Vec<i64>,
    pub break_weeks: Vec<i64>,
    pub count: i64,
    pub per_10_weeks: f64,
    pub positions: Vec<f64>,
    pub placement: String,
}

#[derive(Debug, Clone, Default, Serialize, ToSchema)]
pub struct Specificity {
    pub broad: Option<f64>,
    pub narrow: Option<f64>,
}

#[derive(Debug, Clone, Default, Serialize, ToSchema)]
pub struct Exposure {
    pub training_weeks: i64,
    pub training_days_per_week: Option<f64>,
    pub weekly_hard_sets: f64,
    pub weekly_tonnage_kg: f64,
    pub lifts: BTreeMap<String, LiftExposure>,
    pub accessories: BTreeMap<String, CategoryExposure>,
    pub fatigue: Fatigue,
    pub acwr_peak: Option<f64>,
    pub acwr_composite: Option<f64>,
    pub monotony: Spread,
    pub strain: Spread,
    pub compliance_pct: Option<f64>,
    pub deload: Deload,
    pub specificity: Specificity,
}

#[derive(Debug, Clone, Default, Serialize, ToSchema)]
pub struct Change {
    pub start: Option<f64>,
    pub end: Option<f64>,
    pub delta: Option<f64>,
    pub delta_per_week: Option<f64>,
}

#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct Drift {
    pub slope: f64,
    pub direction: String,
}

#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct CompetitionResult {
    pub name: String,
    pub date: String,
    pub total_kg: Option<f64>,
    pub dots: Option<f64>,
    pub ipf_gl: Option<f64>,
    pub projection_total_delta_kg: Option<f64>,
}

#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct Outcome {
    pub e1rm: BTreeMap<String, Change>,
    pub dots: Change,
    pub ipf_gl: Change,
    pub competition: Option<CompetitionResult>,
    #[schema(value_type = Object)]
    pub rpe_drift: BTreeMap<String, Option<Drift>>,
}

#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct Verdict {
    pub label: String,
    pub delta_kg: Option<f64>,
    pub noise_kg: Option<f64>,
    pub threshold_kg: Option<f64>,
    pub basis: String,
}

#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct BlockClassification {
    pub overall: Verdict,
    pub per_lift: BTreeMap<String, Verdict>,
}

#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct BlockRecord {
    pub block_key: String,
    pub label: String,
    pub start_date: String,
    pub end_date: String,
    pub week_count: i64,
    pub is_current: bool,
    pub training_only: bool,
    pub exposure: Exposure,
    pub outcome: Outcome,
    pub classification: BlockClassification,
    pub data_quality_flags: Vec<Flag>,
}

#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct Thresholds {
    pub method: String,
    pub noise_multiplier: f64,
    pub min_threshold_pct: f64,
    pub fallback_noise_pct: f64,
    pub min_series_points: i64,
}

#[derive(Debug, Clone, Default, Serialize, ToSchema)]
pub struct Counts {
    pub improved: i64,
    pub stalled: i64,
    pub regressed: i64,
    pub insufficient_data: i64,
}

#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct Classification {
    pub thresholds: Thresholds,
    pub overall: Counts,
    pub per_lift: BTreeMap<String, Counts>,
}

#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct Kendall {
    pub tau: Option<f64>,
    pub z: Option<f64>,
    pub p: Option<f64>,
}

#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct Spearman {
    pub rho: Option<f64>,
    pub p: Option<f64>,
}

#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct Observation {
    pub block_key: String,
    pub x: f64,
    pub y: f64,
}

#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct Correlation {
    pub exposure: String,
    pub outcome: String,
    pub lift: Option<String>,
    pub n: i64,
    pub low_n: bool,
    pub kendall: Kendall,
    pub spearman: Spearman,
    pub direction: String,
    pub strength: String,
    pub observations: Vec<Observation>,
}

#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct Band {
    pub label: String,
    pub min: f64,
    pub max: f64,
    pub blocks: i64,
    pub mean_delta_per_week: Option<f64>,
    pub positive_share: Option<f64>,
}

#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct Range {
    pub min: f64,
    pub max: f64,
}

#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct VariableTolerance {
    pub sample_size: i64,
    pub low_n: bool,
    pub bands: Vec<Band>,
    pub positive_range: Option<Range>,
    pub stall_onset: Option<f64>,
}

#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct Tolerance {
    pub min_sample_size: i64,
    pub by_lift: BTreeMap<String, BTreeMap<String, VariableTolerance>>,
}

#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct Evidence {
    pub block_key: String,
    pub label: String,
    pub exposure: f64,
    pub outcome: f64,
    pub classification: String,
}

#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct Signal {
    pub variable: String,
    pub outcome: String,
    pub lift: Option<String>,
    pub statement: String,
    pub strength: String,
    pub n: i64,
    pub low_n: bool,
    pub tau: Option<f64>,
    pub p: Option<f64>,
    pub evidence: Vec<Evidence>,
}

#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct Reference {
    pub metric: String,
    pub kind: String,
    pub lift: Option<String>,
    pub current: f64,
    pub n: i64,
    pub min: f64,
    pub median: f64,
    pub max: f64,
    pub position: String,
}

#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct CurrentVsHistory {
    pub block_key: String,
    pub label: String,
    pub reference_block_keys: Vec<String>,
    pub current: BlockRecord,
    pub metrics: Vec<Reference>,
}

#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct Lifetime {
    pub schema_version: i64,
    pub generated_at: String,
    pub block_count: i64,
    pub min_block_weeks: i64,
    pub blocks: Vec<BlockRecord>,
    pub classification: Classification,
    pub correlations: Vec<Correlation>,
    pub tolerance: Tolerance,
    pub exercise_roi: Vec<ExerciseRoi>,
    pub lift_dose_response: Vec<DoseResponse>,
    pub training_day_response: Vec<TrainingDays>,
    pub pattern_signals: Vec<Pattern>,
    pub worked: Vec<Signal>,
    #[serde(rename = "did_not_work")]
    pub did_not_work: Vec<Signal>,
    pub data_limits: Vec<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub current_vs_history: Option<CurrentVsHistory>,
}
