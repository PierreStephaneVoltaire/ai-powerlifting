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
use utoipa::openapi::security::{ApiKey, ApiKeyValue, SecurityScheme};
use utoipa::{Modify, OpenApi};
use utoipa_swagger_ui::SwaggerUi;

use crate::api::{
    CategoriesRequest, CategoriesResponse, ErrorBody, Health, PercentileRequest,
    PercentileResponse, StatsRequest, StatsResponse,
};

use crate::auth;
use crate::config::DOMAIN;
use crate::dataset::Phase;
use crate::error::Error;
use crate::mcp;
use crate::operations::{Caller, Service};

const REQUEST_TIMEOUT: Duration = Duration::from_secs(180);

struct InternalToken;

impl Modify for InternalToken {
    fn modify(&self, openapi: &mut utoipa::openapi::OpenApi) {
        if let Some(components) = openapi.components.as_mut() {
            components.add_security_scheme(
                "internal",
                SecurityScheme::ApiKey(ApiKey::Header(ApiKeyValue::new("X-Internal-Token"))),
            );
        }
    }
}

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
    )),
    modifiers(&InternalToken)
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

pub fn authenticate(service: &Service, headers: &HeaderMap) -> Result<(), Error> {
    auth::check_internal_token(
        &service.config.internal_token,
        header(headers, "x-internal-token"),
    )
}

fn header<'a>(headers: &'a HeaderMap, name: &str) -> &'a str {
    headers
        .get(name)
        .and_then(|value| value.to_str().ok())
        .unwrap_or_default()
}

pub fn principal_caller(headers: &HeaderMap) -> Caller {
    Caller {
        athlete: header(headers, "x-athlete-pk").to_owned(),
        person: header(headers, "x-person-pk").to_owned(),
        principal: header(headers, "x-pl-principal").to_owned(),
        ..Caller::default()
    }
}

fn caller(headers: &HeaderMap) -> Caller {
    let turn = header(headers, "x-if-turn-id");
    let job = if turn.is_empty() {
        header(headers, "x-if-job-id")
    } else {
        turn
    };
    Caller {
        job_id: job.to_owned(),
        generation_id: header(headers, "x-if-generation-id").to_owned(),
        nested: header(headers, "x-pl-nested-operation") == "true",
        ..principal_caller(headers)
    }
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
    authenticate(&service, &headers)?;
    let arguments = match serde_json::from_slice::<Value>(&body) {
        Ok(Value::Object(arguments)) => arguments,
        _ => return Err(Error::Body),
    };
    service
        .call(&name, arguments, &caller(&headers))
        .await
        .map(Json)
}

#[utoipa::path(
    post,
    path = "/operations/analyze_powerlifting_stats",
    request_body = StatsRequest,
    responses(
        (status = 200, description = "Rank analysis, or a status string while the dataset loads", body = StatsResponse),
        (status = 401, description = "Invalid internal token", body = ErrorBody),
        (status = 422, description = "Invalid request body", body = ErrorBody)
    ),
    security(("internal" = []))
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
        (status = 401, description = "Invalid internal token", body = ErrorBody),
        (status = 422, description = "Invalid request body", body = ErrorBody)
    ),
    security(("internal" = []))
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
        (status = 401, description = "Invalid internal token", body = ErrorBody),
        (status = 422, description = "Invalid request body", body = ErrorBody)
    ),
    security(("internal" = []))
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
    }
}
