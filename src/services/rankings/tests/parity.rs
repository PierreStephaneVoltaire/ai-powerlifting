use std::path::{Path, PathBuf};
use std::time::Duration;

use pl_rankings::cache::Cache;
use pl_rankings::dataset::{Phase, Readiness, prepare};
use pl_rankings::ops::{Engine, Handler};
use pl_rankings::store::NoStore;
use serde_json::Value;

fn subrepo_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(3)
        .expect("crate lives three levels below the subrepo root")
        .to_path_buf()
}

fn dataset_csvs(root: &Path) -> Vec<PathBuf> {
    let Ok(entries) = std::fs::read_dir(root.join("fixtures/opl")) else {
        return Vec::new();
    };
    let mut csvs: Vec<PathBuf> = entries
        .filter_map(Result::ok)
        .map(|entry| entry.path())
        .filter(|path| path.extension().is_some_and(|extension| extension == "csv"))
        .collect();
    csvs.sort();
    csvs
}

fn close(expected: &Value, actual: &Value, path: &str, failures: &mut Vec<String>) {
    match (expected, actual) {
        (Value::Number(a), Value::Number(b)) => {
            let (a, b) = (
                a.as_f64().unwrap_or(f64::NAN),
                b.as_f64().unwrap_or(f64::NAN),
            );
            if (a - b).abs() > 1e-9 && (a - b).abs() > 1e-6 * a.abs().max(b.abs()) {
                failures.push(format!("{path}: {a} != {b}"));
            }
        }
        (Value::Object(a), Value::Object(b)) => {
            if a.len() != b.len() {
                failures.push(format!("{path}: key sets differ"));
            }
            for (key, value) in a {
                match b.get(key) {
                    Some(other) => close(value, other, &format!("{path}.{key}"), failures),
                    None => failures.push(format!("{path}.{key}: missing")),
                }
            }
        }
        (Value::Array(a), Value::Array(b)) => {
            if a.len() != b.len() {
                failures.push(format!("{path}: length {} != {}", a.len(), b.len()));
            }
            for (index, (x, y)) in a.iter().zip(b).enumerate() {
                close(x, y, &format!("{path}[{index}]"), failures);
            }
        }
        _ if expected == actual => {}
        _ => failures.push(format!("{path}: {expected} != {actual}")),
    }
}

fn handler(operation: &str) -> Option<Handler> {
    Handler::for_operation(operation)
}

#[tokio::test]
async fn rankings_match_operator_goldens() {
    let root = subrepo_root();
    let csvs = dataset_csvs(&root);
    let golden = root.join("fixtures/operator/golden");
    let manifest_path = golden.join("manifest.json");
    if csvs.is_empty() || !manifest_path.exists() {
        println!(
            "skipping parity: fixtures/opl/*.csv or fixtures/operator/golden/manifest.json missing"
        );
        return;
    }
    let manifest: Value = serde_json::from_slice(&std::fs::read(manifest_path).unwrap()).unwrap();
    let data = tempfile::tempdir().unwrap();
    for csv in &csvs {
        std::os::unix::fs::symlink(csv, data.path().join(csv.file_name().unwrap())).unwrap();
    }
    let loaded = prepare(&NoStore, data.path()).await.unwrap();
    let readiness = Readiness::new();
    readiness.set(Phase::Ready(std::sync::Arc::new(loaded)));
    let engine = Engine::new(readiness, Cache::disabled(), Duration::from_secs(5), 2);

    let mut failures = Vec::new();
    let mut compared = 0;
    for call in manifest["calls"].as_array().unwrap() {
        let operation = call["operation"].as_str().unwrap();
        let Some(handler) = handler(operation) else {
            continue;
        };
        if call["status"] != 200 {
            continue;
        }
        let body: Value = serde_json::from_slice(
            &std::fs::read(golden.join(call["file"].as_str().unwrap())).unwrap(),
        )
        .unwrap();
        let args = call["inputs"].as_object().unwrap();
        let actual = engine.run(handler, args).await.unwrap();
        close(&body["body"], &actual, operation, &mut failures);
        compared += 1;
    }
    println!("compared {compared} ranking goldens");
    assert!(failures.is_empty(), "{}", failures.join("\n"));
}
