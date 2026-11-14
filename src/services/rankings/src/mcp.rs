use std::sync::Arc;

use axum::Json;
use axum::extract::State;
use axum::http::{HeaderMap, StatusCode};
use axum::response::{IntoResponse, Response};
use serde::Deserialize;
use serde_json::{Map, Value, json};
use utoipa::ToSchema;

use crate::api::CallerHeaders;
use crate::caller::Caller;
use crate::error::Error;
use crate::operations::Service;
use crate::{config::DOMAIN, pyjson};

const PROTOCOL_VERSION: &str = "2025-03-26";

#[derive(Deserialize, ToSchema)]
pub struct RpcRequest {
    #[schema(value_type = Option<Object>)]
    id: Option<Value>,
    method: Option<String>,
    #[schema(value_type = Option<Object>)]
    params: Option<Value>,
}

#[utoipa::path(
    post,
    path = "/mcp",
    request_body = RpcRequest,
    responses((status = 200, description = "JSON-RPC response", body = Object)),
    params(CallerHeaders)
)]
pub async fn handle(
    State(service): State<Arc<Service>>,
    headers: HeaderMap,
    body: axum::body::Bytes,
) -> Result<Response, Error> {
    let request: RpcRequest = serde_json::from_slice(&body).map_err(|_| Error::Body)?;
    let Some(id) = request.id else {
        return Ok((StatusCode::ACCEPTED, Json(json!({}))).into_response());
    };
    let result = match request.method.as_deref() {
        Some("initialize") => initialize(),
        Some("ping") => json!({}),
        Some("tools/list") => list_tools(&service),
        Some("tools/call") => call_tool(&service, &headers, request.params).await,
        _ => {
            let error = json!({"code": -32601, "message": "Method not found"});
            return Ok(Json(json!({"jsonrpc": "2.0", "id": id, "error": error})).into_response());
        }
    };
    Ok(Json(json!({"jsonrpc": "2.0", "id": id, "result": result})).into_response())
}

fn initialize() -> Value {
    json!({
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": {"tools": {}},
        "serverInfo": {"name": format!("powerlifting-{DOMAIN}"), "version": "1.0.0"},
    })
}

fn list_tools(service: &Service) -> Value {
    let tools: Vec<Value> = service
        .registry
        .iter()
        .filter(|operation| !operation.internal_only)
        .map(|operation| {
            let mut tool = Map::new();
            tool.insert("name".to_owned(), json!(operation.name));
            tool.insert("description".to_owned(), json!(operation.description));
            tool.insert("inputSchema".to_owned(), operation.input_schema.clone());
            if operation.result_schema.get("type") == Some(&json!("object")) {
                tool.insert("outputSchema".to_owned(), operation.result_schema.clone());
            }
            Value::Object(tool)
        })
        .collect();
    json!({"tools": tools})
}

async fn call_tool(service: &Service, headers: &HeaderMap, params: Option<Value>) -> Value {
    let params = params.unwrap_or(Value::Null);
    let name = params
        .get("name")
        .and_then(Value::as_str)
        .unwrap_or_default();
    let outcome = match params.get("arguments") {
        None | Some(Value::Null) => Ok(Map::new()),
        Some(Value::Object(arguments)) => Ok(arguments.clone()),
        Some(_) => Err(Error::Body),
    };
    let result = match outcome {
        Ok(arguments) => {
            let caller = Caller::identity(headers);
            service.call(name, arguments, &caller).await
        }
        Err(error) => Err(error),
    };
    match result {
        Ok(value) => {
            let mut content = json!({
                "content": [{"type": "text", "text": pyjson::dumps(&value, false)}],
                "isError": false,
            });
            if value.is_object() {
                content["structuredContent"] = value;
            }
            content
        }
        Err(error) => {
            let payload = json!({"error": error.detail(), "status": error.status().as_u16()});
            json!({
                "content": [{"type": "text", "text": pyjson::dumps(&payload, false)}],
                "isError": true,
            })
        }
    }
}
