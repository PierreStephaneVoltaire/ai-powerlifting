use std::time::Duration;

use redis::AsyncCommands;
use redis::aio::{ConnectionManager, ConnectionManagerConfig};
use serde_json::{Map, Value};
use sha2::{Digest, Sha256};

use crate::pyjson;

const TTL_SECONDS: u64 = 604_800;
const IO_TIMEOUT: Duration = Duration::from_secs(2);
const RANKING_INPUTS: [&str; 9] = [
    "squat_kg",
    "bench_kg",
    "deadlift_kg",
    "bodyweight_kg",
    "sex_code",
    "country",
    "region",
    "age_class",
    "equipment",
];

#[derive(Clone)]
pub struct Cache {
    manager: Option<ConnectionManager>,
}

impl Cache {
    pub fn disabled() -> Self {
        Self { manager: None }
    }

    pub fn connect(url: &str) -> Self {
        let config = ConnectionManagerConfig::new()
            .set_connection_timeout(Some(IO_TIMEOUT))
            .set_response_timeout(Some(IO_TIMEOUT))
            .set_number_of_retries(1);
        let manager = redis::Client::open(url)
            .and_then(|client| ConnectionManager::new_lazy_with_config(client, config))
            .inspect_err(|error| tracing::warn!(%error, "Valkey disabled"))
            .ok();
        Self { manager }
    }

    pub async fn get(&self, key: &str) -> Option<Value> {
        let mut connection = self.manager.clone()?;
        let raw = connection
            .get::<_, Option<String>>(key)
            .await
            .inspect_err(|error| tracing::warn!(%error, key, "Valkey read failed"))
            .ok()??;
        serde_json::from_str(&raw).ok()
    }

    pub async fn set(&self, key: &str, value: &Value) {
        let Some(mut connection) = self.manager.clone() else {
            return;
        };
        let result = connection
            .set_ex::<_, _, ()>(key, value.to_string(), TTL_SECONDS)
            .await;
        if let Err(error) = result {
            tracing::warn!(%error, key, "Valkey write failed");
        }
    }
}

pub fn ranking_key(identity: &str, year: i32, args: &Map<String, Value>) -> String {
    let inputs: Map<String, Value> = RANKING_INPUTS
        .iter()
        .map(|name| {
            (
                (*name).to_owned(),
                args.get(*name).cloned().unwrap_or(Value::Null),
            )
        })
        .collect();
    let digest = hex::encode(Sha256::digest(
        pyjson::dumps(&Value::Object(inputs), true).as_bytes(),
    ));
    let pk = args.get("pk").and_then(Value::as_str).unwrap_or_default();
    format!("pl:rankings:{identity}:{year}:{pk}:{digest}")
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::*;

    #[test]
    fn key_hashes_python_style_inputs() {
        let args = json!({"pk": "operator", "squat_kg": 200, "sex_code": "M", "ignored": 1});
        let key = ranking_key("abc", 2026, args.as_object().unwrap());
        let inputs = r#"{"age_class": null, "bench_kg": null, "bodyweight_kg": null, "country": null, "deadlift_kg": null, "equipment": null, "region": null, "sex_code": "M", "squat_kg": 200}"#;
        let digest = hex::encode(Sha256::digest(inputs.as_bytes()));
        assert_eq!(key, format!("pl:rankings:abc:2026:operator:{digest}"));
    }
}
