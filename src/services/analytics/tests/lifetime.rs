mod common;

use common::fixtures;
use pl_analytics::operations::Registry;
use serde_json::{Map, Value, json};

fn arguments(value: Value) -> Map<String, Value> {
    match value {
        Value::Object(map) => map,
        _ => Map::new(),
    }
}

fn shape(value: &Value) -> Value {
    match value {
        Value::Null => json!("null"),
        Value::Bool(_) => json!("bool"),
        Value::Number(_) => json!("number"),
        Value::String(_) => json!("string"),
        Value::Array(items) => {
            let merged = items.iter().map(shape).reduce(merge);
            json!([merged.unwrap_or(json!("empty"))])
        }
        Value::Object(map) => Value::Object(
            map.iter()
                .map(|(key, item)| (key.clone(), shape(item)))
                .collect(),
        ),
    }
}

fn merge(left: Value, right: Value) -> Value {
    match (left, right) {
        (Value::Object(mut a), Value::Object(b)) => {
            for (key, value) in b {
                let merged = match a.remove(&key) {
                    Some(existing) => merge(existing, value),
                    None => value,
                };
                a.insert(key, merged);
            }
            Value::Object(a)
        }
        (Value::Array(a), Value::Array(b)) => {
            let first = a.into_iter().next().unwrap_or(json!("empty"));
            let second = b.into_iter().next().unwrap_or(json!("empty"));
            json!([merge(first, second)])
        }
        (a, b) if a == b => a,
        (Value::String(a), Value::String(b)) if a == "empty" => Value::String(b),
        (Value::String(a), Value::String(b)) if b == "empty" => Value::String(a),
        (Value::String(a), other) | (other, Value::String(a)) if a == "null" => other,
        (Value::String(a), Value::String(b)) => {
            let mut parts: Vec<&str> = a.split('|').chain(b.split('|')).collect();
            parts.sort_unstable();
            parts.dedup();
            Value::String(parts.join("|"))
        }
        (a, _) => a,
    }
}

async fn report() -> Option<Value> {
    let fixtures = fixtures()?;
    let engine = fixtures.engine();
    Some(
        engine
            .lifetime_report(arguments(json!({"pk": fixtures.athlete})))
            .await
            .expect("lifetime builds"),
    )
}

#[tokio::test(flavor = "multi_thread")]
async fn report_validates_and_keeps_its_shape() {
    let Some(report) = report().await else { return };
    Registry::load()
        .expect("contract loads")
        .get("analytics.lifetime")
        .expect("operation exists")
        .validate_result(&report)
        .expect("result schema holds");
    insta::assert_json_snapshot!("lifetime_shape", shape(&report));
}

#[tokio::test(flavor = "multi_thread")]
async fn report_covers_every_block_with_stored_thresholds() {
    let Some(report) = report().await else { return };
    let fixtures = fixtures().expect("fixtures");
    let blocks = report["blocks"].as_array().expect("blocks");
    assert_eq!(
        blocks.len(),
        fixtures.manifest["blockKeys"]
            .as_array()
            .map_or(0, Vec::len)
    );
    assert_eq!(report["block_count"], json!(blocks.len()));
    let thresholds = &report["classification"]["thresholds"];
    assert!(thresholds["noise_multiplier"].is_number());
    for block in blocks {
        let label = block["classification"]["overall"]["label"]
            .as_str()
            .expect("overall label");
        assert!(["improved", "stalled", "regressed", "insufficient_data"].contains(&label));
    }
    for correlation in report["correlations"].as_array().expect("correlations") {
        let n = correlation["n"].as_i64().expect("n");
        assert_eq!(correlation["low_n"].as_bool().expect("low_n"), n < 5);
        assert_eq!(
            correlation["observations"].as_array().map(Vec::len),
            Some(n as usize)
        );
    }
}
