use std::sync::Arc;
use std::time::Duration;

use axum::extract::{Path, State};
use axum::http::{HeaderMap, StatusCode};
use axum::routing::{get, post};
use axum::{Json, Router};
use serde_json::Value;
use tower_http::compression::CompressionLayer;
use tower_http::timeout::TimeoutLayer;
use tower_http::trace::TraceLayer;
use utoipa::OpenApi;
use utoipa_swagger_ui::SwaggerUi;

use crate::api::{
    CallerHeaders, CategoriesRequest, CategoriesResponse, ErrorBody, Health, PercentileRequest,
    PercentileResponse, StatsRequest, StatsResponse,
};

use crate::caller::Caller;
use crate::config::DOMAIN;
use crate::dataset::Phase;
use crate::error::Error;
use crate::mcp;
use crate::operations::Service;

const REQUEST_TIMEOUT: Duration = Duration::from_secs(180);

#[derive(OpenApi)]
#[openapi(
    info(title = "Powerlifting rankings", version = "1.0.0"),
    paths(
        health,
        mcp::handle,
        analyze_powerlifting_stats,
        powerlifting_filter_categories,
        powerlifting_ranking_percentile
    ),
    components(schemas(
        Health,
        ErrorBody,
        mcp::RpcRequest,
        StatsRequest,
        StatsResponse,
        CategoriesRequest,
        CategoriesResponse,
        PercentileRequest,
        PercentileResponse
    ))
)]
pub struct ApiDoc;

pub fn router(service: Arc<Service>) -> Router {
    Router::new()
        .route("/health", get(health))
        .route(
            "/operations/analyze_powerlifting_stats",
            post(analyze_powerlifting_stats),
        )
        .route(
            "/operations/powerlifting_filter_categories",
            post(powerlifting_filter_categories),
        )
        .route(
            "/operations/powerlifting_ranking_percentile",
            post(powerlifting_ranking_percentile),
        )
        .route("/operations/{name}", post(operation))
        .route("/mcp", post(mcp::handle))
        .merge(SwaggerUi::new("/docs").url("/openapi.json", ApiDoc::openapi()))
        .layer(CompressionLayer::new())
        .layer(TimeoutLayer::with_status_code(
            StatusCode::REQUEST_TIMEOUT,
            REQUEST_TIMEOUT,
        ))
        .layer(TraceLayer::new_for_http())
        .with_state(service)
}

#[utoipa::path(
    get,
    path = "/health",
    responses(
        (status = 200, description = "Dataset loaded", body = Health),
        (status = 503, description = "Dataset still loading or failed", body = Health)
    )
)]
async fn health(State(service): State<Arc<Service>>) -> (StatusCode, Json<Health>) {
    let (code, status) = match service.readiness().current() {
        Phase::Ready(_) => (StatusCode::OK, "ok"),
        Phase::Loading => (StatusCode::SERVICE_UNAVAILABLE, "loading"),
        Phase::Failed(_) => (StatusCode::SERVICE_UNAVAILABLE, "failed"),
    };
    (
        code,
        Json(Health {
            status,
            domain: DOMAIN,
        }),
    )
}

async fn operation(
    State(service): State<Arc<Service>>,
    Path(name): Path<String>,
    headers: HeaderMap,
    body: axum::body::Bytes,
) -> Result<Json<Value>, Error> {
    let arguments = match serde_json::from_slice::<Value>(&body) {
        Ok(Value::Object(arguments)) => arguments,
        _ => return Err(Error::Body),
    };
    service
        .call(&name, arguments, &Caller::from_headers(&headers))
        .await
        .map(Json)
}

#[utoipa::path(
    post,
    path = "/operations/analyze_powerlifting_stats",
    request_body = StatsRequest,
    responses(
        (status = 200, description = "Rank analysis, or a status string while the dataset loads", body = StatsResponse),
        (status = 403, description = "Access denied", body = ErrorBody),
        (status = 422, description = "Invalid request body", body = ErrorBody)
    ),
    params(CallerHeaders)
)]
async fn analyze_powerlifting_stats(
    state: State<Arc<Service>>,
    headers: HeaderMap,
    body: axum::body::Bytes,
) -> Result<Json<Value>, Error> {
    operation(
        state,
        Path("analyze_powerlifting_stats".to_owned()),
        headers,
        body,
    )
    .await
}

#[utoipa::path(
    post,
    path = "/operations/powerlifting_filter_categories",
    request_body = CategoriesRequest,
    responses(
        (status = 200, description = "Distinct filter values, or a status string while the dataset loads", body = CategoriesResponse),
        (status = 403, description = "Access denied", body = ErrorBody),
        (status = 422, description = "Invalid request body", body = ErrorBody)
    ),
    params(CallerHeaders)
)]
async fn powerlifting_filter_categories(
    state: State<Arc<Service>>,
    headers: HeaderMap,
    body: axum::body::Bytes,
) -> Result<Json<Value>, Error> {
    operation(
        state,
        Path("powerlifting_filter_categories".to_owned()),
        headers,
        body,
    )
    .await
}

#[utoipa::path(
    post,
    path = "/operations/powerlifting_ranking_percentile",
    request_body = PercentileRequest,
    responses(
        (status = 200, description = "Percentiles by scope, or a status string while the dataset loads", body = PercentileResponse),
        (status = 403, description = "Access denied", body = ErrorBody),
        (status = 422, description = "Invalid request body", body = ErrorBody)
    ),
    params(CallerHeaders)
)]
async fn powerlifting_ranking_percentile(
    state: State<Arc<Service>>,
    headers: HeaderMap,
    body: axum::body::Bytes,
) -> Result<Json<Value>, Error> {
    operation(
        state,
        Path("powerlifting_ranking_percentile".to_owned()),
        headers,
        body,
    )
    .await
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::operations::Registry;

    #[test]
    fn openapi_documents_every_registered_operation() {
        let document = serde_json::to_value(ApiDoc::openapi()).expect("serializable");
        let registry = Registry::load().expect("contract loads");
        let mut count = 0;
        for operation in registry.iter() {
            count += 1;
            let path = format!("/operations/{}", operation.name);
            assert!(
                document
                    .pointer(&format!("/paths/{}/post", path.replace('/', "~1")))
                    .is_some(),
                "missing {path}"
            );
        }
        assert!(count > 0);
        assert!(document.pointer("/paths/~1health/get").is_some());
        assert!(document.pointer("/paths/~1mcp/post").is_some());
        assert!(document.pointer("/components/securitySchemes").is_none());
        let parameters = document
            .pointer("/paths/~1operations~1powerlifting_filter_categories/post/parameters")
            .and_then(Value::as_array)
            .expect("header parameters");
        let names: Vec<&str> = parameters
            .iter()
            .filter_map(|parameter| parameter["name"].as_str())
            .collect();
        assert!(names.contains(&"X-Person-Pk") && names.contains(&"X-Athlete-Pk"));
    }
}
