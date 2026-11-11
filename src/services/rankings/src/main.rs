use std::sync::Arc;

use mimalloc::MiMalloc;
use pl_rankings::cache::Cache;
use pl_rankings::config::Config;
use pl_rankings::dataset::{self, Readiness};
use pl_rankings::http;
use pl_rankings::operations::{Registry, Service};
use pl_rankings::ops::Engine;
use pl_rankings::store::{NoStore, S3Store};
use tokio::net::TcpListener;
use tokio::signal::unix::{SignalKind, signal};
use tracing_subscriber::EnvFilter;

#[global_allocator]
static GLOBAL: MiMalloc = MiMalloc;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    tracing_subscriber::fmt()
        .json()
        .with_env_filter(
            EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("info")),
        )
        .init();
    let config = Config::from_env();
    let readiness = Readiness::new();
    tokio::spawn(load_dataset(config.clone(), readiness.clone()));
    let engine = Engine::new(
        readiness,
        Cache::connect(&config.valkey_url),
        config.ready_timeout,
        config.max_concurrency,
    );
    let port = config.port;
    let service = Arc::new(Service::new(config, Registry::load()?, engine));
    let listener = TcpListener::bind(("0.0.0.0", port)).await?;
    tracing::info!(port, "pl-rankings listening");
    axum::serve(listener, http::router(service))
        .with_graceful_shutdown(shutdown())
        .await?;
    Ok(())
}

async fn load_dataset(config: Config, readiness: Readiness) {
    match config.bucket {
        Some(bucket) => {
            let store = S3Store::connect(bucket, config.region, dataset::PREFIX).await;
            dataset::boot(&store, &config.data_dir, &readiness).await;
        }
        None => dataset::boot(&NoStore, &config.data_dir, &readiness).await,
    }
}

async fn shutdown() {
    let Ok(mut terminate) = signal(SignalKind::terminate()) else {
        return;
    };
    tokio::select! {
        _ = terminate.recv() => {}
        _ = tokio::signal::ctrl_c() => {}
    }
}
