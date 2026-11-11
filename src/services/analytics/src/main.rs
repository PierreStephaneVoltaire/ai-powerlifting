use std::sync::Arc;

use mimalloc::MiMalloc;
use pl_analytics::cache::Cache;
use pl_analytics::config::{Config, SourceKind};
use pl_analytics::engine::{Clock, Engine};
use pl_analytics::http;
use pl_analytics::operations::{Registry, Service};
use pl_analytics::source::Source;
use pl_analytics::source::dynamo::DynamoSource;
use pl_analytics::source::fixture::FixtureSource;
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
    let source: Arc<dyn Source> = match config.source {
        SourceKind::Dynamo => {
            Arc::new(DynamoSource::connect(config.tables.clone(), config.region.clone()).await)
        }
        SourceKind::Fixture => Arc::new(FixtureSource::new(config.fixture_dir.clone())),
    };
    let engine = Engine::new(source, Cache::connect(&config.valkey_url), Clock::System);
    let port = config.port;
    let service = Arc::new(Service::new(config, Registry::load()?, engine));
    let listener = TcpListener::bind(("0.0.0.0", port)).await?;
    tracing::info!(port, "pl-analytics listening");
    axum::serve(listener, http::router(service))
        .with_graceful_shutdown(shutdown())
        .await?;
    Ok(())
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
