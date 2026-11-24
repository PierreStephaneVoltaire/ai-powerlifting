use chrono::Utc;
use serde_json::{Map, Value, json};

use crate::{store::ImportStore, summary};

pub async fn execute(
    store: &ImportStore,
    name: &str,
    args: &Map<String, Value>,
) -> Result<Option<Value>, String> {
    match name {
        "import_get_pending" => {
            let id = args
                .get("import_id")
                .and_then(Value::as_str)
                .filter(|s| !s.is_empty())
                .ok_or("import_id is required")?;
            Ok(Some(
                store
                    .get(id)
                    .await
                    .map_err(|error| error.to_string())?
                    .unwrap_or(Value::Null),
            ))
        }
        "import_list" => {
            let items = store
                .list("import#")
                .await
                .map_err(|error| error.to_string())?;
            let limit = args
                .get("limit")
                .and_then(Value::as_u64)
                .unwrap_or(100)
                .min(500) as usize;
            Ok(Some(summary::list(items, limit)))
        }
        "import_list_pending" => {
            let import_type = args.get("import_type").and_then(Value::as_str);
            let items: Vec<Value> = store
                .list("import#pending#")
                .await
                .map_err(|error| error.to_string())?
                .into_iter()
                .filter(|item| {
                    item["status"] == "awaiting_review"
                        && import_type.is_none_or(|kind| item["import_type"] == kind)
                })
                .collect();
            Ok(Some(json!(items)))
        }
        "import_reject" => {
            let id = args
                .get("import_id")
                .and_then(Value::as_str)
                .filter(|s| !s.is_empty())
                .ok_or("import_id is required")?;
            let reason = args.get("reason").and_then(Value::as_str);
            store
                .reject(id, &Utc::now().to_rfc3339(), reason)
                .await
                .map_err(|error| error.to_string())?;
            Ok(Some(json!({"status":"rejected", "import_id":id})))
        }
        _ => Ok(None),
    }
}
