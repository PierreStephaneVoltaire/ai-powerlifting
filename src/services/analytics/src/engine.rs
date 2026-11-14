use std::sync::Arc;

use chrono::NaiveDate;
use serde::Serialize;
use serde_json::Value;

use crate::ai::Ai;
use crate::assemble::{self, Loaded, Scope};
use crate::cache::Cache;
use crate::calc::Env;
use crate::error::Error;
use crate::snapshots::Snapshots;
use crate::source::{Source, Window};

#[derive(Clone, Copy, Debug)]
pub enum Clock {
    System,
    Fixed(NaiveDate),
}

impl Clock {
    pub fn today(self) -> NaiveDate {
        match self {
            Self::System => chrono::Utc::now().date_naive(),
            Self::Fixed(date) => date,
        }
    }
}

#[derive(Clone)]
pub struct Engine {
    pub source: Arc<dyn Source>,
    pub cache: Cache,
    pub clock: Clock,
    pub ai: Ai,
    pub snapshots: Option<Arc<dyn Snapshots>>,
}

pub fn to_value<T: Serialize>(value: &T) -> Result<Value, Error> {
    serde_json::to_value(value).map_err(|error| Error::Internal(error.to_string()))
}

impl Engine {
    pub fn new(source: Arc<dyn Source>, cache: Cache, clock: Clock) -> Self {
        Self {
            source,
            cache,
            clock,
            ai: Ai::disabled(),
            snapshots: None,
        }
    }

    pub fn with_ai(mut self, ai: Ai) -> Self {
        self.ai = ai;
        self
    }

    pub fn with_snapshots(mut self, snapshots: Arc<dyn Snapshots>) -> Self {
        self.snapshots = Some(snapshots);
        self
    }

    pub async fn load(
        &self,
        athlete: &str,
        window: &Window,
        scope: Scope<'_>,
    ) -> Result<Loaded, Error> {
        let raw = self.source.load(athlete, window).await?;
        assemble::build(raw, scope)
    }

    pub fn env<'a>(&self, loaded: &'a Loaded) -> Env<'a> {
        Env {
            today: self.clock.today(),
            glossary: &loaded.glossary,
        }
    }
}
