use std::sync::Arc;
use std::time::Duration;

use axum::extract::{Path, State};
use axum::http::{HeaderMap, StatusCode};
use axum::routing::{get, post};
use axum::{Json, Router};
use serde::Serialize;
use serde_json::{Map, Value, json};
use tower_http::compression::CompressionLayer;
use tower_http::timeout::TimeoutLayer;
use tower_http::trace::TraceLayer;
use utoipa::{OpenApi, ToSchema};
use utoipa_scalar::{Scalar, Servable};

use crate::auth;
use crate::config::DOMAIN;
use crate::error::Error;
use crate::mcp;
use crate::operations::{Caller, Registry, Service};

const REQUEST_TIMEOUT: Duration = Duration::from_secs(180);

#[derive(Serialize, ToSchema)]
pub struct Health {
    status: &'static str,
    domain: &'static str,
}

#[derive(OpenApi)]
#[openapi(
    info(title = "Powerlifting analytics", version = "1.0.0"),
    paths(health, mcp::handle),
    components(schemas(Health, mcp::RpcRequest))
)]
struct ApiDoc;

pub fn router(service: Arc<Service>) -> Router {
    let document = Arc::new(openapi(&service.registry));
    let served = Arc::clone(&document);
    Router::new()
        .route("/health", get(health))
        .route("/operations/{name}", post(operation))
        .route("/mcp", post(mcp::handle))
        .route(
            "/openapi.json",
            get(move || async move { Json(served.as_ref().clone()) }),
        )
        .merge(Scalar::with_url("/docs", document.as_ref().clone()))
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
        (status = 200, description = "Service ready", body = Health)
    )
)]
async fn health() -> Json<Health> {
    Json(Health {
        status: "ok",
        domain: DOMAIN,
    })
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

fn openapi(registry: &Registry) -> Value {
    let mut document = serde_json::to_value(ApiDoc::openapi()).unwrap_or_else(|_| json!({}));
    let mut paths = document
        .get("paths")
        .and_then(Value::as_object)
        .cloned()
        .unwrap_or_default();
    for operation in registry.iter() {
        paths.insert(
            format!("/operations/{}", operation.name),
            operation_path(operation),
        );
    }
    document["paths"] = Value::Object(paths);
    document["info"]["title"] = json!(format!("Powerlifting {DOMAIN}"));
    document["components"]["securitySchemes"] =
        json!({"internal": {"type": "apiKey", "in": "header", "name": "X-Internal-Token"}});
    document
}

fn operation_path(operation: &crate::operations::Operation) -> Value {
    let mut post = Map::new();
    post.insert("operationId".to_owned(), json!(operation.name));
    post.insert("summary".to_owned(), json!(operation.description));
    post.insert(
        "requestBody".to_owned(),
        json!({"required": true, "content": {"application/json": {"schema": operation.input_schema}}}),
    );
    post.insert(
        "responses".to_owned(),
        json!({"200": {
            "description": "Domain result",
            "content": {"application/json": {"schema": operation.result_schema}},
        }}),
    );
    post.insert("security".to_owned(), json!([{"internal": []}]));
    json!({"post": post})
}
