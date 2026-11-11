use axum::Json;
use axum::http::StatusCode;
use axum::response::{IntoResponse, Response};
use serde_json::{Value, json};
use thiserror::Error;

#[derive(Debug, Error)]
pub enum Error {
    #[error("Invalid internal token")]
    InvalidToken,
    #[error("Unknown operation")]
    UnknownOperation,
    #[error("Generation requires an active native turn")]
    GenerationWithoutTurn,
    #[error("Verified acting Person required")]
    InvalidPrincipal,
    #[error("{0}")]
    Forbidden(&'static str),
    #[error("Access evaluation denied")]
    AccessDenied(StatusCode),
    #[error("Permission service unavailable")]
    AccessUnavailable,
    #[error("Nested operation requires an active domain execution")]
    NestedWithoutExecution,
    #[error("{0}")]
    Validation(String),
    #[error("Request body must be a JSON object")]
    Body,
    #[error("Domain returned an invalid result")]
    InvalidResult,
    #[error("{0}")]
    NotFound(String),
    #[error("{0}")]
    CacheMiss(String),
    #[error("{0}")]
    NotImplemented(&'static str),
    #[error("{0}")]
    Internal(String),
}

impl Error {
    pub fn status(&self) -> StatusCode {
        match self {
            Self::InvalidToken | Self::InvalidPrincipal => StatusCode::UNAUTHORIZED,
            Self::UnknownOperation | Self::NotFound(_) | Self::CacheMiss(_) => StatusCode::NOT_FOUND,
            Self::GenerationWithoutTurn | Self::Forbidden(_) => StatusCode::FORBIDDEN,
            Self::AccessDenied(status) => *status,
            Self::AccessUnavailable => StatusCode::SERVICE_UNAVAILABLE,
            Self::NestedWithoutExecution => StatusCode::CONFLICT,
            Self::Validation(_) | Self::Body => StatusCode::UNPROCESSABLE_ENTITY,
            Self::NotImplemented(_) => StatusCode::NOT_IMPLEMENTED,
            Self::InvalidResult | Self::Internal(_) => StatusCode::INTERNAL_SERVER_ERROR,
        }
    }

    pub fn detail(&self) -> Value {
        let message = self.to_string();
        match self {
            Self::InvalidToken | Self::UnknownOperation | Self::GenerationWithoutTurn => {
                Value::String(message)
            }
            Self::Body => json!([{"type": "dict_type", "loc": ["body"], "msg": message}]),
            _ => json!({"code": self.code(), "message": message}),
        }
    }

    fn code(&self) -> &'static str {
        match self {
            Self::InvalidPrincipal => "invalid_principal",
            Self::Forbidden(_) | Self::AccessDenied(_) => "forbidden",
            Self::AccessUnavailable => "access_unavailable",
            Self::NestedWithoutExecution => "uncertain",
            Self::Validation(_) => "validation",
            Self::InvalidResult => "invalid_result",
            Self::NotFound(_) => "not_found",
            Self::CacheMiss(_) => "cache_miss",
            Self::NotImplemented(_) => "not_implemented",
            _ => "internal",
        }
    }
}

impl IntoResponse for Error {
    fn into_response(self) -> Response {
        if self.status().is_server_error() {
            tracing::error!(error = %self, "request failed");
        }
        (self.status(), Json(json!({"detail": self.detail()}))).into_response()
    }
}
