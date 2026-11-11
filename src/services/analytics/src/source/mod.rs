use std::future::Future;
use std::pin::Pin;

use serde_json::Value;

use crate::error::Error;

pub mod dynamo;
pub mod fixture;

pub const SESSION_PREFIX: &str = "session#";
pub const UPPER_BOUND: char = '\u{10ffff}';

#[derive(Debug, Default, Clone, PartialEq, Eq)]
pub struct Window {
    pub start: Option<String>,
    pub end: Option<String>,
}

impl Window {
    pub fn is_open(&self) -> bool {
        self.start.is_none() && self.end.is_none()
    }

    pub fn session_bounds(&self, program_sk: &str) -> (String, String) {
        let prefix = format!("{SESSION_PREFIX}{program_sk}#");
        let upper = self
            .end
            .as_deref()
            .map_or_else(|| UPPER_BOUND.to_string(), str::to_owned);
        (
            format!("{prefix}{}", self.start.as_deref().unwrap_or_default()),
            format!("{prefix}{upper}{UPPER_BOUND}"),
        )
    }

    pub fn holds_entry(&self, entry_date: &str) -> bool {
        self.start
            .as_deref()
            .is_none_or(|start| entry_date >= start)
            && self.end.as_deref().is_none_or(|end| entry_date <= end)
    }
}

#[derive(Debug, Default)]
pub struct RawData {
    pub pointer: Value,
    pub program: Value,
    pub program_sk: String,
    pub sessions: Vec<Value>,
    pub weight_log: Value,
    pub glossary: Value,
    pub competitions: Vec<Value>,
    pub goals: Vec<Value>,
}

pub type Loading<'a> = Pin<Box<dyn Future<Output = Result<RawData, Error>> + Send + 'a>>;

pub type Fetching<'a> = Pin<Box<dyn Future<Output = Result<Value, Error>> + Send + 'a>>;

pub trait Source: Send + Sync {
    fn load<'a>(&'a self, athlete: &'a str, window: &'a Window) -> Loading<'a>;
    fn glossary<'a>(&'a self, athlete: &'a str) -> Fetching<'a>;
}
