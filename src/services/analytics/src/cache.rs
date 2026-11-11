use std::time::Duration;

use redis::AsyncCommands;
use redis::aio::{ConnectionManager, ConnectionManagerConfig};
use serde::Serialize;
use serde::de::DeserializeOwned;

const RECORD_TTL_SECONDS: u64 = 2_592_000;
const IO_TIMEOUT: Duration = Duration::from_secs(2);

#[derive(Clone)]
pub struct Cache {
    manager: Option<ConnectionManager>,
}

fn record_key(athlete: &str, key: &str) -> String {
    format!("pl:analysis:{athlete}:{key}")
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

    pub async fn version(&self, athlete: &str) -> String {
        let Some(mut connection) = self.manager.clone() else {
            return "0".to_owned();
        };
        connection
            .get::<_, Option<String>>(format!("pl:analysis-version:{athlete}"))
            .await
            .inspect_err(|error| tracing::warn!(%error, "analysis version read failed"))
            .ok()
            .flatten()
            .unwrap_or_else(|| "0".to_owned())
    }

    pub async fn read<T: DeserializeOwned>(&self, athlete: &str, key: &str) -> Option<T> {
        let mut connection = self.manager.clone()?;
        let raw = connection
            .get::<_, Option<String>>(record_key(athlete, key))
            .await
            .inspect_err(|error| tracing::warn!(%error, key, "analysis record read failed"))
            .ok()??;
        serde_json::from_str(&raw).ok()
    }

    pub async fn write<T: Serialize>(
        &self,
        athlete: &str,
        key: &str,
        value: &T,
        create_only: bool,
    ) -> bool {
        let Some(mut connection) = self.manager.clone() else {
            return false;
        };
        let Ok(body) = serde_json::to_string(value) else {
            return false;
        };
        let mut command = redis::cmd("SET");
        command
            .arg(record_key(athlete, key))
            .arg(body)
            .arg("EX")
            .arg(RECORD_TTL_SECONDS);
        if create_only {
            command.arg("NX");
        }
        command
            .query_async::<Option<String>>(&mut connection)
            .await
            .inspect_err(|error| tracing::warn!(%error, key, "analysis record write failed"))
            .is_ok_and(|reply| reply.as_deref() == Some("OK"))
    }
}
