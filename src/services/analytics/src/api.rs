use std::sync::Arc;

use axum::Json;
use axum::extract::State;
use axum::http::HeaderMap;
use serde::Serialize;
use serde_json::Value;
use utoipa::openapi::security::{ApiKey, ApiKeyValue, SecurityScheme};
use utoipa::{Modify, OpenApi, ToSchema};

use crate::args::{
    BlockArgs, CompareArgs, ExerciseArgs, LifetimeArgs, PkArgs, SectionArgs, SuggestArgs,
    WeeklyArgs, WindowArgs,
};
use crate::blocks::types::{BlockEntry, Bundle};
use crate::compare::types::Comparison;
use crate::error::Error;
use crate::http::{Health, execute};
use crate::lifetime::types::Lifetime;
use crate::operations::Service;
use crate::records::SectionStatus;

type Shared = State<Arc<Service>>;
type Outcome = Result<Json<Value>, Error>;

#[derive(Serialize, ToSchema)]
pub struct ErrorResponse {
    #[schema(value_type = Object)]
    detail: Value,
}

#[derive(Serialize, ToSchema)]
#[serde(rename_all = "camelCase")]
pub struct ManifestResponse {
    schema_version: i64,
    as_of_date: String,
    window_key: String,
    #[schema(value_type = Object)]
    windows: Value,
    source_fingerprint: String,
    #[schema(value_type = Object)]
    sections: Value,
}

#[derive(Serialize, ToSchema)]
#[serde(rename_all = "camelCase")]
pub struct SectionResponse {
    #[serde(flatten)]
    status: SectionStatus,
    as_of_date: String,
    window_key: String,
}

#[derive(Serialize, ToSchema)]
#[serde(rename_all = "camelCase")]
pub struct QueueResponse {
    accepted: bool,
    as_of_date: String,
    window_key: String,
    queued: Vec<String>,
    source_fingerprint: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    invalidated: Option<Vec<String>>,
}

#[derive(Serialize, ToSchema)]
#[serde(rename_all = "camelCase")]
pub struct RegenerateResponse {
    success: bool,
    accepted: bool,
    as_of_date: String,
    window_key: String,
    queued: Vec<String>,
    generated_at: String,
    windows_regenerated: i64,
}

#[derive(Serialize, ToSchema)]
#[serde(rename_all = "camelCase")]
pub struct BundleResponse {
    schema_version: i64,
    as_of_date: String,
    generated_at: String,
    cached: bool,
    #[schema(value_type = Object)]
    windows: Value,
    #[schema(value_type = Object)]
    results: Value,
}

#[derive(Serialize, ToSchema)]
#[serde(rename_all = "camelCase")]
pub struct BlockRegenerateResponse {
    success: bool,
    block_key: String,
    generated_at: String,
    correlation_regenerated: bool,
    evaluation_regenerated: bool,
}

macro_rules! operation_handlers {
    ($(($function:ident, $name:literal, $path:literal, $request:ty, $response:ty, $summary:literal)),+ $(,)?) => {
        $(
            #[utoipa::path(
                post,
                path = $path,
                summary = $summary,
                request_body = $request,
                responses(
                    (status = 200, description = "Operation result", body = $response),
                    (status = 401, description = "Invalid internal token or principal", body = ErrorResponse),
                    (status = 403, description = "Access denied", body = ErrorResponse),
                    (status = 404, description = "Not found or not cached", body = ErrorResponse),
                    (status = 422, description = "Invalid arguments", body = ErrorResponse),
                    (status = 500, description = "Internal error", body = ErrorResponse)
                ),
                security(("internal" = []))
            )]
            pub async fn $function(
                State(service): Shared,
                headers: HeaderMap,
                body: axum::body::Bytes,
            ) -> Outcome {
                execute(service, $name, headers, body).await
            }
        )+
    };
}

operation_handlers!(
    (analysis_section, "analysis_section", "/operations/analysis_section", SectionArgs, Object, "Compute one deterministic analysis section"),
    (weekly_analysis, "weekly_analysis", "/operations/weekly_analysis", SectionArgs, Object, "Compute every deterministic analysis section"),
    (analyze_progression, "analyze_progression", "/operations/analyze_progression", ExerciseArgs, Object, "Theil-Sen progression rate of one exercise"),
    (analyze_rpe_drift, "analyze_rpe_drift", "/operations/analyze_rpe_drift", ExerciseArgs, Object, "RPE drift of one exercise"),
    (suggest_multipliers, "health_suggest_e1rm_multipliers", "/operations/health_suggest_e1rm_multipliers", SuggestArgs, Object, "Suggest e1RM multipliers"),
    (analytics_manifest, "analytics.manifest", "/operations/analytics.manifest", WindowArgs, ManifestResponse, "Analysis manifest of one window"),
    (analytics_sections_queue, "analytics.sections_queue", "/operations/analytics.sections_queue", WindowArgs, QueueResponse, "Queue missing analysis sections"),
    (analytics_sections_get, "analytics.sections_get", "/operations/analytics.sections_get", WindowArgs, SectionResponse, "Read one analysis section record"),
    (analytics_sections_invalidate, "analytics.sections_invalidate", "/operations/analytics.sections_invalidate", WindowArgs, QueueResponse, "Invalidate and regenerate analysis sections"),
    (analytics_weekly, "analytics.weekly", "/operations/analytics.weekly", WeeklyArgs, Object, "Weekly analysis of a block window"),
    (analytics_bundle, "analytics.bundle", "/operations/analytics.bundle", WindowArgs, BundleResponse, "Analysis bundle for every window"),
    (analytics_regenerate, "analytics.regenerate", "/operations/analytics.regenerate", WindowArgs, RegenerateResponse, "Regenerate analysis sections"),
    (analytics_blocks_list, "analytics.blocks_list", "/operations/analytics.blocks_list", PkArgs, Vec<BlockEntry>, "List analyzed training blocks"),
    (analytics_blocks_get, "analytics.blocks_get", "/operations/analytics.blocks_get", BlockArgs, Bundle, "Analysis bundle of one block"),
    (analytics_blocks_regenerate, "analytics.blocks_regenerate", "/operations/analytics.blocks_regenerate", BlockArgs, BlockRegenerateResponse, "Regenerate one block analysis and its AI reports"),
    (analytics_compare, "analytics.compare", "/operations/analytics.compare", CompareArgs, Comparison, "Deterministic comparison of selected blocks"),
    (analytics_lifetime, "analytics.lifetime", "/operations/analytics.lifetime", LifetimeArgs, Lifetime, "Holistic all-blocks lifetime report"),
);

struct InternalToken;

impl Modify for InternalToken {
    fn modify(&self, openapi: &mut utoipa::openapi::OpenApi) {
        let components = openapi.components.get_or_insert_with(Default::default);
        components.add_security_scheme(
            "internal",
            SecurityScheme::ApiKey(ApiKey::Header(ApiKeyValue::new("X-Internal-Token"))),
        );
    }
}

#[derive(OpenApi)]
#[openapi(
    info(title = "Powerlifting analytics", version = "1.0.0"),
    paths(
        crate::http::health,
        crate::mcp::handle,
        analysis_section,
        weekly_analysis,
        analyze_progression,
        analyze_rpe_drift,
        suggest_multipliers,
        analytics_manifest,
        analytics_sections_queue,
        analytics_sections_get,
        analytics_sections_invalidate,
        analytics_weekly,
        analytics_bundle,
        analytics_regenerate,
        analytics_blocks_list,
        analytics_blocks_get,
        analytics_blocks_regenerate,
        analytics_compare,
        analytics_lifetime,
    ),
    components(schemas(Health, crate::mcp::RpcRequest, ErrorResponse)),
    modifiers(&InternalToken)
)]
pub struct ApiDoc;
