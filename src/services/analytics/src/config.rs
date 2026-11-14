use std::path::PathBuf;

pub const DOMAIN: &str = "analytics";

#[derive(Clone, Debug)]
pub struct Tables {
    pub health: String,
    pub sessions: String,
    pub competitions: String,
    pub goals: String,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum SourceKind {
    Dynamo,
    Fixture,
}

#[derive(Clone, Debug)]
pub struct Config {
    pub profile_url: String,
    pub valkey_url: String,
    pub region: String,
    pub snapshot_bucket: Option<String>,
    pub port: u16,
    pub grpc_port: u16,
    pub ai_grpc_url: String,
    pub grpc_allowed_callers: Vec<String>,
    pub tables: Tables,
    pub source: SourceKind,
    pub fixture_dir: PathBuf,
}

fn var(name: &str, default: &str) -> String {
    std::env::var(name)
        .ok()
        .filter(|value| !value.is_empty())
        .unwrap_or_else(|| default.to_owned())
}

fn table(name: &str, default: &str) -> String {
    let fallback = var("DYNAMODB_TABLE", default);
    var(name, &fallback)
}

impl Config {
    pub fn from_env() -> Self {
        Self {
            profile_url: var("PL_PROFILE_URL", "http://pl-profile:8000"),
            valkey_url: var("VALKEY_URL", "redis://pl-valkey:6379"),
            region: var("AWS_REGION", "ca-central-1"),
            snapshot_bucket: Some(var("POWERLIFTING_S3_BUCKET", ""))
                .filter(|name| !name.is_empty()),
            port: var("PORT", "8000").parse().unwrap_or(8000),
            grpc_port: var("GRPC_PORT", "50051").parse().unwrap_or(50051),
            ai_grpc_url: var("ANALYTICS_AI_GRPC_URL", "http://pl-analytics-ai:50051"),
            grpc_allowed_callers: var(
                "GRPC_ALLOWED_CALLERS",
                "pl-analytics-ai,pl-analytics-export",
            )
            .split(',')
            .map(|account| account.trim().to_owned())
            .filter(|account| !account.is_empty())
            .collect(),
            tables: Tables {
                health: table("IF_HEALTH_TABLE_NAME", "if-health"),
                sessions: table("IF_SESSIONS_TABLE_NAME", "if-sessions"),
                competitions: var(
                    "POWERLIFTING_USER_COMPETITIONS_TABLE",
                    "if-powerlifting-user-competitions",
                ),
                goals: var("POWERLIFTING_GOALS_TABLE", "if-powerlifting-goals"),
            },
            source: if var("ANALYTICS_SOURCE", "dynamo") == "fixture" {
                SourceKind::Fixture
            } else {
                SourceKind::Dynamo
            },
            fixture_dir: PathBuf::from(var("ANALYTICS_FIXTURE_DIR", "fixtures/operator/source")),
        }
    }
}
