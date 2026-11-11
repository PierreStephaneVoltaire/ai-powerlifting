use axum::http::StatusCode;
use jsonwebtoken::{Algorithm, DecodingKey, Validation, decode};
use serde::Deserialize;
use serde_json::{Map, Value, json};
use subtle::ConstantTimeEq;

use crate::config::Config;
use crate::error::Error;
use crate::operations::{Caller, Operation, Ownership};

const ISSUERS: [&str; 2] = ["powerlifting-gateway", "if-native"];
const AUDIENCE: &str = "powerlifting-services";
const MAX_LIFETIME_SECONDS: i64 = 300;
const MIN_SECRET_LENGTH: usize = 32;

#[derive(Debug, Deserialize)]
pub struct Claims {
    pub sub: String,
    pub athlete: String,
    operation: String,
    iat: i64,
    exp: i64,
}

pub fn check_internal_token(expected: &str, given: &str) -> Result<(), Error> {
    let matches = !expected.is_empty() && bool::from(expected.as_bytes().ct_eq(given.as_bytes()));
    matches.then_some(()).ok_or(Error::InvalidToken)
}

fn now() -> i64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map_or(0, |elapsed| elapsed.as_secs() as i64)
}

pub fn verify_principal(secret: &str, operation: &str, caller: &Caller) -> Result<Claims, Error> {
    if secret.len() < MIN_SECRET_LENGTH {
        return Err(Error::InvalidPrincipal);
    }
    let mut validation = Validation::new(Algorithm::HS256);
    validation.leeway = 0;
    validation.set_audience(&[AUDIENCE]);
    validation.set_issuer(&ISSUERS);
    validation.set_required_spec_claims(&["exp", "iss", "aud", "sub"]);
    let claims = decode::<Claims>(
        &caller.principal,
        &DecodingKey::from_secret(secret.as_bytes()),
        &validation,
    )
    .map_err(|_| Error::InvalidPrincipal)?
    .claims;
    let scoped = (caller.person.is_empty() || caller.person == claims.sub)
        && (caller.athlete.is_empty() || caller.athlete == claims.athlete);
    let lifetime_ok = claims.exp - claims.iat <= MAX_LIFETIME_SECONDS && claims.iat <= now();
    if claims.operation != operation || !scoped || !lifetime_ok {
        return Err(Error::InvalidPrincipal);
    }
    Ok(claims)
}

pub async fn fetch_access(
    http: &reqwest::Client,
    config: &Config,
    operation: &str,
    arguments: &Map<String, Value>,
    caller: &Caller,
) -> Result<Value, Error> {
    let response = http
        .post(format!("{}/internal/access", config.profile_url))
        .timeout(std::time::Duration::from_secs(10))
        .header("X-Internal-Token", &config.internal_token)
        .header("X-PL-Principal", &caller.principal)
        .json(&json!({"operation": operation, "arguments": arguments}))
        .send()
        .await
        .map_err(|_| Error::AccessUnavailable)?;
    if response.status() != StatusCode::OK {
        return Err(Error::AccessDenied(response.status()));
    }
    response.json().await.map_err(|_| Error::AccessUnavailable)
}

fn truthy(value: &Value) -> bool {
    match value {
        Value::Null => false,
        Value::Bool(flag) => *flag,
        Value::Number(number) => number.as_f64() != Some(0.0),
        Value::String(text) => !text.is_empty(),
        Value::Array(items) => !items.is_empty(),
        Value::Object(map) => !map.is_empty(),
    }
}

fn conflicts(arguments: &Map<String, Value>, key: &str, expected: &str) -> bool {
    arguments
        .get(key)
        .is_some_and(|value| truthy(value) && value.as_str() != Some(expected))
}

pub fn scope(
    operation: &Operation,
    arguments: &Map<String, Value>,
    claims: &Claims,
    access: &Value,
) -> Result<Map<String, Value>, Error> {
    if operation.ownership != Ownership::Public && claims.athlete.is_empty() {
        return Err(Error::Forbidden("Athlete scope required"));
    }
    let mut scoped = arguments.clone();
    if conflicts(&scoped, "actor_pk", &claims.sub) {
        return Err(Error::Forbidden(
            "Acting Person differs from authenticated identity",
        ));
    }
    if scoped.contains_key("actor_pk") {
        scoped.insert("actor_pk".to_owned(), json!(claims.sub));
    }
    let settings_pk = access
        .get("settings_pk")
        .and_then(Value::as_str)
        .unwrap_or_default();
    if conflicts(&scoped, "viewer_username", settings_pk) {
        return Err(Error::Forbidden("Viewer differs from authenticated Person"));
    }
    if operation.has_input("viewer_username") {
        if settings_pk.is_empty() {
            scoped.remove("viewer_username");
        } else {
            scoped.insert("viewer_username".to_owned(), json!(settings_pk));
        }
    }
    for key in ["pk", "user_pk", "mapped_pk", "_user_pk"] {
        if conflicts(&scoped, key, &claims.athlete) {
            return Err(Error::Forbidden(
                "Operation ownership conflicts with authenticated scope",
            ));
        }
    }
    if operation.ownership != Ownership::Public {
        scoped.insert("pk".to_owned(), json!(claims.athlete));
    }
    Ok(scoped)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn internal_token_must_match_and_be_configured() {
        assert!(check_internal_token("secret", "secret").is_ok());
        assert!(check_internal_token("secret", "other").is_err());
        assert!(check_internal_token("", "").is_err());
    }

    #[test]
    fn truthiness_follows_python() {
        assert!(!truthy(&json!("")));
        assert!(!truthy(&json!(0)));
        assert!(truthy(&json!("x")));
        assert!(!truthy(&Value::Null));
    }
}
