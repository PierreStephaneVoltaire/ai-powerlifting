use std::fmt::Write;

use serde_json::Value;

pub fn dumps(value: &Value, sort_keys: bool) -> String {
    let mut out = String::new();
    write_value(&mut out, value, sort_keys);
    out
}

fn write_value(out: &mut String, value: &Value, sort_keys: bool) {
    match value {
        Value::Null => out.push_str("null"),
        Value::Bool(flag) => out.push_str(if *flag { "true" } else { "false" }),
        Value::Number(number) => out.push_str(&number.to_string()),
        Value::String(text) => write_string(out, text),
        Value::Array(items) => write_array(out, items, sort_keys),
        Value::Object(map) => {
            let mut entries: Vec<_> = map.iter().collect();
            if sort_keys {
                entries.sort_by(|a, b| a.0.cmp(b.0));
            }
            out.push('{');
            for (index, (key, item)) in entries.into_iter().enumerate() {
                if index > 0 {
                    out.push_str(", ");
                }
                write_string(out, key);
                out.push_str(": ");
                write_value(out, item, sort_keys);
            }
            out.push('}');
        }
    }
}

fn write_array(out: &mut String, items: &[Value], sort_keys: bool) {
    out.push('[');
    for (index, item) in items.iter().enumerate() {
        if index > 0 {
            out.push_str(", ");
        }
        write_value(out, item, sort_keys);
    }
    out.push(']');
}

fn write_string(out: &mut String, text: &str) {
    out.push('"');
    for ch in text.chars() {
        match ch {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            '\u{8}' => out.push_str("\\b"),
            '\u{c}' => out.push_str("\\f"),
            ' '..='~' | '\u{7f}' => out.push(ch),
            _ => write_escaped(out, ch),
        }
    }
    out.push('"');
}

fn write_escaped(out: &mut String, ch: char) {
    let mut units = [0u16; 2];
    for unit in ch.encode_utf16(&mut units) {
        let _ = write!(out, "\\u{unit:04x}");
    }
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::*;

    #[test]
    fn matches_python_default_separators_and_sorting() {
        let value = json!({"b": 1, "a": [1.5, null, "x"]});
        assert_eq!(dumps(&value, true), r#"{"a": [1.5, null, "x"], "b": 1}"#);
    }

    #[test]
    fn escapes_like_ensure_ascii() {
        assert_eq!(dumps(&json!("é\n😀"), false), r#""\u00e9\n\ud83d\ude00""#);
    }

    #[test]
    fn keeps_float_and_int_distinct() {
        assert_eq!(dumps(&json!([180, 180.0]), false), "[180, 180.0]");
    }
}
