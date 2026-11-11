use std::path::PathBuf;
use std::sync::Arc;

use chrono::NaiveDate;
use pl_analytics::cache::Cache;
use pl_analytics::engine::{Clock, Engine};
use pl_analytics::source::fixture::FixtureSource;
use serde_json::Value;

pub const IGNORED_FIELDS: [&str; 3] = ["generatedAt", "updatedAt", "sourceFingerprint"];

pub struct Fixtures {
    pub root: PathBuf,
    pub manifest: Value,
    pub as_of: NaiveDate,
    pub athlete: String,
}

pub fn fixtures() -> Option<Fixtures> {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../../fixtures/operator");
    if !FixtureSource::available(&root.join("source"))
        || !root.join("golden/manifest.json").is_file()
    {
        eprintln!("skipping: fixtures/operator is not present");
        return None;
    }
    let manifest: Value =
        serde_json::from_slice(&std::fs::read(root.join("golden/manifest.json")).ok()?).ok()?;
    let as_of = manifest["asOfDate"].as_str()?.parse().ok()?;
    let athlete = manifest["athlete"].as_str()?.to_owned();
    Some(Fixtures {
        root,
        manifest,
        as_of,
        athlete,
    })
}

impl Fixtures {
    pub fn engine(&self) -> Engine {
        Engine::new(
            Arc::new(FixtureSource::new(self.root.join("source"))),
            Cache::disabled(),
            Clock::Fixed(self.as_of),
        )
    }

    pub fn golden(&self, file: &str) -> Value {
        let bytes = std::fs::read(self.root.join("golden").join(file)).expect("golden is readable");
        serde_json::from_slice(&bytes).expect("golden is json")
    }

    pub fn calls(&self, operation: &str) -> Vec<(String, Value)> {
        self.manifest["calls"]
            .as_array()
            .into_iter()
            .flatten()
            .filter(|call| call["operation"] == operation)
            .map(|call| {
                (
                    call["file"].as_str().unwrap_or_default().to_owned(),
                    call["inputs"].clone(),
                )
            })
            .collect()
    }
}

fn numbers_match(expected: f64, actual: f64) -> bool {
    (expected - actual).abs() <= f64::max(1e-9, 1e-6 * expected.abs())
}

pub fn diff(path: &str, expected: &Value, actual: &Value, out: &mut Vec<String>) {
    match (expected, actual) {
        (Value::Number(a), Value::Number(b)) => {
            if !numbers_match(
                a.as_f64().unwrap_or(f64::NAN),
                b.as_f64().unwrap_or(f64::NAN),
            ) {
                out.push(format!("{path}: expected {a} got {b}"));
            }
        }
        (Value::Object(a), Value::Object(b)) => {
            for key in a.keys().chain(b.keys().filter(|key| !a.contains_key(*key))) {
                if IGNORED_FIELDS.contains(&key.as_str()) {
                    continue;
                }
                match (a.get(key), b.get(key)) {
                    (Some(x), Some(y)) => diff(&format!("{path}.{key}"), x, y, out),
                    (Some(x), None) => out.push(format!(
                        "{path}.{key}: missing in actual (expected {})",
                        short(x)
                    )),
                    (None, Some(y)) => {
                        out.push(format!("{path}.{key}: unexpected in actual ({})", short(y)))
                    }
                    (None, None) => {}
                }
            }
        }
        (Value::Array(a), Value::Array(b)) => {
            if a.len() != b.len() {
                out.push(format!(
                    "{path}: length expected {} got {}",
                    a.len(),
                    b.len()
                ));
            }
            for (index, (x, y)) in a.iter().zip(b).enumerate() {
                diff(&format!("{path}[{index}]"), x, y, out);
            }
        }
        _ if expected == actual => {}
        _ => out.push(format!(
            "{path}: expected {} got {}",
            short(expected),
            short(actual)
        )),
    }
}

fn short(value: &Value) -> String {
    let text = value.to_string();
    if text.len() > 120 {
        format!("{}...", &text[..120])
    } else {
        text
    }
}

pub fn assert_matches(label: &str, expected: &Value, actual: &Value) {
    let mut differences = Vec::new();
    diff("", expected, actual, &mut differences);
    assert!(
        differences.is_empty(),
        "{label}: {} difference(s)\n{}",
        differences.len(),
        differences
            .iter()
            .take(25)
            .cloned()
            .collect::<Vec<_>>()
            .join("\n")
    );
}
