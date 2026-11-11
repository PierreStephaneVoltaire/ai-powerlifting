use std::future::Future;
use std::path::Path;

use aws_sdk_s3::Client;
use aws_sdk_s3::primitives::ByteStream;
use tokio::io::AsyncWriteExt;

use crate::dataset::DatasetError;

#[derive(Clone, Debug)]
pub struct ObjectMeta {
    pub key: String,
    pub size: u64,
    pub modified: i64,
}

pub trait ObjectStore: Send + Sync {
    fn list(&self) -> impl Future<Output = Result<Vec<ObjectMeta>, DatasetError>> + Send;
    fn download(
        &self,
        key: &str,
        dest: &Path,
    ) -> impl Future<Output = Result<(), DatasetError>> + Send;
    fn upload(
        &self,
        source: &Path,
        key: &str,
    ) -> impl Future<Output = Result<(), DatasetError>> + Send;
}

pub struct NoStore;

impl ObjectStore for NoStore {
    async fn list(&self) -> Result<Vec<ObjectMeta>, DatasetError> {
        Ok(Vec::new())
    }

    async fn download(&self, key: &str, _dest: &Path) -> Result<(), DatasetError> {
        Err(DatasetError::Failed(format!("no object store for {key}")))
    }

    async fn upload(&self, _source: &Path, _key: &str) -> Result<(), DatasetError> {
        Ok(())
    }
}

pub struct S3Store {
    client: Client,
    bucket: String,
    prefix: &'static str,
}

impl S3Store {
    pub async fn connect(bucket: String, region: String, prefix: &'static str) -> Self {
        let config = aws_config::defaults(aws_config::BehaviorVersion::latest())
            .region(aws_config::Region::new(region))
            .load()
            .await;
        Self {
            client: Client::new(&config),
            bucket,
            prefix,
        }
    }
}

fn failure(error: impl std::fmt::Display) -> DatasetError {
    DatasetError::Failed(error.to_string())
}

impl ObjectStore for S3Store {
    async fn list(&self) -> Result<Vec<ObjectMeta>, DatasetError> {
        let mut pages = self
            .client
            .list_objects_v2()
            .bucket(&self.bucket)
            .prefix(self.prefix)
            .into_paginator()
            .send();
        let mut objects = Vec::new();
        while let Some(page) = pages.next().await {
            for object in page.map_err(failure)?.contents() {
                objects.push(ObjectMeta {
                    key: object.key().unwrap_or_default().to_owned(),
                    size: object.size().unwrap_or_default().max(0) as u64,
                    modified: object.last_modified().map_or(0, |time| time.secs()),
                });
            }
        }
        Ok(objects)
    }

    async fn download(&self, key: &str, dest: &Path) -> Result<(), DatasetError> {
        let response = self
            .client
            .get_object()
            .bucket(&self.bucket)
            .key(key)
            .send()
            .await
            .map_err(failure)?;
        let mut body = response.body;
        let mut file = tokio::fs::File::create(dest).await.map_err(failure)?;
        while let Some(chunk) = body.try_next().await.map_err(failure)? {
            file.write_all(&chunk).await.map_err(failure)?;
        }
        file.flush().await.map_err(failure)
    }

    async fn upload(&self, source: &Path, key: &str) -> Result<(), DatasetError> {
        let body = ByteStream::from_path(source).await.map_err(failure)?;
        self.client
            .put_object()
            .bucket(&self.bucket)
            .key(key)
            .body(body)
            .send()
            .await
            .map_err(failure)?;
        Ok(())
    }
}
