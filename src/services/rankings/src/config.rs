use std::path::PathBuf;
use std::time::Duration;

pub const DOMAIN: &str = "rankings";

#[derive(Clone, Debug)]
pub struct Config {
    pub internal_token: String,
    pub principal_secret: String,
    pub profile_url: String,
    pub valkey_url: String,
    pub data_dir: PathBuf,
    pub bucket: Option<String>,
    pub region: String,
    pub port: u16,
    pub ready_timeout: Duration,
    pub max_concurrency: usize,
}

fn var(name: &str, default: &str) -> String {
    std::env::var(name).unwrap_or_else(|_| default.to_owned())
}

fn parsed<T: std::str::FromStr>(name: &str, default: T) -> T {
    std::env::var(name)
        .ok()
        .and_then(|value| value.parse().ok())
        .unwrap_or(default)
}

impl Config {
    pub fn from_env() -> Self {
        Self {
            internal_token: var("INTERNAL_API_TOKEN", ""),
            principal_secret: var("PL_PRINCIPAL_SECRET", ""),
            profile_url: var("PL_PROFILE_URL", "http://pl-profile:8000"),
            valkey_url: var("VALKEY_URL", "redis://pl-valkey:6379"),
            data_dir: PathBuf::from(var("DATA_DIR", "/data")),
            bucket: Some(var("POWERLIFTING_S3_BUCKET", "")).filter(|name| !name.is_empty()),
            region: var("AWS_REGION", "ca-central-1"),
            port: parsed("PORT", 8000),
            ready_timeout: Duration::from_secs(parsed("RANKINGS_READY_TIMEOUT_SECS", 120)),
            max_concurrency: parsed("RANKINGS_MAX_CONCURRENCY", 4),
        }
    }
}
