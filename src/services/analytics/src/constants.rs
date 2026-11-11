use std::collections::HashMap;
use std::sync::LazyLock;

use serde::Deserialize;

const CONSTANTS: &str = include_str!("../../calculation_constants.json");

#[derive(Deserialize)]
pub struct DotsCoefficients {
    pub a: f64,
    pub b: f64,
    pub c: f64,
    pub d: f64,
    pub e: f64,
}

#[derive(Deserialize)]
struct Constants {
    rpe_percent: HashMap<String, f64>,
    dots_coefficients: HashMap<String, DotsCoefficients>,
}

static LOADED: LazyLock<Constants> =
    LazyLock::new(|| serde_json::from_str(CONSTANTS).expect("calculation_constants.json is valid"));

pub fn rpe_percent(reps: i64, rpe: i64) -> Option<f64> {
    LOADED.rpe_percent.get(&format!("{reps}-{rpe}")).copied()
}

pub fn dots_coefficients(sex: &str) -> Option<&'static DotsCoefficients> {
    LOADED.dots_coefficients.get(sex)
}
