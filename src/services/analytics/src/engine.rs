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
    pub build_id: Option<String>,
}

tokio::task_local! {
    pub static ATHLETE_SEX: Option<String>;
}

pub fn with_default_sex(program: &mut Value, sex: Option<String>) {
    let Some(sex) = sex else { return };
    let present = |pointer: &str| {
        program
            .pointer(pointer)
            .and_then(Value::as_str)
            .is_some_and(|text| !text.is_empty())
    };
    if present("/meta/sex") || present("/settings/sex") {
        return;
    }
    if program
        .get("settings")
        .is_none_or(|settings| !settings.is_object())
    {
        program["settings"] = Value::Object(Default::default());
    }
    program["settings"]["sex"] = Value::String(sex);
}

pub fn access_sex() -> Option<String> {
    ATHLETE_SEX.try_with(Clone::clone).ok().flatten()
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
            build_id: None,
        }
    }

    pub fn with_ai(mut self, ai: Ai) -> Self {
        self.ai = ai;
        self
    }

    pub fn with_build_id(mut self, build_id: Option<String>) -> Self {
        self.build_id = build_id;
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
        let mut raw = self.source.load(athlete, window).await?;
        with_default_sex(&mut raw.program, access_sex());
        assemble::build(raw, scope)
    }

    pub fn env<'a>(&self, loaded: &'a Loaded) -> Env<'a> {
        Env {
            today: self.clock.today(),
            glossary: &loaded.glossary,
        }
    }
}
