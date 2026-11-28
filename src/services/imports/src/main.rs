use pl_imports::server::{Service, router};
use std::{env, sync::Arc};

fn setting(name: &str, fallback: &str) -> String {
    env::var(name).unwrap_or_else(|_| fallback.into())
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let region = aws_config::Region::new(setting("AWS_REGION", "ca-central-1"));
    let aws = aws_config::defaults(aws_config::BehaviorVersion::latest())
        .region(region)
        .load()
        .await;
    let service = Arc::new(Service::new(
        aws_sdk_dynamodb::Client::new(&aws),
        setting("PL_PROFILE_URL", "http://pl-profile:8000"),
        setting("IF_API_URL", "http://pl-assistant:8000"),
        setting("IF_HEALTH_TABLE_NAME", "if-health"),
        setting("PL_SERVICE_URL_TEMPLATE", "http://pl-{domain}:8000"),
        setting("PL_JOB_TOKEN_PUBLIC_KEY", ""),
    )?);
    let listener =
        tokio::net::TcpListener::bind(format!("0.0.0.0:{}", setting("PORT", "8000"))).await?;
    axum::serve(listener, router(service))
        .with_graceful_shutdown(async {
            let _ = tokio::signal::ctrl_c().await;
        })
        .await?;
    Ok(())
}
