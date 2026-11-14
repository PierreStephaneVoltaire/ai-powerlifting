use std::sync::{Arc, Mutex};
use std::time::Duration;

use axum::Router;
use axum::extract::State;
use axum::http::{HeaderMap, StatusCode};
use axum::response::IntoResponse;
use axum::routing::post;
use serde_json::Value;
use tokio::net::TcpListener;

use crate::cache::Cache;
use crate::config::Config;
use crate::dataset::Readiness;
use crate::operations::{Registry, Service};
use crate::ops::Engine;

pub type Hits = Arc<Mutex<Vec<(HeaderMap, Value)>>>;

#[derive(Clone)]
struct Stub {
    status: StatusCode,
    body: Value,
    hits: Hits,
}

pub struct Profile {
    pub url: String,
    pub hits: Hits,
}

async fn access_context(
    State(stub): State<Stub>,
    headers: HeaderMap,
    body: axum::body::Bytes,
) -> impl IntoResponse {
    let parsed = serde_json::from_slice(&body).unwrap_or(Value::Null);
    stub.hits.lock().unwrap().push((headers, parsed));
    (stub.status, axum::Json(stub.body))
}

pub async fn profile(status: u16, body: Value) -> Profile {
    let hits = Hits::default();
    let stub = Stub {
        status: StatusCode::from_u16(status).unwrap(),
        body,
        hits: hits.clone(),
    };
    let router = Router::new()
        .route("/operations/access_context", post(access_context))
        .with_state(stub);
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let url = format!("http://{}", listener.local_addr().unwrap());
    tokio::spawn(async move { axum::serve(listener, router).await });
    Profile { url, hits }
}

pub fn service(profile: &Profile) -> Service {
    let config = Config {
        profile_url: profile.url.clone(),
        ..Config::from_env()
    };
    let engine = Engine::new(
        Readiness::new(),
        Cache::disabled(),
        Duration::from_millis(20),
        1,
    );
    Service::new(config, Registry::load().unwrap(), engine)
}
