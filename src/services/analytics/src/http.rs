use std::sync::Arc;
use std::time::Duration;

use axum::extract::{Path, State};
use axum::http::{HeaderMap, StatusCode};
use axum::routing::{get, post};
use axum::{Json, Router};
use serde::Serialize;
use serde_json::Value;
use tower_http::compression::CompressionLayer;
use tower_http::timeout::TimeoutLayer;
use tower_http::trace::TraceLayer;
use utoipa::{OpenApi, ToSchema};
use utoipa_swagger_ui::SwaggerUi;

use crate::api::ApiDoc;
use crate::caller::Caller;
use crate::config::DOMAIN;
use crate::error::Error;
use crate::mcp;
use crate::operations::Service;

const REQUEST_TIMEOUT: Duration = Duration::from_secs(180);

#[derive(Serialize, ToSchema)]
pub struct Health {
    status: &'static str,
    domain: &'static str,
}

pub fn router(service: Arc<Service>) -> Router {
    Router::new()
        .route("/health", get(health))
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
        (status = 200, description = "Service ready", body = Health)
    )
)]
pub async fn health() -> Json<Health> {
    Json(Health {
        status: "ok",
        domain: DOMAIN,
    })
}

pub async fn execute(
    service: Arc<Service>,
    name: &str,
    headers: HeaderMap,
    body: axum::body::Bytes,
) -> Result<Json<Value>, Error> {
    let arguments = match serde_json::from_slice::<Value>(&body) {
        Ok(Value::Object(arguments)) => arguments,
        _ => return Err(Error::Body),
    };
    service
        .call(name, arguments, &Caller::from_headers(&headers))
        .await
        .map(Json)
}

async fn operation(
    State(service): State<Arc<Service>>,
    Path(name): Path<String>,
    headers: HeaderMap,
    body: axum::body::Bytes,
) -> Result<Json<Value>, Error> {
    execute(service, &name, headers, body).await
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
            .pointer("/paths/~1operations~1analytics.manifest/post/parameters")
            .and_then(Value::as_array)
            .expect("header parameters");
        let names: Vec<&str> = parameters
            .iter()
            .filter_map(|parameter| parameter["name"].as_str())
            .collect();
        assert!(names.contains(&"X-Person-Pk") && names.contains(&"X-Athlete-Pk"));
    }
}
