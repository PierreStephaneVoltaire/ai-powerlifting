use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::Duration;

use polars::prelude::*;
use serde_json::Value;
use sha2::{Digest, Sha256};
use thiserror::Error;
use tokio::sync::watch;

use crate::categories;
use crate::store::{ObjectMeta, ObjectStore};

pub const PREFIX: &str = "datasets/openpowerlifting-";
const ROW_GROUP_ROWS: usize = 131_072;
const TEXT_COLUMNS: [&str; 7] = [
    "Federation",
    "MeetCountry",
    "State",
    "Equipment",
    "Sex",
    "AgeClass",
    "Event",
];
const FLOAT_COLUMNS: [&str; 6] = [
    "Best3SquatKg",
    "Best3BenchKg",
    "Best3DeadliftKg",
    "TotalKg",
    "Dots",
    "BodyweightKg",
];

#[derive(Clone, Debug, Error)]
pub enum DatasetError {
    #[error("No powerlifting datasets found in sandbox matching: {0}")]
    Missing(String),
    #[error("{0}")]
    Failed(String),
}

impl From<PolarsError> for DatasetError {
    fn from(error: PolarsError) -> Self {
        Self::Failed(error.to_string())
    }
}

impl From<std::io::Error> for DatasetError {
    fn from(error: std::io::Error) -> Self {
        Self::Failed(error.to_string())
    }
}

#[derive(Debug)]
pub struct Loaded {
    pub parquet: PathBuf,
    pub identity: String,
    pub categories: Value,
}

#[derive(Clone, Debug)]
pub enum Phase {
    Loading,
    Ready(Arc<Loaded>),
    Failed(DatasetError),
}

#[derive(Clone)]
pub struct Readiness(Arc<watch::Sender<Phase>>);

impl Readiness {
    pub fn new() -> Self {
        Self(Arc::new(watch::channel(Phase::Loading).0))
    }

    pub fn set(&self, phase: Phase) {
        self.0.send_replace(phase);
    }

    pub fn current(&self) -> Phase {
        self.0.borrow().clone()
    }

    pub async fn settled(&self, limit: Duration) -> Phase {
        let mut receiver = self.0.subscribe();
        match tokio::time::timeout(limit, receiver.wait_for(|p| !matches!(p, Phase::Loading))).await
        {
            Ok(Ok(phase)) => phase.clone(),
            _ => Phase::Loading,
        }
    }
}

impl Default for Readiness {
    fn default() -> Self {
        Self::new()
    }
}

const RETRY_INITIAL: Duration = Duration::from_secs(2);
const RETRY_MAX: Duration = Duration::from_secs(60);

pub async fn boot<S: ObjectStore>(store: &S, data_dir: &Path, readiness: &Readiness) {
    let mut delay = RETRY_INITIAL;
    let phase = loop {
        match prepare(store, data_dir).await {
            Ok(loaded) => break Phase::Ready(Arc::new(loaded)),
            Err(error @ DatasetError::Failed(_)) => {
                tracing::warn!(%error, next_retry_secs = delay.as_secs(), "OpenPowerlifting dataset load failed, retrying");
                tokio::time::sleep(delay).await;
                delay = (delay * 2).min(RETRY_MAX);
            }
            Err(error) => {
                tracing::error!(%error, "OpenPowerlifting dataset load failed");
                break Phase::Failed(error);
            }
        }
    };
    readiness.set(phase);
}

pub async fn prepare<S: ObjectStore>(store: &S, data_dir: &Path) -> Result<Loaded, DatasetError> {
    tokio::fs::create_dir_all(data_dir).await?;
    let remote = store.list().await?;
    let remote_csvs = csv_objects(&remote);
    let (identity, parquet) = if remote_csvs.is_empty() {
        build_local(data_dir).await?
    } else {
        build_remote(store, &remote, &remote_csvs, data_dir).await?
    };
    let scan_path = parquet.clone();
    let categories = blocking(move || categories::compute(&scan_path)).await?;
    tracing::info!(%identity, "OpenPowerlifting dataset ready");
    Ok(Loaded {
        parquet,
        identity,
        categories,
    })
}

fn csv_objects(objects: &[ObjectMeta]) -> Vec<&ObjectMeta> {
    let mut csvs: Vec<&ObjectMeta> = objects
        .iter()
        .filter(|object| object.key.starts_with(PREFIX) && object.key.ends_with(".csv"))
        .collect();
    csvs.sort_by(|a, b| a.key.cmp(&b.key));
    csvs
}

fn basename(key: &str) -> &str {
    key.rsplit('/').next().unwrap_or(key)
}

pub fn identity<'a>(files: impl IntoIterator<Item = (&'a str, u64, i64)>) -> String {
    let joined = files
        .into_iter()
        .map(|(name, size, modified)| format!("{name}:{size}:{modified}"))
        .collect::<Vec<_>>()
        .join("|");
    hex::encode(Sha256::digest(joined.as_bytes()))[..16].to_owned()
}

fn parquet_path(data_dir: &Path, identity: &str) -> PathBuf {
    data_dir.join(format!("openpowerlifting-{identity}.parquet"))
}

async fn build_remote<S: ObjectStore>(
    store: &S,
    remote: &[ObjectMeta],
    csvs: &[&ObjectMeta],
    data_dir: &Path,
) -> Result<(String, PathBuf), DatasetError> {
    let identity = identity(
        csvs.iter()
            .map(|csv| (basename(&csv.key), csv.size, csv.modified)),
    );
    let target = parquet_path(data_dir, &identity);
    let key = format!("{PREFIX}{identity}.parquet");
    if remote.iter().any(|object| object.key == key) {
        if !target.exists() {
            store.download(&key, &target).await?;
        }
        return Ok((identity, target));
    }
    let mut paths = Vec::with_capacity(csvs.len());
    for csv in csvs {
        let path = data_dir.join(basename(&csv.key));
        store.download(&csv.key, &path).await?;
        paths.push(path);
    }
    let output = target.clone();
    let sources = paths.clone();
    blocking(move || convert(&sources, &output)).await?;
    store.upload(&target, &key).await?;
    for path in paths {
        tokio::fs::remove_file(path).await?;
    }
    Ok((identity, target))
}

async fn build_local(data_dir: &Path) -> Result<(String, PathBuf), DatasetError> {
    let csvs = local_csvs(data_dir)?;
    if csvs.is_empty() {
        return Err(DatasetError::Missing(
            data_dir
                .join("openpowerlifting-*.csv")
                .display()
                .to_string(),
        ));
    }
    let stats = csvs
        .iter()
        .map(|path| local_stat(path))
        .collect::<Result<Vec<_>, _>>()?;
    let identity = identity(
        stats
            .iter()
            .map(|(name, size, modified)| (name.as_str(), *size, *modified)),
    );
    let target = parquet_path(data_dir, &identity);
    if !target.exists() {
        let output = target.clone();
        blocking(move || convert(&csvs, &output)).await?;
    }
    Ok((identity, target))
}

fn local_csvs(data_dir: &Path) -> Result<Vec<PathBuf>, DatasetError> {
    let mut paths: Vec<PathBuf> = std::fs::read_dir(data_dir)?
        .filter_map(Result::ok)
        .map(|entry| entry.path())
        .filter(|path| {
            path.file_name()
                .and_then(|name| name.to_str())
                .is_some_and(|name| name.starts_with("openpowerlifting-") && name.ends_with(".csv"))
        })
        .collect();
    paths.sort();
    Ok(paths)
}

fn local_stat(path: &Path) -> Result<(String, u64, i64), DatasetError> {
    let meta = std::fs::metadata(path)?;
    let modified = meta
        .modified()?
        .duration_since(std::time::UNIX_EPOCH)
        .map_or(0, |elapsed| elapsed.as_secs() as i64);
    let name = path
        .file_name()
        .map(|name| name.to_string_lossy().into_owned())
        .unwrap_or_default();
    Ok((name, meta.len(), modified))
}

async fn blocking<T, F>(work: F) -> Result<T, DatasetError>
where
    F: FnOnce() -> PolarsResult<T> + Send + 'static,
    T: Send + 'static,
{
    tokio::task::spawn_blocking(work)
        .await
        .map_err(|error| DatasetError::Failed(error.to_string()))?
        .map_err(DatasetError::from)
}

pub fn convert(csvs: &[PathBuf], output: &Path) -> PolarsResult<()> {
    let frames = csvs
        .iter()
        .map(|path| scan_csv(path))
        .collect::<PolarsResult<Vec<_>>>()?;
    let mut combined = concat(frames, UnionArgs::default())?;
    let schema = combined.collect_schema()?;
    let temporary = output.with_extension("parquet.tmp");
    let options = ParquetWriteOptions {
        row_group_size: Some(ROW_GROUP_ROWS),
        ..Default::default()
    };
    combined
        .select(projection(&schema))
        .sink(
            SinkDestination::File {
                target: SinkTarget::Path(PlRefPath::try_from_path(&temporary)?),
            },
            FileWriteFormat::Parquet(Arc::new(options)),
            UnifiedSinkArgs::default(),
        )?
        .collect_with_engine(Engine::Streaming)?;
    std::fs::rename(&temporary, output).map_err(|error| polars_err!(ComputeError: "{error}"))
}

fn scan_csv(path: &Path) -> PolarsResult<LazyFrame> {
    LazyCsvReader::new(PlRefPath::try_from_path(path)?)
        .with_infer_schema_length(Some(0))
        .with_has_header(true)
        .finish()
}

fn projection(schema: &Schema) -> Vec<Expr> {
    let present = |name: &str| schema.contains(name);
    let mut columns = vec![if present("Name") {
        col("Name")
    } else {
        lit(NULL).cast(DataType::String).alias("Name")
    }];
    columns.extend(TEXT_COLUMNS.iter().map(|name| {
        if present(name) {
            trimmed(name)
        } else {
            lit(NULL).cast(DataType::String).alias(*name)
        }
    }));
    columns.extend(FLOAT_COLUMNS.iter().map(|name| {
        if present(name) {
            col(*name).cast(DataType::Float32)
        } else {
            lit(NULL).cast(DataType::Float32).alias(*name)
        }
    }));
    columns.push(year(present("Date")));
    columns
}

fn trimmed(name: &str) -> Expr {
    let stripped = col(name).str().strip_chars(lit(NULL));
    when(stripped.clone().eq(lit("")))
        .then(lit(NULL))
        .otherwise(stripped)
        .alias(name)
}

fn year(has_date: bool) -> Expr {
    if has_date {
        col("Date")
            .str()
            .slice(lit(0), lit(4))
            .cast(DataType::Float32)
            .alias("Year")
    } else {
        lit(NULL).cast(DataType::Float32).alias("Year")
    }
}
