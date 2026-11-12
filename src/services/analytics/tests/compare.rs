mod common;

use std::collections::BTreeSet;

use common::fixtures;
use pl_analytics::operations::Registry;
use serde_json::{Value, json};

fn assert_finite(path: &str, value: &Value) {
    match value {
        Value::Number(number) => {
            assert!(
                number.as_f64().is_some_and(f64::is_finite),
                "{path} is not finite"
            );
        }
        Value::Array(items) => {
            for (index, item) in items.iter().enumerate() {
                assert_finite(&format!("{path}[{index}]"), item);
            }
        }
        Value::Object(map) => {
            for (key, item) in map {
                assert_finite(&format!("{path}.{key}"), item);
            }
        }
        _ => {}
    }
}

fn arguments(value: Value) -> serde_json::Map<String, Value> {
    match value {
        Value::Object(map) => map,
        _ => serde_json::Map::new(),
    }
}

#[tokio::test(flavor = "multi_thread")]
async fn comparison_validates_and_covers_every_block() {
    let Some(fixtures) = fixtures() else { return };
    let engine = fixtures.engine();
    let actual = engine
        .compare_blocks(arguments(json!({"pk": fixtures.athlete})))
        .await
        .expect("comparison builds");
    Registry::load()
        .expect("contract loads")
        .get("analytics.compare")
        .expect("operation exists")
        .validate_result(&actual)
        .expect("result schema holds");

    let expected: BTreeSet<String> = fixtures.manifest["blockKeys"]
        .as_array()
        .expect("block keys")
        .iter()
        .filter_map(|key| key.as_str().map(str::to_owned))
        .collect();
    let selected: Vec<String> = actual["selectedBlockKeys"]
        .as_array()
        .expect("selected keys")
        .iter()
        .filter_map(|key| key.as_str().map(str::to_owned))
        .collect();
    assert_eq!(selected.iter().cloned().collect::<BTreeSet<_>>(), expected);
    assert_eq!(selected.len(), expected.len(), "no duplicates");

    let rows = actual["rows"].as_array().expect("rows");
    assert_eq!(rows.len(), expected.len());
    let row_keys: Vec<&str> = rows
        .iter()
        .map(|row| row["blockKey"].as_str().expect("row key"))
        .collect();
    assert_eq!(
        row_keys,
        selected.iter().map(String::as_str).collect::<Vec<_>>()
    );
    let starts: Vec<&str> = rows
        .iter()
        .map(|row| row["startDate"].as_str().expect("start"))
        .collect();
    assert!(
        starts.windows(2).all(|pair| pair[0] <= pair[1]),
        "rows ordered by start date"
    );

    assert_finite("$", &actual);
    for series in actual["trends"].as_object().expect("trends").values() {
        let points = series.as_array().expect("trend series");
        assert_eq!(points.len(), rows.len());
        let order: Vec<&str> = points
            .iter()
            .map(|point| point["blockKey"].as_str().expect("point key"))
            .collect();
        assert_eq!(order, row_keys);
    }
    assert_eq!(
        actual["missingDataSummary"]
            .as_array()
            .expect("missing")
            .len(),
        rows.len()
    );
    for row in rows {
        assert!(row["totalVolumeKg"].is_number());
    }
    let tolerance = &actual["volumeTolerance"];
    assert!(tolerance["sampleSize"].as_i64().unwrap_or(-1) >= 0);
    assert!(
        tolerance["sampleSize"].as_i64() <= tolerance["requiredSampleSize"].as_i64()
            || tolerance["status"] == "estimated"
    );
    let weeks: Vec<(String, i64)> = actual["trendSeries"]
        .as_array()
        .expect("trend series")
        .iter()
        .map(|point| {
            (
                point["blockKey"].as_str().unwrap_or_default().to_owned(),
                point["weekNumber"].as_i64().unwrap_or(-1),
            )
        })
        .collect();
    for pair in weeks.windows(2) {
        if pair[0].0 == pair[1].0 {
            assert!(pair[0].1 < pair[1].1, "weeks ascend within a block");
        }
    }
}

#[tokio::test(flavor = "multi_thread")]
async fn explicit_selection_always_adds_the_current_block() {
    let Some(fixtures) = fixtures() else { return };
    let engine = fixtures.engine();
    let first = fixtures.manifest["blockKeys"][0].clone();
    let actual = engine
        .compare_blocks(arguments(
            json!({"pk": fixtures.athlete, "blockKeys": [first]}),
        ))
        .await
        .expect("comparison builds");
    let selected: BTreeSet<&str> = actual["selectedBlockKeys"]
        .as_array()
        .expect("selected")
        .iter()
        .filter_map(Value::as_str)
        .collect();
    assert!(selected.contains("current"));
    assert!(selected.contains(first.as_str().unwrap_or_default()));
    assert_eq!(selected.len(), 2);
}
