use std::collections::BTreeMap;
use std::io::Cursor;

use base64::{Engine, engine::general_purpose::STANDARD};
use calamine::{Data, DataType, Reader, open_workbook_auto_from_rs};
use chrono::NaiveDate;
use regex::Regex;
use serde_json::{Map, Value, json};
use sha2::{Digest, Sha256};

type Result<T> = std::result::Result<T, Box<dyn std::error::Error + Send + Sync>>;

#[derive(Debug)]
pub struct Extracted {
    pub rows: Vec<Value>,
    pub headings: BTreeMap<String, Vec<String>>,
    pub file_hash: String,
}

pub fn extract(content: &str, filename: &str, template: bool) -> Result<Extracted> {
    let bytes = STANDARD
        .decode(content)
        .map_err(|_| "base64_content is invalid")?;
    let digest = Sha256::digest(&bytes);
    let file_hash = format!(
        "sha256:{}",
        digest[..8]
            .iter()
            .map(|byte| format!("{byte:02x}"))
            .collect::<String>()
    );
    let (mut rows, headings) = if filename.to_ascii_lowercase().ends_with(".xlsx") {
        workbook(&bytes, template)?
    } else {
        (csv(&bytes)?, BTreeMap::new())
    };
    if template {
        normalize_dates(&mut rows);
    }
    Ok(Extracted {
        rows,
        headings,
        file_hash,
    })
}

fn csv(bytes: &[u8]) -> Result<Vec<Value>> {
    let text = String::from_utf8_lossy(bytes);
    let mut reader = csv::ReaderBuilder::new()
        .flexible(true)
        .from_reader(text.as_bytes());
    let headers = reader.headers()?.clone();
    let mut result = Vec::new();
    for row in reader.records() {
        let row = row?;
        if !row.iter().any(|cell| !cell.is_empty()) {
            continue;
        }
        let mut values = Map::new();
        for (index, header) in headers.iter().enumerate() {
            values.insert(
                header.to_owned(),
                row.get(index).map_or(Value::Null, |v| json!(v)),
            );
        }
        if row.len() > headers.len() {
            values.insert(
                "null".to_owned(),
                json!(row.iter().skip(headers.len()).collect::<Vec<_>>()),
            );
        }
        result.push(Value::Object(values));
    }
    Ok(result)
}

fn date(value: &str) -> Option<NaiveDate> {
    let value = value.trim();
    let date_part = value.split(['T', ' ']).next().unwrap_or(value);
    [
        "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d", "%m-%d-%Y", "%d-%m-%Y",
    ]
    .iter()
    .find_map(|format| NaiveDate::parse_from_str(date_part, format).ok())
}

fn training_header(row: &[Data]) -> bool {
    let names: Vec<String> = row
        .iter()
        .map(|v| v.to_string().trim().to_lowercase())
        .collect();
    names
        .iter()
        .any(|name| ["day", "day of week", "weekday"].contains(&name.as_str()))
        && names
            .iter()
            .any(|name| ["lift", "exercise", "exercise name", "movement"].contains(&name.as_str()))
}

fn value(cell: &Data) -> Value {
    match cell {
        Data::Empty => Value::Null,
        Data::String(v) | Data::DateTimeIso(v) | Data::DurationIso(v) => json!(v),
        Data::Bool(v) => json!(v),
        Data::Int(v) => json!(v),
        Data::Float(v) => json!(v),
        Data::DateTime(_) => cell
            .as_datetime()
            .map(|v| json!(v.date().to_string()))
            .unwrap_or(Value::Null),
        Data::Error(v) => json!(format!("{v:?}")),
    }
}

fn workbook(bytes: &[u8], template: bool) -> Result<(Vec<Value>, BTreeMap<String, Vec<String>>)> {
    let mut workbook = open_workbook_auto_from_rs(Cursor::new(bytes))?;
    let names = workbook.sheet_names().to_vec();
    let week_pattern = Regex::new(r"(?i)\bweek\s*#?\s*(\d+)\b")?;
    let mut rows = Vec::new();
    let mut headings = BTreeMap::new();
    for name in names {
        let range = workbook.worksheet_range(&name)?;
        let sheet: Vec<&[Data]> = range.rows().collect();
        if sheet.len() < 2 {
            continue;
        }
        let week = template
            .then(|| {
                week_pattern
                    .captures(&name)
                    .and_then(|c| c[1].parse::<u64>().ok())
            })
            .flatten();
        let header_index = if template {
            sheet
                .iter()
                .take(12)
                .position(|row| training_header(row))
                .unwrap_or(0)
        } else {
            0
        };
        if template {
            headings.insert(
                name.clone(),
                sheet[..=header_index]
                    .iter()
                    .flat_map(|row| row.iter())
                    .filter_map(|cell| match cell {
                        Data::String(text) if !text.trim().is_empty() => {
                            Some(text.trim().to_owned())
                        }
                        _ => None,
                    })
                    .collect(),
            );
        }
        let header = sheet[header_index];
        let dates: BTreeMap<usize, NaiveDate> = header
            .iter()
            .enumerate()
            .filter_map(|(index, cell)| {
                let parsed = match cell {
                    Data::DateTime(_) => cell.as_datetime().map(|v| v.date()),
                    Data::String(s) => date(s),
                    _ => None,
                };
                parsed.map(|date| (index, date))
            })
            .collect();
        let label_index = header.iter().position(|cell| {
            matches!(
                cell.to_string().trim().to_lowercase().as_str(),
                "date" | "row_label"
            )
        });
        let event_row = if template {
            label_index.and_then(|index| {
                sheet[header_index + 1..].iter().find(|row| {
                    row.get(index).is_some_and(|v| {
                        matches!(
                            v.to_string().trim().to_lowercase().as_str(),
                            "phase" | "event" | "type"
                        )
                    })
                })
            })
        } else {
            None
        };
        let event_columns: Vec<usize> = dates
            .keys()
            .copied()
            .filter(|index| {
                event_row.and_then(|row| row.get(*index)).is_some_and(|v| {
                    matches!(
                        v.to_string().trim().to_lowercase().as_str(),
                        "meet" | "competition" | "comp" | "event"
                    )
                })
            })
            .collect();
        let first_date = dates.values().min().copied();
        let headers: Vec<String> = header
            .iter()
            .enumerate()
            .map(|(index, cell)| {
                if let (Some(day), Some(first)) = (dates.get(&index), first_date) {
                    if !event_columns.contains(&index) {
                        return format!(
                            "week_{}",
                            day.signed_duration_since(first).num_days() / 7 + 1
                        );
                    }
                }
                if template && cell.to_string().trim().eq_ignore_ascii_case("date") {
                    return "row_label".into();
                }
                if matches!(cell, Data::Empty) {
                    format!("col_{index}")
                } else {
                    cell.to_string().trim().to_owned()
                }
            })
            .collect();
        let mut last_day = Value::Null;
        for cells in &sheet[header_index + 1..] {
            let mut row = Map::new();
            row.insert(
                "_sheet".into(),
                json!(
                    week.map(|w| format!("Week {w}"))
                        .unwrap_or_else(|| name.clone())
                ),
            );
            if let Some(week) = week {
                row.insert("week_number".into(), json!(week));
            }
            let mut has_data = false;
            for (index, cell) in cells.iter().enumerate().take(headers.len()) {
                if event_columns.contains(&index) {
                    continue;
                }
                let cell = value(cell);
                if template
                    && headers[index].to_lowercase().contains("date")
                    && cell.as_str().and_then(date).is_some()
                {
                    continue;
                }
                has_data |= !cell.is_null();
                row.insert(headers[index].clone(), cell);
            }
            if template && row.contains_key("day") {
                let day = &row["day"];
                if !day.is_null() && day != "" {
                    last_day = day.clone();
                }
                row.insert("day".into(), last_day.clone());
            }
            if has_data {
                rows.push(Value::Object(row));
            }
        }
    }
    Ok((rows, headings))
}

fn normalize_dates(rows: &mut [Value]) {
    let date_key = |key: &str| {
        let key = key.to_lowercase();
        key.contains("date")
            && !["meet", "competition", "comp", "event"]
                .iter()
                .any(|s| key.contains(s))
    };
    let first = rows
        .iter()
        .filter_map(Value::as_object)
        .flat_map(|row| row.iter())
        .filter(|(key, _)| date_key(key))
        .filter_map(|(_, v)| v.as_str().and_then(date))
        .min();
    let date_pattern =
        Regex::new(r"\b\d{4}-\d{2}-\d{2}(?:[T ][0-9:.+Z-]+)?\b").expect("valid pattern");
    for row in rows.iter_mut().filter_map(Value::as_object_mut) {
        let original = std::mem::take(row);
        for (key, mut v) in original {
            if date_key(&key) {
                if let (Some(day), Some(first)) = (v.as_str().and_then(date), first) {
                    row.insert(
                        "_relative_week".into(),
                        json!(day.signed_duration_since(first).num_days() / 7 + 1),
                    );
                    row.insert("_day_of_week".into(), json!(day.format("%A").to_string()));
                } else if key.eq_ignore_ascii_case("date") {
                    row.insert("row_label".into(), v);
                }
                continue;
            }
            let normalized = key.to_lowercase().replace(['_', '-'], " ");
            if ["meet date", "competition date", "comp date", "event date"]
                .iter()
                .any(|s| normalized.contains(s))
                || v.as_str().and_then(date).is_some()
            {
                continue;
            }
            if let Some(s) = v.as_str() {
                v = json!(date_pattern.replace_all(s, "").to_string());
            }
            row.insert(key, v);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn csv_extracts_and_removes_calendar_dates_from_templates() {
        let source = STANDARD.encode(
            b"date,exercise,notes\n2026-09-01,Squat,Keep knees out\n2026-09-09,Bench,Brace\n",
        );
        let result = extract(&source, "test.csv", true).unwrap();
        assert_eq!(result.rows[0]["_relative_week"], 1);
        assert_eq!(result.rows[1]["_relative_week"], 2);
        assert_eq!(result.rows[0]["exercise"], "Squat");
        assert!(!result.rows[0].as_object().unwrap().contains_key("date"));
        assert!(result.file_hash.starts_with("sha256:"));
        assert_eq!(result.file_hash.len(), 23);
    }

    #[test]
    fn rejects_invalid_base64_and_workbooks() {
        assert!(extract("!", "test.csv", false).is_err());
        assert!(extract(&STANDARD.encode(b"not a workbook"), "test.xlsx", true).is_err());
    }

    #[test]
    fn extracts_workbook_title_week_and_carried_day() {
        let workbook = include_str!("week_test_data.txt");
        let result = extract(workbook, "program.xlsx", true).unwrap();
        assert!(result.headings["Week 1"].contains(&"Meet Prep".to_string()));
        assert_eq!(result.rows.len(), 2);
        assert_eq!(result.rows[0]["week_number"], 1);
        assert_eq!(result.rows[0]["exercise"], "Squat");
        assert_eq!(result.rows[1]["exercise"], "Bench");
        assert_eq!(result.rows[1]["day"], "Monday");
    }
}
