use axum::Json;
use axum::http::StatusCode;
use axum::response::{IntoResponse, Response};
use serde_json::{Value, json};
use thiserror::Error;

#[derive(Debug, Error)]
pub enum Error {
    #[error("Unknown operation")]
    UnknownOperation,
    #[error("Generation requires an active native turn")]
    GenerationWithoutTurn,
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
    Internal(String),
}

impl Error {
    pub fn status(&self) -> StatusCode {
        match self {
            Self::UnknownOperation => StatusCode::NOT_FOUND,
            Self::GenerationWithoutTurn | Self::Forbidden(_) => StatusCode::FORBIDDEN,
            Self::AccessDenied(status) => *status,
            Self::AccessUnavailable => StatusCode::SERVICE_UNAVAILABLE,
            Self::NestedWithoutExecution => StatusCode::CONFLICT,
            Self::Validation(_) | Self::Body => StatusCode::UNPROCESSABLE_ENTITY,
            Self::InvalidResult | Self::Internal(_) => StatusCode::INTERNAL_SERVER_ERROR,
        }
    }

    pub fn detail(&self) -> Value {
        let message = self.to_string();
        match self {
            Self::UnknownOperation | Self::GenerationWithoutTurn => Value::String(message),
            Self::Body => json!([{"type": "dict_type", "loc": ["body"], "msg": message}]),
            _ => json!({"code": self.code(), "message": message}),
        }
    }

    fn code(&self) -> &'static str {
        match self {
            Self::Forbidden(_) | Self::AccessDenied(_) => "forbidden",
            Self::AccessUnavailable => "access_unavailable",
            Self::NestedWithoutExecution => "uncertain",
            Self::Validation(_) => "validation",
            Self::InvalidResult => "invalid_result",
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

impl From<polars::prelude::PolarsError> for Error {
    fn from(error: polars::prelude::PolarsError) -> Self {
        Self::Internal(error.to_string())
    }
}
