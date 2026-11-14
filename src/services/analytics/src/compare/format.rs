pub fn number(value: f64) -> String {
    if value.is_finite() && value.fract() == 0.0 && value.abs() < 1e15 {
        format!("{}", value as i64)
    } else {
        format!("{value}")
    }
}

pub fn optional(value: Option<f64>, missing: &str) -> String {
    value.map_or_else(|| missing.to_owned(), number)
}

pub fn grouped(value: f64) -> String {
    let rounded = crate::js::round_half_up(value) as i64;
    let digits = rounded.unsigned_abs().to_string();
    let mut out = String::new();
    for (index, ch) in digits.chars().enumerate() {
        if index > 0 && (digits.len() - index).is_multiple_of(3) {
            out.push(',');
        }
        out.push(ch);
    }
    if rounded < 0 {
        out.insert(0, '-');
    }
    out
}

pub fn plural(count: i64) -> &'static str {
    if count == 1 { "" } else { "s" }
}
