use std::collections::BTreeMap;
use std::future::Future;
use std::pin::Pin;
use std::sync::Mutex;

use aws_sdk_s3::Client;
use aws_sdk_s3::primitives::{ByteStream, DateTimeFormat};
use serde_json::Value;

use crate::error::Error;
use crate::windows::CACHE_SCHEMA_VERSION;

pub type Stored<'a, T> = Pin<Box<dyn Future<Output = Result<T, Error>> + Send + 'a>>;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct StoredBlock {
    pub block_key: String,
    pub stored_at: String,
}

pub trait Snapshots: Send + Sync {
    fn list<'a>(&'a self, athlete: &'a str) -> Stored<'a, Vec<StoredBlock>>;
    fn read<'a>(&'a self, athlete: &'a str, block_key: &'a str) -> Stored<'a, Option<Value>>;
    fn write<'a>(&'a self, athlete: &'a str, block_key: &'a str, body: Value) -> Stored<'a, ()>;
}

pub fn prefix(athlete: &str) -> String {
    format!("analysis/{athlete}/blocks/")
}

pub fn object_key(athlete: &str, block_key: &str) -> String {
    format!(
        "{}{block_key}/v{CACHE_SCHEMA_VERSION}.json",
        prefix(athlete)
    )
}

fn block_of(athlete: &str, key: &str) -> Option<String> {
    let rest = key.strip_prefix(&prefix(athlete))?;
    let block = rest.strip_suffix(&format!("/v{CACHE_SCHEMA_VERSION}.json"))?;
    (!block.is_empty() && !block.contains('/')).then(|| block.to_owned())
}

fn storage(error: impl std::fmt::Display) -> Error {
    Error::Internal(format!("snapshot storage: {error}"))
}

#[derive(Default)]
pub struct MemorySnapshots {
    objects: Mutex<BTreeMap<String, (String, Value)>>,
    clock: Mutex<u64>,
}

impl Snapshots for MemorySnapshots {
    fn list<'a>(&'a self, athlete: &'a str) -> Stored<'a, Vec<StoredBlock>> {
        Box::pin(async move {
            let objects = self.objects.lock().unwrap();
            Ok(objects
                .iter()
                .filter_map(|(key, (stored_at, _))| {
                    Some(StoredBlock {
                        block_key: block_of(athlete, key)?,
                        stored_at: stored_at.clone(),
                    })
                })
                .collect())
        })
    }

    fn read<'a>(&'a self, athlete: &'a str, block_key: &'a str) -> Stored<'a, Option<Value>> {
        Box::pin(async move {
            Ok(self
                .objects
                .lock()
                .unwrap()
                .get(&object_key(athlete, block_key))
                .map(|(_, body)| body.clone()))
        })
    }

    fn write<'a>(&'a self, athlete: &'a str, block_key: &'a str, body: Value) -> Stored<'a, ()> {
        Box::pin(async move {
            let tick = {
                let mut clock = self.clock.lock().unwrap();
                *clock += 1;
                *clock
            };
            self.objects.lock().unwrap().insert(
                object_key(athlete, block_key),
                (format!("1970-01-01T00:00:{tick:02}Z"), body),
            );
            Ok(())
        })
    }
}

pub struct S3Snapshots {
    client: Client,
    bucket: String,
}

impl S3Snapshots {
    pub async fn connect(bucket: String, region: String) -> Self {
        let config = aws_config::defaults(aws_config::BehaviorVersion::latest())
            .region(aws_config::Region::new(region))
            .load()
            .await;
        Self {
            client: Client::new(&config),
            bucket,
        }
    }
}

impl Snapshots for S3Snapshots {
    fn list<'a>(&'a self, athlete: &'a str) -> Stored<'a, Vec<StoredBlock>> {
        Box::pin(async move {
            let mut pages = self
                .client
                .list_objects_v2()
                .bucket(&self.bucket)
                .prefix(prefix(athlete))
                .into_paginator()
                .send();
            let mut stored = Vec::new();
            while let Some(page) = pages.next().await {
                for object in page.map_err(storage)?.contents() {
                    let Some(block_key) = object.key().and_then(|key| block_of(athlete, key))
                    else {
                        continue;
                    };
                    let stored_at = object
                        .last_modified()
                        .and_then(|time| time.fmt(DateTimeFormat::DateTime).ok())
                        .unwrap_or_default();
                    stored.push(StoredBlock {
                        block_key,
                        stored_at,
                    });
                }
            }
            Ok(stored)
        })
    }

    fn read<'a>(&'a self, athlete: &'a str, block_key: &'a str) -> Stored<'a, Option<Value>> {
        Box::pin(async move {
            let response = match self
                .client
                .get_object()
                .bucket(&self.bucket)
                .key(object_key(athlete, block_key))
                .send()
                .await
            {
                Ok(response) => response,
                Err(error) if error.as_service_error().is_some_and(|e| e.is_no_such_key()) => {
                    return Ok(None);
                }
                Err(error) => return Err(storage(error)),
            };
            let bytes = response.body.collect().await.map_err(storage)?.into_bytes();
            Ok(serde_json::from_slice(&bytes).ok())
        })
    }

    fn write<'a>(&'a self, athlete: &'a str, block_key: &'a str, body: Value) -> Stored<'a, ()> {
        Box::pin(async move {
            let bytes = serde_json::to_vec(&body).map_err(storage)?;
            self.client
                .put_object()
                .bucket(&self.bucket)
                .key(object_key(athlete, block_key))
                .content_type("application/json")
                .body(ByteStream::from(bytes))
                .send()
                .await
                .map_err(storage)?;
            Ok(())
        })
    }
}
