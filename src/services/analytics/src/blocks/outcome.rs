use serde_json::{Map, Value, json};

use super::competitions::{flag_truthy, has_results, results_of};
use super::types::{Link, Outcome};
use crate::calc::scoring;
use crate::js::{coerce_number, number, round_digits, round_or_null};
use crate::util::round;

const IPF_GL_MALE: (f64, f64, f64) = (1199.72839, 1025.18162, 0.00921);
const IPF_GL_FEMALE: (f64, f64, f64) = (610.32796, 1045.59282, 0.03048);

pub fn dots(total_kg: f64, bodyweight_kg: f64, sex: &str) -> Option<f64> {
    if total_kg > 0.0 && bodyweight_kg > 0.0 {
        scoring::dots(total_kg, bodyweight_kg, sex)
    } else {
        None
    }
}

pub fn ipf_gl(total_kg: f64, bodyweight_kg: f64, sex: &str) -> Option<f64> {
    if total_kg <= 0.0 || bodyweight_kg <= 0.0 {
        return None;
    }
    let (a, b, c) = if sex == "female" {
        IPF_GL_FEMALE
    } else {
        IPF_GL_MALE
    };
    let denominator = a - b * (-c * bodyweight_kg).exp();
    (denominator.abs() >= 1e-12).then(|| round(total_kg * 100.0 / denominator, 2))
}

fn record<'a>(value: Option<&'a Value>) -> Option<&'a Map<String, Value>> {
    value.and_then(Value::as_object)
}

pub fn projection_results(weekly: &Value, linked: Option<&Link>) -> Option<Value> {
    let projections = weekly.get("projections").and_then(Value::as_array)?;
    let chosen = projections
        .iter()
        .find(|item| {
            linked.is_some_and(|link| {
                !link.name.is_empty()
                    && item.get("comp_name").and_then(Value::as_str) == Some(link.name.as_str())
            })
        })
        .or_else(|| projections.first());
    let projection = record(chosen);
    let lifts = record(projection.and_then(|map| map.get("lifts")));
    let lift_value = |lift: &str| -> f64 {
        let nested = lifts
            .and_then(|map| map.get(lift))
            .and_then(|entry| entry.get("projected"))
            .filter(|value| !value.is_null());
        let value = number(nested.or_else(|| projection.and_then(|map| map.get(lift))));
        value
            .filter(|projected| *projected > 0.0)
            .map_or(0.0, |projected| round_digits(projected, 1))
    };
    let (squat, bench, deadlift) = (
        lift_value("squat"),
        lift_value("bench"),
        lift_value("deadlift"),
    );
    let total = number(projection.and_then(|map| map.get("total")));
    if squat <= 0.0 && bench <= 0.0 && deadlift <= 0.0 && total.is_none_or(|total| total <= 0.0) {
        return None;
    }
    let total = total
        .filter(|total| *total > 0.0)
        .map_or_else(|| round_digits(squat + bench + deadlift, 1), |total| round_digits(total, 1));
    Some(json!({
        "squat_kg": squat,
        "bench_kg": bench,
        "deadlift_kg": deadlift,
        "total_kg": total,
    }))
}

pub fn summarize(
    sex: &str,
    linked: Option<&Link>,
    fallback: Option<Value>,
) -> Option<Outcome> {
    let link = linked?;
    let competition = &link.competition;
    let results = results_of(competition).filter(|results| has_results(Some(results)));
    let bodyweight = number(competition.get("body_weight_kg")).filter(|kg| *kg > 0.0);
    let total = results
        .and_then(|results| number(results.get("total_kg")))
        .filter(|total| *total > 0.0);
    let projected = results_of(competition)
        .and_then(|results| results.get("projected_at_t_minus_1w"))
        .filter(|value| !value.is_null())
        .or_else(|| {
            competition
                .get("projected_at_t_minus_1w")
                .filter(|value| !value.is_null())
        })
        .cloned()
        .or(fallback);
    let accuracy = match (results, projected.as_ref()) {
        (Some(results), Some(projected)) => Some(accuracy(results, projected)),
        _ => None,
    };
    let scored = total.zip(bodyweight);
    Some(Outcome {
        competition_name: link.name.clone(),
        competition_date: link.date.clone(),
        bodyweight_kg: bodyweight,
        results: results.cloned(),
        dots: scored.and_then(|(total, weight)| dots(total, weight, sex)),
        ipf_gl: scored.and_then(|(total, weight)| ipf_gl(total, weight, sex)),
        ipf_gl_mode: scored.map(|_| "classic_powerlifting".to_owned()),
        projected_at_t_minus1w: projected,
        projection_accuracy: accuracy,
        prr: results_of(competition)
            .and_then(|results| results.get("prr"))
            .filter(|value| !value.is_null())
            .cloned(),
        post_meet_report_captured: flag_truthy(competition, "post_meet_report"),
    })
}

fn accuracy(results: &Value, projected: &Value) -> Map<String, Value> {
    let mut map = Map::new();
    for key in ["squat_kg", "bench_kg", "deadlift_kg", "total_kg"] {
        let actual = coerce_number(results.get(key));
        let forecast = coerce_number(projected.get(key));
        if actual > 0.0 && forecast > 0.0 {
            map.insert(
                key.to_owned(),
                json!({
                    "actualKg": actual,
                    "projectedKg": forecast,
                    "deltaKg": round_or_null(Some(actual - forecast), 1).unwrap_or(0.0),
                    "deltaPct": round_or_null(Some((actual - forecast) / forecast * 100.0), 1),
                }),
            );
        }
    }
    map
}
