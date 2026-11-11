use chrono::NaiveDate;
use serde_json::{Map, Value};
use sha1::Sha1;
use sha2::{Digest, Sha256};

pub fn round_half_up(value: f64) -> f64 {
    (value + 0.5).floor()
}

pub fn round_digits(value: f64, digits: i32) -> f64 {
    let factor = 10f64.powi(digits);
    round_half_up(value * factor) / factor
}

pub fn round_or_null(value: Option<f64>, digits: i32) -> Option<f64> {
    value
        .filter(|value| value.is_finite())
        .map(|value| round_digits(value, digits))
}

pub fn truthy(value: Option<&Value>) -> bool {
    match value {
        None | Some(Value::Null) => false,
        Some(Value::Bool(flag)) => *flag,
        Some(Value::Number(number)) => number.as_f64().is_some_and(|n| n != 0.0 && !n.is_nan()),
        Some(Value::String(text)) => !text.is_empty(),
        Some(_) => true,
    }
}

pub fn number(value: Option<&Value>) -> Option<f64> {
    value
        .and_then(Value::as_f64)
        .filter(|number| number.is_finite())
}

pub fn text<'a>(map: &'a Map<String, Value>, key: &str) -> &'a str {
    map.get(key).and_then(Value::as_str).unwrap_or_default()
}

pub fn coerce_number(value: Option<&Value>) -> f64 {
    match value {
        Some(Value::Number(number)) => number.as_f64().unwrap_or(0.0),
        Some(Value::String(text)) => text.trim().parse().unwrap_or(0.0),
        Some(Value::Bool(flag)) => f64::from(u8::from(*flag)),
        _ => 0.0,
    }
}

pub fn iso_date(text: &str) -> Option<NaiveDate> {
    let bytes = text.as_bytes();
    let shaped = bytes.len() == 10
        && bytes.iter().enumerate().all(|(index, byte)| {
            if index == 4 || index == 7 {
                *byte == b'-'
            } else {
                byte.is_ascii_digit()
            }
        });
    if shaped {
        NaiveDate::parse_from_str(text, "%Y-%m-%d").ok()
    } else {
        None
    }
}

pub fn sha256_hex(value: &Value) -> String {
    let bytes = serde_json::to_vec(value).unwrap_or_default();
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

pub fn sha1_prefix(text: &str, length: usize) -> String {
    let hex: String = Sha1::digest(text.as_bytes())
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect();
    hex[..length].to_owned()
}

pub fn locale_order(a: &str, b: &str) -> std::cmp::Ordering {
    a.to_lowercase()
        .cmp(&b.to_lowercase())
        .then_with(|| b.cmp(a))
}
