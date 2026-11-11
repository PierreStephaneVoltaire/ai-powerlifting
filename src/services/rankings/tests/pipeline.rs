mod common;

use std::collections::BTreeSet;
use std::path::{Path, PathBuf};
use std::time::Duration;

use common::{Row, args, ready_engine, synthetic_rows, write_csv};
use pl_rankings::cache::Cache;
use pl_rankings::dataset::{DatasetError, Phase, Readiness, boot};
use pl_rankings::ops::{Engine, Handler};
use pl_rankings::query::current_year;
use pl_rankings::store::{ObjectMeta, ObjectStore};
use serde_json::{Value, json};

fn setup(count: usize) -> (tempfile::TempDir, Vec<Row>) {
    let dir = tempfile::tempdir().unwrap();
    let rows = synthetic_rows(count);
    write_csv(&dir.path().join("openpowerlifting-test.csv"), &rows);
    (dir, rows)
}

fn recent_deduped(rows: &[Row], keep: impl Fn(&Row) -> bool) -> Vec<Row> {
    let year = current_year();
    let mut candidates: Vec<&Row> = rows
        .iter()
        .filter(|row| row.event == "SBD" && row.year >= year - 2 && keep(row))
        .collect();
    candidates.sort_by(|a, b| match (a.total, b.total) {
        (Some(x), Some(y)) => y.total_cmp(&x),
        (Some(_), None) => std::cmp::Ordering::Less,
        (None, Some(_)) => std::cmp::Ordering::Greater,
        (None, None) => std::cmp::Ordering::Equal,
    });
    let mut seen = BTreeSet::new();
    candidates
        .into_iter()
        .filter(|row| seen.insert(row.name.clone()))
        .cloned()
        .collect()
}

fn percent_below(pool: &[f32], value: f32) -> Option<i64> {
    (pool.len() >= 10).then(|| {
        let below = pool.iter().filter(|v| **v < value).count();
        (below as f64 / pool.len() as f64 * 100.0).round_ties_even() as i64
    })
}

#[tokio::test]
async fn categories_come_from_the_converted_parquet() {
    let (dir, rows) = setup(400);
    let engine = ready_engine(dir.path()).await;
    let categories = engine
        .run(Handler::Categories, &args(json!({})))
        .await
        .unwrap();
    assert_eq!(categories["federations"], json!(["IPF", "USAPL"]));
    assert_eq!(categories["countries"], json!(["Canada", "USA"]));
    assert_eq!(categories["regions"], json!(["CA", "ON", "QC"]));
    assert_eq!(categories["equipment"], json!(["Raw", "Single-ply"]));
    assert_eq!(categories["sex"], json!(["F", "M"]));
    assert_eq!(categories["event_types"], json!(["B", "SBD"]));
    let year = current_year();
    assert_eq!(
        categories["years"],
        json!([year, year - 1, year - 2, year - 3])
    );
    assert_eq!(
        categories["country_federations"]["Canada"],
        json!(["IPF", "USAPL"])
    );
    assert_eq!(categories["country_regions"]["USA"], json!(["CA"]));
    assert_eq!(categories["region_federations"]["ON"], json!(["IPF"]));
    assert!(!rows.is_empty());
}

#[tokio::test]
async fn percentile_matches_a_brute_force_reference() {
    let (dir, rows) = setup(400);
    let engine = ready_engine(dir.path()).await;
    let result = engine
        .run(
            Handler::Percentile,
            &args(json!({
                "squat_kg": 200, "bench_kg": 120.5, "deadlift_kg": 250,
                "bodyweight_kg": 80, "sex_code": "M", "country": "canada", "region": "on",
                "equipment": "Raw", "pk": "operator"
            })),
        )
        .await
        .unwrap();
    let pool = recent_deduped(&rows, |row| {
        row.sex == "M" && row.equipment == "Raw" && row.bodyweight > 66.0 && row.bodyweight <= 93.0
    });
    let squats: Vec<f32> = pool.iter().map(|row| row.squat).collect();
    let totals: Vec<f32> = pool.iter().filter_map(|row| row.total).collect();
    assert_eq!(
        result["global"]["squat"],
        json!(percent_below(&squats, 200.0))
    );
    assert_eq!(
        result["global"]["total"],
        json!(percent_below(&totals, 570.5))
    );
    assert_eq!(result["meta"]["global_n"], json!(pool.len()));
    let canada = pool.iter().filter(|row| row.country == "Canada").count();
    assert_eq!(result["meta"]["national_n"], json!(canada));
    let ontario = pool
        .iter()
        .filter(|row| row.country == "Canada" && row.state == "ON")
        .count();
    assert_eq!(result["meta"]["regional_n"], json!(ontario));
    assert_eq!(result["weight_class_label"], json!("83kg"));
    assert!(result["global"]["top10_mean_squat"].is_f64());
}

#[tokio::test]
async fn percentile_is_null_for_small_pools_and_missing_scopes() {
    let (dir, _) = setup(400);
    let engine = ready_engine(dir.path()).await;
    let result = engine
        .run(
            Handler::Percentile,
            &args(json!({"squat_kg": 200, "bodyweight_kg": 80, "sex_code": "F", "age_class": "40-44"})),
        )
        .await
        .unwrap();
    assert_eq!(result["global"]["squat"], Value::Null);
    assert_eq!(result["global"]["top10_mean_squat"], Value::Null);
    assert_eq!(result["national"]["squat"], Value::Null);
    assert_eq!(result["meta"]["national_n"], Value::Null);
    assert_eq!(result["meta"]["regional_n"], Value::Null);
}

#[tokio::test]
async fn stats_match_a_brute_force_reference() {
    let (dir, rows) = setup(400);
    let engine = ready_engine(dir.path()).await;
    let result = engine
        .run(
            Handler::Stats,
            &args(json!({
                "sex": "F", "country": "CANADA", "squat_kg": 150, "bench_kg": 90,
                "deadlift_kg": 180, "bodyweight_kg": 63, "sex_code": "F"
            })),
        )
        .await
        .unwrap();
    let filtered: Vec<&Row> = rows
        .iter()
        .filter(|row| row.sex == "F" && row.country == "Canada")
        .collect();
    assert_eq!(result["dataset_size"], json!(filtered.len()));
    assert_eq!(result["computed"]["total_kg"], json!(420));
    assert!(result["computed"]["dots"].is_f64());
    let squats: Vec<f32> = filtered.iter().map(|row| row.squat).collect();
    let squat = &result["analysis"]["Squat"];
    let beat = squats.iter().filter(|v| **v < 150.0).count();
    assert_eq!(squat["n"], json!(squats.len()));
    assert_eq!(squat["beat"], json!(beat));
    assert_eq!(squat["rank"], json!(squats.len() - beat));
    assert_eq!(
        squat["max"],
        json!(squats.iter().cloned().fold(0.0f32, f32::max))
    );
    assert!(squat["pct_of_max"].is_string());
    assert!(result["analysis"]["Dots"]["n"].as_u64().unwrap() > 0);
}

#[tokio::test]
async fn stats_with_no_matches_have_empty_analysis() {
    let (dir, _) = setup(60);
    let engine = ready_engine(dir.path()).await;
    let result = engine
        .run(
            Handler::Stats,
            &args(json!({"federation": "NOPE", "squat_kg": 100})),
        )
        .await
        .unwrap();
    assert_eq!(result["dataset_size"], json!(0));
    assert_eq!(result["analysis"], json!({}));
    assert_eq!(result["computed"], json!({"total_kg": null, "dots": null}));
}

#[tokio::test]
async fn unready_dataset_returns_error_strings() {
    let readiness = Readiness::new();
    let engine = Engine::new(
        readiness.clone(),
        Cache::disabled(),
        Duration::from_millis(50),
        1,
    );
    let loading = engine
        .run(Handler::Categories, &args(json!({})))
        .await
        .unwrap();
    assert_eq!(
        loading,
        json!(
            "ERROR: Dataset not ready. The dataset is still loading in the background. Try again in a moment."
        )
    );
    let waited = engine
        .run(Handler::Percentile, &args(json!({})))
        .await
        .unwrap();
    assert_eq!(waited, loading);
    readiness.set(Phase::Failed(DatasetError::Missing(
        "/data/openpowerlifting-*.csv".into(),
    )));
    let missing = engine.run(Handler::Stats, &args(json!({}))).await.unwrap();
    assert_eq!(
        missing,
        json!(
            "ERROR: Dataset missing. No powerlifting datasets found in sandbox matching: /data/openpowerlifting-*.csv"
        )
    );
}

struct DirStore {
    root: PathBuf,
}

impl DirStore {
    fn path(&self, key: &str) -> PathBuf {
        self.root.join(key)
    }
}

impl ObjectStore for DirStore {
    async fn list(&self) -> Result<Vec<ObjectMeta>, DatasetError> {
        let folder = self.root.join("datasets");
        let Ok(entries) = std::fs::read_dir(folder) else {
            return Ok(Vec::new());
        };
        Ok(entries
            .filter_map(Result::ok)
            .map(|entry| ObjectMeta {
                key: format!("datasets/{}", entry.file_name().to_string_lossy()),
                size: entry.metadata().map_or(0, |meta| meta.len()),
                modified: 1_700_000_000,
            })
            .collect())
    }

    async fn download(&self, key: &str, dest: &Path) -> Result<(), DatasetError> {
        std::fs::copy(self.path(key), dest)?;
        Ok(())
    }

    async fn upload(&self, source: &Path, key: &str) -> Result<(), DatasetError> {
        std::fs::create_dir_all(self.path(key).parent().unwrap())?;
        std::fs::copy(source, self.path(key))?;
        Ok(())
    }
}

#[tokio::test]
async fn converted_parquet_is_uploaded_and_reused_by_the_next_replica() {
    let bucket = tempfile::tempdir().unwrap();
    let rows = synthetic_rows(200);
    std::fs::create_dir_all(bucket.path().join("datasets")).unwrap();
    write_csv(
        &bucket.path().join("datasets/openpowerlifting-test.csv"),
        &rows,
    );
    let store = DirStore {
        root: bucket.path().to_path_buf(),
    };

    let first_dir = tempfile::tempdir().unwrap();
    let first = Readiness::new();
    boot(&store, first_dir.path(), &first).await;
    let Phase::Ready(first_loaded) = first.current() else {
        panic!("first boot failed")
    };
    assert!(!first_dir.path().join("openpowerlifting-test.csv").exists());
    let parquet_key = format!(
        "datasets/openpowerlifting-{}.parquet",
        first_loaded.identity
    );
    assert!(bucket.path().join(&parquet_key).exists());

    let second_dir = tempfile::tempdir().unwrap();
    let second = Readiness::new();
    boot(&store, second_dir.path(), &second).await;
    let Phase::Ready(second_loaded) = second.current() else {
        panic!("second boot failed")
    };
    assert_eq!(second_loaded.identity, first_loaded.identity);
    assert_eq!(second_loaded.categories, first_loaded.categories);
    assert!(
        second_dir
            .path()
            .join(format!(
                "openpowerlifting-{}.parquet",
                second_loaded.identity
            ))
            .exists()
    );
    assert!(!second_dir.path().join("openpowerlifting-test.csv").exists());
}

#[tokio::test]
async fn missing_dataset_reports_failure() {
    let dir = tempfile::tempdir().unwrap();
    let readiness = Readiness::new();
    boot(&pl_rankings::store::NoStore, dir.path(), &readiness).await;
    assert!(matches!(
        readiness.current(),
        Phase::Failed(DatasetError::Missing(_))
    ));
}
