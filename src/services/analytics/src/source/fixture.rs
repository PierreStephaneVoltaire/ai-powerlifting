use std::path::{Path, PathBuf};

use serde_json::Value;

use super::{Fetching, Loading, RawData, Source, Window};
use crate::error::Error;

pub struct FixtureSource {
    dir: PathBuf,
}

impl FixtureSource {
    pub fn new(dir: impl Into<PathBuf>) -> Self {
        Self { dir: dir.into() }
    }

    pub fn available(dir: &Path) -> bool {
        dir.join("program.json").is_file() && dir.join("sessions.json").is_file()
    }

    fn read(&self, name: &str) -> Result<Value, Error> {
        let path = self.dir.join(name);
        match std::fs::read(&path) {
            Ok(bytes) => serde_json::from_slice(&bytes)
                .map_err(|error| Error::Internal(format!("{}: {error}", path.display()))),
            Err(_) => Ok(Value::Null),
        }
    }

    fn list(&self, name: &str) -> Result<Vec<Value>, Error> {
        Ok(match self.read(name)? {
            Value::Array(items) => items,
            _ => Vec::new(),
        })
    }

    fn load_blocking(&self, window: &Window) -> Result<RawData, Error> {
        let pointer = self.read("program_pointer.json")?;
        let program_sk = pointer
            .get("ref_sk")
            .and_then(Value::as_str)
            .ok_or_else(|| Error::NotFound("Program not found".to_owned()))?
            .to_owned();
        let (lower, upper) = window.session_bounds(&program_sk);
        let sessions = self
            .list("sessions.json")?
            .into_iter()
            .filter(|item| {
                item.get("sk")
                    .and_then(Value::as_str)
                    .is_some_and(|sk| sk >= lower.as_str() && sk <= upper.as_str())
            })
            .collect();
        let competitions = self
            .list("competitions.json")?
            .into_iter()
            .filter(|item| {
                window.is_open()
                    || item
                        .get("entry_date")
                        .and_then(Value::as_str)
                        .is_some_and(|date| window.holds_entry(date))
            })
            .collect();
        Ok(RawData {
            program: self.read("program.json")?,
            weight_log: self.read("weight_log.json")?,
            glossary: self.read("glossary.json")?,
            goals: self.list("goals.json")?,
            pointer,
            program_sk,
            sessions,
            competitions,
        })
    }
}

impl Source for FixtureSource {
    fn load<'a>(&'a self, _athlete: &'a str, window: &'a Window) -> Loading<'a> {
        Box::pin(async move { self.load_blocking(window) })
    }

    fn glossary<'a>(&'a self, _athlete: &'a str) -> Fetching<'a> {
        Box::pin(async move { self.read("glossary.json") })
    }
}
