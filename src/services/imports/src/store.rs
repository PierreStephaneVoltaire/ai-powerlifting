use std::collections::HashMap;

use aws_sdk_dynamodb::{
    Client,
    types::{AttributeValue, ReturnValue},
};
use chrono::{DateTime, Duration, Utc};
use serde_json::Value;

type Result<T> = std::result::Result<T, Box<dyn std::error::Error + Send + Sync>>;

pub struct ImportStore {
    client: Client,
    table: String,
    pk: String,
}

fn string(value: impl Into<String>) -> AttributeValue {
    AttributeValue::S(value.into())
}

impl ImportStore {
    pub fn new(client: Client, table: String, pk: String) -> Self {
        Self { client, table, pk }
    }

    pub async fn get(&self, id: &str) -> Result<Option<Value>> {
        let output = self
            .client
            .get_item()
            .table_name(&self.table)
            .key("pk", string(&self.pk))
            .key("sk", string(format!("import#pending#{id}")))
            .send()
            .await?;
        output
            .item
            .map(serde_dynamo::from_item)
            .transpose()
            .map_err(Into::into)
    }

    pub async fn list(&self, prefix: &str) -> Result<Vec<Value>> {
        let mut items = Vec::new();
        let mut cursor = None;
        loop {
            let output = self
                .client
                .query()
                .table_name(&self.table)
                .key_condition_expression("pk = :pk AND begins_with(sk, :prefix)")
                .expression_attribute_values(":pk", string(&self.pk))
                .expression_attribute_values(":prefix", string(prefix))
                .set_exclusive_start_key(cursor)
                .send()
                .await?;
            for item in output.items.unwrap_or_default() {
                items.push(serde_dynamo::from_item(item)?);
            }
            cursor = output.last_evaluated_key.filter(|key| !key.is_empty());
            if cursor.is_none() {
                break;
            }
        }
        Ok(items)
    }

    pub async fn put(&self, item: Value) -> Result<()> {
        let item: HashMap<String, AttributeValue> = serde_dynamo::to_item(item)?;
        self.client
            .put_item()
            .table_name(&self.table)
            .set_item(Some(item))
            .send()
            .await?;
        Ok(())
    }

    pub async fn stage(&self, record: Value, now: DateTime<Utc>) -> Result<String> {
        let import_type = record
            .get("import_type")
            .and_then(Value::as_str)
            .filter(|value| !value.is_empty())
            .ok_or("import_type is required")?;
        if self
            .list("import#pending#")
            .await?
            .iter()
            .any(|item| item["import_type"] == import_type && item["status"] == "awaiting_review")
        {
            return Err(format!("An import of type '{import_type}' is already awaiting review. Apply or reject it first.").into());
        }
        let id = uuid::Uuid::new_v4().to_string();
        let expires = now + Duration::days(7);
        let mut item = record
            .as_object()
            .ok_or("import record must be an object")?
            .clone();
        item.insert("pk".into(), self.pk.clone().into());
        item.insert("sk".into(), format!("import#pending#{id}").into());
        item.insert("import_id".into(), id.clone().into());
        item.insert("status".into(), "awaiting_review".into());
        item.insert("uploaded_at".into(), now.to_rfc3339().into());
        item.insert("expires_at".into(), expires.to_rfc3339().into());
        item.insert("ttl".into(), expires.timestamp().into());
        self.put(Value::Object(item)).await?;
        Ok(id)
    }

    pub async fn reject(&self, id: &str, at: &str, reason: Option<&str>) -> Result<()> {
        let expression = if reason.filter(|reason| !reason.is_empty()).is_some() {
            "SET #status = :status, rejected_at = :at, rejection_reason = :reason"
        } else {
            "SET #status = :status, rejected_at = :at"
        };
        let mut update = self
            .client
            .update_item()
            .table_name(&self.table)
            .key("pk", string(&self.pk))
            .key("sk", string(format!("import#pending#{id}")))
            .update_expression(expression)
            .condition_expression("#status = :awaiting")
            .expression_attribute_names("#status", "status")
            .expression_attribute_values(":status", string("rejected"))
            .expression_attribute_values(":awaiting", string("awaiting_review"))
            .expression_attribute_values(":at", string(at));
        if let Some(reason) = reason.filter(|reason| !reason.is_empty()) {
            update = update.expression_attribute_values(":reason", string(reason));
        }
        update.send().await?;
        Ok(())
    }

    pub async fn claim(&self, id: &str, claim: &str, at: &str) -> Result<Value> {
        let output = self
            .client
            .update_item()
            .table_name(&self.table)
            .key("pk", string(&self.pk))
            .key("sk", string(format!("import#pending#{id}")))
            .update_expression(
                "SET #status = :applying, applying_at = :at, apply_claim_id = :claim",
            )
            .condition_expression("#status = :awaiting")
            .expression_attribute_names("#status", "status")
            .expression_attribute_values(":applying", string("applying"))
            .expression_attribute_values(":awaiting", string("awaiting_review"))
            .expression_attribute_values(":at", string(at))
            .expression_attribute_values(":claim", string(claim))
            .return_values(ReturnValue::AllNew)
            .send()
            .await?;
        let attributes = output.attributes.ok_or("claim returned no attributes")?;
        Ok(serde_dynamo::from_item(attributes)?)
    }

    pub async fn finish_claim(
        &self,
        id: &str,
        claim: &str,
        status: &str,
        at: &str,
        reason: Option<&str>,
    ) -> Result<()> {
        if !matches!(status, "applied" | "uncertain") {
            return Err("invalid claim status".into());
        }
        let time_field = if status == "applied" {
            "applied_at"
        } else {
            "uncertain_at"
        };
        let expression = if reason.is_some() {
            format!("SET #status = :status, {time_field} = :at, uncertainty_reason = :reason")
        } else {
            format!("SET #status = :status, {time_field} = :at")
        };
        let mut update = self
            .client
            .update_item()
            .table_name(&self.table)
            .key("pk", string(&self.pk))
            .key("sk", string(format!("import#pending#{id}")))
            .update_expression(expression)
            .condition_expression("#status = :applying AND apply_claim_id = :claim")
            .expression_attribute_names("#status", "status")
            .expression_attribute_values(":status", string(status))
            .expression_attribute_values(":applying", string("applying"))
            .expression_attribute_values(":at", string(at))
            .expression_attribute_values(":claim", string(claim));
        if let Some(reason) = reason {
            update = update.expression_attribute_values(
                ":reason",
                string(reason.chars().take(1000).collect::<String>()),
            );
        }
        update.send().await?;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::{Json, Router, extract::State, http::StatusCode, routing::post};
    use serde_json::json;
    use std::sync::Arc;
    use tokio::sync::Mutex;

    #[tokio::test]
    async fn rejection_only_changes_imports_awaiting_review() {
        async fn update(
            State(status): State<Arc<Mutex<Option<String>>>>,
            body: axum::body::Bytes,
        ) -> (StatusCode, Json<Value>) {
            let request: Value = serde_json::from_slice(&body).unwrap();
            assert_eq!(request["ConditionExpression"], "#status = :awaiting");
            assert_eq!(
                request["ExpressionAttributeValues"][":awaiting"]["S"],
                "awaiting_review"
            );
            let mut status = status.lock().await;
            if status.as_deref() != Some("awaiting_review") {
                return (
                    StatusCode::BAD_REQUEST,
                    Json(json!({"__type":"ConditionalCheckFailedException"})),
                );
            }
            *status = Some("rejected".into());
            (StatusCode::OK, Json(json!({})))
        }

        let status = Arc::new(Mutex::new(Some("awaiting_review".to_owned())));
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let url = format!("http://{}", listener.local_addr().unwrap());
        let app = Router::new()
            .route("/", post(update))
            .with_state(status.clone());
        let task = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
        let config = aws_config::defaults(aws_config::BehaviorVersion::latest())
            .region(aws_config::Region::new("ca-central-1"))
            .endpoint_url(url)
            .credentials_provider(aws_sdk_dynamodb::config::Credentials::new(
                "test", "test", None, None, "test",
            ))
            .load()
            .await;
        let store = ImportStore::new(Client::new(&config), "test".into(), "athlete".into());
        store.reject("id", "now", None).await.unwrap();
        assert_eq!(status.lock().await.as_deref(), Some("rejected"));
        *status.lock().await = Some("applying".into());
        assert!(store.reject("id", "now", None).await.is_err());
        assert_eq!(status.lock().await.as_deref(), Some("applying"));
        *status.lock().await = None;
        assert!(store.reject("missing", "now", None).await.is_err());
        assert!(status.lock().await.is_none());
        task.abort();
    }
}
