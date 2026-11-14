use std::time::Duration;

use redis::AsyncCommands;
use redis::aio::{ConnectionManager, ConnectionManagerConfig};
use serde::Serialize;
use serde::de::DeserializeOwned;

pub const RECORD_TTL_SECONDS: u64 = 2_592_000;
const BUILD_KEY: &str = "pl:analysis-build";
const SWEEP_LOCK_KEY: &str = "pl:analysis-build-sweep";
const SWEEP_LOCK_SECONDS: u64 = 300;
const SWEEP_BATCH: usize = 500;
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

    pub async fn sweep_for_build(&self, build_id: &str) {
        let Some(mut connection) = self.manager.clone() else {
            return;
        };
        match connection.get::<_, Option<String>>(BUILD_KEY).await {
            Ok(current) if current.as_deref() == Some(build_id) => return,
            Ok(_) => {}
            Err(error) => {
                tracing::warn!(%error, "analysis build read failed");
                return;
            }
        }
        let claimed = redis::cmd("SET")
            .arg(SWEEP_LOCK_KEY)
            .arg(build_id)
            .arg("NX")
            .arg("EX")
            .arg(SWEEP_LOCK_SECONDS)
            .query_async::<Option<String>>(&mut connection)
            .await
            .inspect_err(|error| tracing::warn!(%error, "analysis sweep lock failed"))
            .is_ok_and(|reply| reply.as_deref() == Some("OK"));
        if !claimed {
            return;
        }
        let mut cursor = 0u64;
        let mut removed = 0usize;
        loop {
            let scanned = redis::cmd("SCAN")
                .arg(cursor)
                .arg("MATCH")
                .arg("pl:analysis:*")
                .arg("COUNT")
                .arg(SWEEP_BATCH)
                .query_async::<(u64, Vec<String>)>(&mut connection)
                .await;
            let (next, keys) = match scanned {
                Ok(page) => page,
                Err(error) => {
                    tracing::warn!(%error, "analysis sweep scan failed");
                    return;
                }
            };
            if !keys.is_empty() {
                match redis::cmd("UNLINK")
                    .arg(&keys)
                    .query_async::<usize>(&mut connection)
                    .await
                {
                    Ok(count) => removed += count,
                    Err(error) => {
                        tracing::warn!(%error, "analysis sweep unlink failed");
                        return;
                    }
                }
            }
            cursor = next;
            if cursor == 0 {
                break;
            }
        }
        if let Err(error) = connection.set::<_, _, ()>(BUILD_KEY, build_id).await {
            tracing::warn!(%error, "analysis build write failed");
            return;
        }
        tracing::info!(build_id, removed, "analysis cache swept for new build");
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn records_live_thirty_days() {
        assert_eq!(RECORD_TTL_SECONDS, 30 * 24 * 60 * 60);
    }

    #[test]
    fn record_keys_are_namespaced_per_athlete() {
        assert_eq!(
            record_key("operator", "native_lifetime#3"),
            "pl:analysis:operator:native_lifetime#3"
        );
    }
}
