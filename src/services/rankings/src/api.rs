use serde::{Deserialize, Serialize};
use serde_json::{Map, Number, Value};
use utoipa::ToSchema;

#[derive(Serialize, ToSchema)]
pub struct Health {
    pub status: &'static str,
    pub domain: &'static str,
}

#[derive(Serialize, ToSchema)]
pub struct ErrorBody {
    #[schema(value_type = Object)]
    pub detail: Value,
}

#[derive(Deserialize, ToSchema)]
pub struct StatsRequest {
    pub pk: Option<String>,
    pub version: Option<String>,
    pub federation: Option<String>,
    pub country: Option<String>,
    pub region: Option<String>,
    pub equipment: Option<String>,
    pub sex: Option<String>,
    pub age_class: Option<String>,
    pub year: Option<f64>,
    pub event_type: Option<String>,
    pub min_dots: Option<f64>,
    pub squat_kg: Option<f64>,
    pub bench_kg: Option<f64>,
    pub deadlift_kg: Option<f64>,
    pub bodyweight_kg: Option<f64>,
    #[schema(example = "M")]
    pub sex_code: Option<String>,
}

#[derive(Serialize, ToSchema)]
pub struct Computed {
    #[schema(value_type = Option<f64>)]
    pub total_kg: Option<Number>,
    pub dots: Option<f64>,
}

#[derive(Serialize, ToSchema)]
pub struct StatsResponse {
    pub dataset_size: usize,
    pub computed: Computed,
    #[schema(value_type = Object)]
    pub analysis: Map<String, Value>,
}

#[derive(Deserialize, ToSchema)]
pub struct CategoriesRequest {
    pub pk: Option<String>,
}

#[derive(ToSchema)]
pub struct CategoriesResponse {
    pub federations: Vec<String>,
    pub countries: Vec<String>,
    pub regions: Vec<String>,
    pub equipment: Vec<String>,
    pub sex: Vec<String>,
    pub age_classes: Vec<String>,
    pub event_types: Vec<String>,
    pub years: Vec<i64>,
    #[schema(value_type = Object)]
    pub country_federations: Map<String, Value>,
    #[schema(value_type = Object)]
    pub country_regions: Map<String, Value>,
    #[schema(value_type = Object)]
    pub region_federations: Map<String, Value>,
}

#[derive(Deserialize, ToSchema)]
pub struct PercentileRequest {
    pub squat_kg: Option<f64>,
    pub bench_kg: Option<f64>,
    pub deadlift_kg: Option<f64>,
    pub bodyweight_kg: Option<f64>,
    #[schema(example = "M")]
    pub sex_code: Option<String>,
    pub country: Option<String>,
    pub region: Option<String>,
    pub age_class: Option<String>,
    pub equipment: Option<String>,
    pub pk: Option<String>,
}

#[derive(Serialize, ToSchema)]
pub struct PercentileCard {
    pub squat: Option<i64>,
    pub bench: Option<i64>,
    pub deadlift: Option<i64>,
    pub total: Option<i64>,
    pub top10_mean_squat: Option<f64>,
    pub top10_mean_bench: Option<f64>,
    pub top10_mean_deadlift: Option<f64>,
    pub top10_mean_total: Option<f64>,
}

#[derive(Serialize, ToSchema)]
pub struct PercentileMeta {
    pub global_n: usize,
    pub national_n: Option<usize>,
    pub regional_n: Option<usize>,
}

#[derive(Serialize, ToSchema)]
pub struct PercentileResponse {
    pub global: PercentileCard,
    pub national: PercentileCard,
    pub regional: PercentileCard,
    pub weight_class_label: Option<String>,
    pub meta: PercentileMeta,
}
