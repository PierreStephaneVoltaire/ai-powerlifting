use std::time::Duration;

use axum::http::StatusCode;
use serde_json::{Map, Value, json};

use crate::caller::Caller;
use crate::error::Error;

const TIMEOUT: Duration = Duration::from_secs(10);

pub async fn fetch(
    http: &reqwest::Client,
    profile_url: &str,
    operation: &str,
    arguments: &Map<String, Value>,
    caller: &Caller,
) -> Result<Value, Error> {
    let response = http
        .post(format!("{profile_url}/operations/access_context"))
        .timeout(TIMEOUT)
        .header("X-Person-Pk", &caller.person)
        .header("X-Athlete-Pk", &caller.athlete)
        .json(&json!({"operation": operation, "arguments": arguments}))
        .send()
        .await
        .map_err(|_| Error::AccessUnavailable)?;
    if response.status() != StatusCode::OK {
        return Err(Error::AccessDenied(response.status()));
    }
    response.json().await.map_err(|_| Error::AccessUnavailable)
}
