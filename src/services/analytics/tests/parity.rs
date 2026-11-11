mod common;

use common::{Fixtures, assert_matches, fixtures};
use pl_analytics::assemble::Scope;
use pl_analytics::calc::Env;
use pl_analytics::operations::Registry;
use pl_analytics::sections::{self, Params};
use pl_analytics::source::Window;
use pl_analytics::windows::{self, WindowKey};
use serde_json::{Map, Value, json};

fn object(value: Value) -> Map<String, Value> {
    match value {
        Value::Object(map) => map,
        _ => Map::new(),
    }
}

async fn section_payload(fixtures: &Fixtures, window_key: &str, section: &str) -> Value {
    let engine = fixtures.engine();
    let loaded = engine
        .load(
            &fixtures.athlete,
            &Window::default(),
            Scope::Block("current"),
        )
        .await
        .expect("fixture loads");
    let built = windows::build(&loaded.program, fixtures.as_of).expect("windows build");
    let window = &built[&WindowKey::parse(window_key)];
    let params = Params {
        weeks: window.weeks,
        block: Some("current".to_owned()),
        window_start: Some(window.start.clone()),
        window_end: Some(window.end.clone()),
        ref_date: Some(fixtures.as_of.to_string()),
        week_start: Some(window.week_start),
        week_end: Some(window.week_end),
    };
    let env = Env {
        today: fixtures.as_of,
        glossary: &loaded.glossary,
    };
    sections::compute(env, &loaded.program, section, &params).expect("section computes")
}

async fn check_section(section: &str) {
    let Some(fixtures) = fixtures() else { return };
    let registry = Registry::load().expect("contract loads");
    let mut checked = 0;
    for (file, inputs) in fixtures.calls("analytics.sections_get") {
        if inputs["sectionKey"] != section {
            continue;
        }
        let window = inputs["window"].as_str().unwrap_or("current").to_owned();
        let golden = fixtures.golden(&file);
        let actual = section_payload(&fixtures, &window, section).await;
        assert_matches(
            &format!("{file} payload"),
            &golden["body"]["payload"],
            &actual,
        );
        let status = pl_analytics::records::SectionStatus::complete(section, "fingerprint", actual);
        let mut body = serde_json::to_value(&status).expect("status serializes");
        body["asOfDate"] = json!(fixtures.as_of.to_string());
        body["windowKey"] = json!(window);
        registry
            .get("analytics.sections_get")
            .expect("operation exists")
            .validate_result(&body)
            .expect("result schema holds");
        assert_eq!(golden["body"]["status"], body["status"], "{file}");
        assert_eq!(golden["body"]["sectionKey"], body["sectionKey"], "{file}");
        checked += 1;
    }
    eprintln!("{section}: {checked} golden(s) matched");
}

#[tokio::test(flavor = "multi_thread")]
async fn overview() {
    check_section("overview").await;
}

#[tokio::test(flavor = "multi_thread")]
async fn workload() {
    check_section("workload").await;
}

#[tokio::test(flavor = "multi_thread")]
async fn fatigue_readiness() {
    check_section("fatigue_readiness").await;
}

#[tokio::test(flavor = "multi_thread")]
async fn peaking() {
    check_section("peaking").await;
}

#[tokio::test(flavor = "multi_thread")]
async fn alerts() {
    check_section("alerts").await;
}

#[tokio::test(flavor = "multi_thread")]
async fn manifests() {
    let Some(fixtures) = fixtures() else { return };
    let engine = fixtures.engine();
    for (file, inputs) in fixtures.calls("analytics.manifest") {
        let window = inputs["window"].as_str().unwrap_or("current");
        let golden = fixtures.golden(&file);
        let args = object(
            json!({"pk": fixtures.athlete, "asOfDate": fixtures.as_of.to_string(), "window": window}),
        );
        let actual = engine.manifest(args).await.expect("manifest builds");
        for field in ["schemaVersion", "asOfDate", "windowKey", "windows"] {
            assert_matches(
                &format!("{file}.{field}"),
                &golden["body"][field],
                &actual[field],
            );
        }
        let expected_sections: Vec<&String> = golden["body"]["sections"]
            .as_object()
            .map(|map| map.keys().collect())
            .unwrap_or_default();
        let actual_sections: Vec<&String> = actual["sections"]
            .as_object()
            .map(|map| map.keys().collect())
            .unwrap_or_default();
        let (mut expected_sorted, mut actual_sorted) = (expected_sections, actual_sections);
        expected_sorted.sort();
        actual_sorted.sort();
        assert_eq!(expected_sorted, actual_sorted, "{file} section keys");
    }
}

#[tokio::test(flavor = "multi_thread")]
async fn weekly() {
    let Some(fixtures) = fixtures() else { return };
    let engine = fixtures.engine();
    let registry = Registry::load().expect("contract loads");
    for (file, inputs) in fixtures.calls("analytics.weekly") {
        let golden = fixtures.golden(&file);
        let args = object(json!({
            "pk": fixtures.athlete,
            "weeks": inputs["weeks"],
            "block": inputs["block"],
            "refDate": inputs["refDate"],
        }));
        let actual = engine.weekly(args).await.expect("weekly computes");
        assert_matches(&file, &golden["body"], &actual);
        registry
            .get("analytics.weekly")
            .expect("operation exists")
            .validate_result(&actual)
            .expect("result schema holds");
    }
}

async fn check_exercise(operation: &str, call: &str) {
    let Some(fixtures) = fixtures() else { return };
    let engine = fixtures.engine();
    let registry = Registry::load().expect("contract loads");
    for (file, inputs) in fixtures.calls(operation) {
        let golden = fixtures.golden(&file);
        let args = object(json!({
            "pk": fixtures.athlete,
            "exercise_name": inputs["exercise_name"],
            "window_weeks": inputs["window_weeks"],
        }));
        let actual = match call {
            "progression" => engine.progression(args).await,
            _ => engine.drift(args).await,
        }
        .expect("operation computes");
        assert_matches(&file, &golden["body"], &actual);
        registry
            .get(operation)
            .expect("operation exists")
            .validate_result(&actual)
            .expect("result schema holds");
    }
}

#[tokio::test(flavor = "multi_thread")]
async fn progression() {
    check_exercise("analyze_progression", "progression").await;
}

#[tokio::test(flavor = "multi_thread")]
async fn rpe_drift() {
    check_exercise("analyze_rpe_drift", "drift").await;
}
