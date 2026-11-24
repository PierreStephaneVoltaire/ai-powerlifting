use serde_json::{Value, json};

fn number(value: Option<&Value>) -> i64 {
    value
        .and_then(|value| {
            value
                .as_i64()
                .or_else(|| value.as_f64().map(|number| number as i64))
                .or_else(|| value.as_str().and_then(|s| s.parse().ok()))
        })
        .unwrap_or(0)
}

pub fn list(mut items: Vec<Value>, limit: usize) -> Value {
    items.sort_by(|a, b| {
        b["sk"]
            .as_str()
            .unwrap_or("")
            .cmp(a["sk"].as_str().unwrap_or(""))
    });
    let total = items.len();
    let imports: Vec<Value> = items
        .into_iter()
        .take(limit.clamp(1, 500))
        .map(|item| {
            let field = |name: &str, fallback: &str| {
                item.get(name)
                    .or_else(|| item.get(fallback))
                    .cloned()
                    .unwrap_or_else(|| json!(""))
            };
            json!({
                "sk": item.get("sk"),
                "id": field("id", "import_id"),
                "filename": field("filename", "source_filename"),
                "source": field("source", "source"),
                "format": field("format", "import_type"),
                "status": field("status", "status"),
                "classification": field("classification", "classification"),
                "row_count": number(item.get("row_count")),
                "session_count": number(item.get("session_count")),
                "created_at": field("created_at", "uploaded_at"),
                "updated_at": field("updated_at", "updated_at")
            })
        })
        .collect();
    json!({"count": imports.len(), "total": total, "imports": imports})
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn summaries_are_sorted_limited_and_include_total() {
        let result = list(
            vec![
                json!({"sk":"import#a", "import_id":"a"}),
                json!({"sk":"import#b", "import_id":"b", "row_count":"3", "source_filename":"b.csv"}),
            ],
            1,
        );
        assert_eq!(result["total"], 2);
        assert_eq!(result["count"], 1);
        assert_eq!(result["imports"][0]["id"], "b");
        assert_eq!(result["imports"][0]["filename"], "b.csv");
        assert_eq!(result["imports"][0]["row_count"], 3);
    }
}
