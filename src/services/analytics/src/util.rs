use std::cmp::Ordering;

use chrono::NaiveDate;
use serde_json::{Map, Value};
use statrs::statistics::{Data, OrderStatistics};

pub fn num(value: &Value) -> f64 {
    match value {
        Value::Null => 0.0,
        Value::Bool(flag) => f64::from(u8::from(*flag)),
        Value::Number(number) => number.as_f64().unwrap_or(0.0),
        Value::String(text) => text.trim().parse().unwrap_or(0.0),
        _ => 0.0,
    }
}

pub fn num_of(value: Option<&Value>) -> f64 {
    value.map_or(0.0, num)
}

pub fn present(value: Option<&Value>) -> Option<&Value> {
    value.filter(|value| !value.is_null())
}

pub fn truthy(value: &Value) -> bool {
    match value {
        Value::Null => false,
        Value::Bool(flag) => *flag,
        Value::Number(number) => number.as_f64() != Some(0.0),
        Value::String(text) => !text.is_empty(),
        Value::Array(items) => !items.is_empty(),
        Value::Object(map) => !map.is_empty(),
    }
}

pub fn truthy_of(value: Option<&Value>) -> bool {
    value.is_some_and(truthy)
}

pub fn text(map: &Map<String, Value>, key: &str) -> String {
    match map.get(key) {
        Some(Value::String(text)) => text.clone(),
        Some(Value::Null) | None => String::new(),
        Some(other) => other.to_string(),
    }
}

pub fn text_of(value: &str, default: &str) -> String {
    if value.is_empty() {
        default.to_owned()
    } else {
        value.to_owned()
    }
}

pub fn int_of(value: f64) -> i64 {
    value.trunc() as i64
}

pub fn clamp(value: f64, low: f64, high: f64) -> f64 {
    low.max(high.min(value))
}

pub fn round(value: f64, digits: usize) -> f64 {
    if !value.is_finite() {
        return value;
    }
    format!("{value:.digits$}").parse().unwrap_or(value)
}

pub fn round_even(value: f64) -> f64 {
    value.round_ties_even()
}

pub fn parse_date(text: &str) -> Option<NaiveDate> {
    NaiveDate::parse_from_str(text, "%Y-%m-%d").ok()
}

pub fn median(values: &[f64]) -> f64 {
    if values.is_empty() {
        return f64::NAN;
    }
    Data::new(values.to_vec()).median()
}

pub fn mean(values: &[f64]) -> f64 {
    values.iter().sum::<f64>() / values.len() as f64
}

pub fn population_sd(values: &[f64]) -> f64 {
    if values.len() < 2 {
        return 0.0;
    }
    let center = mean(values);
    (values
        .iter()
        .map(|value| (value - center).powi(2))
        .sum::<f64>()
        / values.len() as f64)
        .sqrt()
}

pub fn mad(values: &[f64]) -> f64 {
    if values.is_empty() {
        return 0.0;
    }
    let center = median(values);
    let deviations: Vec<f64> = values.iter().map(|value| (value - center).abs()).collect();
    median(&deviations)
}

#[derive(Clone, Copy, Debug)]
pub struct TheilSen {
    pub slope: f64,
    pub intercept: f64,
}

pub fn theil_sen(ys: &[f64], xs: &[f64]) -> TheilSen {
    let mut slopes = Vec::new();
    for (index, (x_a, y_a)) in xs.iter().zip(ys).enumerate() {
        for (x_b, y_b) in xs.iter().zip(ys).skip(index + 1) {
            let dx = x_b - x_a;
            if dx > 0.0 {
                slopes.push((y_b - y_a) / dx);
            } else if dx < 0.0 {
                slopes.push((y_a - y_b) / -dx);
            }
        }
    }
    let slope = median(&slopes);
    TheilSen {
        slope,
        intercept: median(ys) - slope * median(xs),
    }
}

pub fn kendall_tau(xs: &[f64], ys: &[f64]) -> f64 {
    kendalls::tau_b_with_comparator(xs, ys, |a, b| a.partial_cmp(b).unwrap_or(Ordering::Equal))
        .map(|(tau, _)| tau)
        .unwrap_or(f64::NAN)
}

pub fn ols_slope(xs: &[f64], ys: &[f64]) -> f64 {
    let count = xs.len() as f64;
    if xs.len() < 2 {
        return 0.0;
    }
    let sum_x: f64 = xs.iter().sum();
    let sum_xx: f64 = xs.iter().map(|x| x * x).sum();
    if (count * sum_xx - sum_x * sum_x).abs() < 1e-12 {
        return 0.0;
    }
    let fitted = linregress::RegressionDataBuilder::new()
        .build_from(vec![("Y", ys.to_vec()), ("X", xs.to_vec())])
        .ok()
        .and_then(|data| {
            linregress::FormulaRegressionBuilder::new()
                .data(&data)
                .formula("Y ~ X")
                .fit_without_statistics()
                .ok()
        });
    fitted
        .and_then(|params| params.get(1).copied())
        .unwrap_or(0.0)
}

fn singularize(word: &str) -> &str {
    if word.ends_with("sses")
        || word.ends_with("ches")
        || word.ends_with("shes")
        || word.ends_with("xes")
    {
        &word[..word.len() - 2]
    } else if word.ends_with('s') && !word.ends_with("ss") {
        &word[..word.len() - 1]
    } else {
        word
    }
}

pub fn normalize_name(name: &str) -> String {
    let mut stripped = String::with_capacity(name.len());
    let mut depth = 0usize;
    for character in name.chars() {
        match character {
            '(' => {
                depth += 1;
                stripped.push(' ');
            }
            ')' if depth > 0 => depth -= 1,
            _ if depth == 0 => stripped.push(character),
            _ => {}
        }
    }
    stripped
        .to_lowercase()
        .split_whitespace()
        .map(singularize)
        .collect::<Vec<_>>()
        .join(" ")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rounds_like_python() {
        assert_eq!(round(2.675, 2), 2.67);
        assert_eq!(round(0.125, 2), 0.12);
        assert_eq!(round_even(2.5), 2.0);
    }

    #[test]
    fn theil_sen_matches_scipy_on_simple_series() {
        let fit = theil_sen(&[1.0, 2.0, 4.0], &[0.0, 1.0, 2.0]);
        assert!((fit.slope - 1.5).abs() < 1e-12);
        assert!((fit.intercept - 0.5).abs() < 1e-12);
    }

    #[test]
    fn kendall_handles_ties() {
        assert!((kendall_tau(&[1.0, 2.0, 3.0], &[1.0, 2.0, 3.0]) - 1.0).abs() < 1e-12);
        assert!(kendall_tau(&[1.0, 1.0, 1.0], &[1.0, 2.0, 3.0]).is_nan());
    }

    #[test]
    fn ols_recovers_slope() {
        assert!((ols_slope(&[0.0, 1.0, 2.0], &[1.0, 3.0, 5.0]) - 2.0).abs() < 1e-9);
    }
}
