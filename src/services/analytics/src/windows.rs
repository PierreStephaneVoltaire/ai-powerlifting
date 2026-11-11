use std::collections::BTreeMap;

use chrono::{Datelike, Duration, NaiveDate};
use serde::{Deserialize, Serialize};

use crate::error::Error;
use crate::model::{DEFAULT_BLOCK, ProgramData};
use crate::scope::BlockScope;
use crate::util::parse_date;

pub const CACHE_SCHEMA_VERSION: i64 = 5;
pub const SECTION_CACHE_SCHEMA_VERSION: i64 = 4;
pub const MANIFEST_SCHEMA_VERSION: i64 = 6;

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub enum WindowKey {
    Current,
    Previous1,
    Previous2,
    Previous4,
    Previous8,
    Block,
}

pub const ALL_WINDOWS: [WindowKey; 6] = [
    WindowKey::Current,
    WindowKey::Previous1,
    WindowKey::Previous2,
    WindowKey::Previous4,
    WindowKey::Previous8,
    WindowKey::Block,
];

enum Mode {
    Current,
    Back(i64),
    Block,
}

impl WindowKey {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Current => "current",
            Self::Previous1 => "previous_1",
            Self::Previous2 => "previous_2",
            Self::Previous4 => "previous_4",
            Self::Previous8 => "previous_8",
            Self::Block => "block",
        }
    }

    pub fn parse(value: &str) -> Self {
        ALL_WINDOWS
            .into_iter()
            .find(|key| key.as_str() == value)
            .unwrap_or(Self::Current)
    }

    fn label(self) -> &'static str {
        match self {
            Self::Current => "Current Week",
            Self::Previous1 => "Previous Week",
            Self::Previous2 => "Previous 2 Weeks",
            Self::Previous4 => "Previous 4 Weeks",
            Self::Previous8 => "Previous 8 Weeks",
            Self::Block => "Full Block",
        }
    }

    fn mode(self) -> Mode {
        match self {
            Self::Current => Mode::Current,
            Self::Previous1 => Mode::Back(1),
            Self::Previous2 => Mode::Back(2),
            Self::Previous4 => Mode::Back(4),
            Self::Previous8 => Mode::Back(8),
            Self::Block => Mode::Block,
        }
    }
}

impl Serialize for WindowKey {
    fn serialize<S: serde::Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        serializer.serialize_str(self.as_str())
    }
}

impl<'de> Deserialize<'de> for WindowKey {
    fn deserialize<D: serde::Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        let text = String::deserialize(deserializer)?;
        Ok(Self::parse(&text))
    }
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "camelCase")]
pub struct Window {
    pub key: WindowKey,
    pub label: String,
    pub start: String,
    pub end: String,
    pub week_start: i64,
    pub week_end: i64,
    pub weeks: i64,
    pub current_week: i64,
}

pub type Windows = BTreeMap<WindowKey, Window>;

fn week_start_index(name: &str) -> i64 {
    match name {
        "Sunday" => 0,
        "Tuesday" => 2,
        "Wednesday" => 3,
        "Thursday" => 4,
        "Friday" => 5,
        "Saturday" => 6,
        _ => 1,
    }
}

fn week_start_day(program: &ProgramData, scope: &BlockScope) -> i64 {
    let active = scope.active();
    let configured = program
        .meta
        .blocks
        .iter()
        .find(|block| block.id == active)
        .and_then(|block| block.week_start_day.as_deref());
    configured.map_or(1, week_start_index)
}

fn anchor(start: NaiveDate, week_start: i64) -> NaiveDate {
    let current = i64::from(start.weekday().num_days_from_sunday());
    start - Duration::days((current - week_start).rem_euclid(7))
}

fn week_start_date(start: NaiveDate, week: i64, week_start: i64) -> NaiveDate {
    anchor(start, week_start) + Duration::days((week.max(1) - 1) * 7)
}

fn training_week(day: NaiveDate, start: NaiveDate, week_start: i64) -> i64 {
    ((day - anchor(start, week_start)).num_days().div_euclid(7) + 1).max(1)
}

fn date_of(text: &str) -> Result<NaiveDate, Error> {
    parse_date(text).ok_or_else(|| Error::Validation(format!("Invalid date: {text}")))
}

pub fn build(program: &ProgramData, as_of: NaiveDate) -> Result<Windows, Error> {
    let scope = BlockScope::new(&program.meta);
    let in_current = |session: &&crate::model::Session| {
        let block = if session.block.is_empty() {
            DEFAULT_BLOCK
        } else {
            session.block.as_str()
        };
        block == DEFAULT_BLOCK
    };
    let active_block = program
        .meta
        .blocks
        .iter()
        .find(|block| block.status == "active");
    let first_session = program
        .sessions
        .iter()
        .filter(in_current)
        .find(|session| !session.date_text.is_empty())
        .map(|session| session.date_text.clone());
    let program_start = active_block
        .map(|block| block.start_date.clone())
        .filter(|text| !text.is_empty())
        .or_else(|| Some(program.meta.program_start()).filter(|text| !text.is_empty()))
        .or(first_session)
        .unwrap_or_else(|| as_of.to_string());
    let start_date = date_of(&program_start)?;
    let week_start = week_start_day(program, &scope);
    let calculated = training_week(as_of, start_date, week_start);
    let calculated_start = week_start_date(start_date, calculated, week_start);
    let calculated_end = calculated_start + Duration::days(6);
    let due: Vec<i64> = program
        .sessions
        .iter()
        .filter(in_current)
        .filter(|session| {
            session.date.is_some_and(|date| {
                date >= calculated_start && date <= calculated_end && date <= as_of
            })
        })
        .filter_map(|session| session.week_number)
        .collect();
    let current_week = due.into_iter().max().unwrap_or(calculated);

    let mut windows = Windows::new();
    for key in ALL_WINDOWS {
        let (first, last) = match key.mode() {
            Mode::Current => (current_week, current_week),
            Mode::Block => (1, current_week),
            Mode::Back(back) => ((current_week - back).max(1), current_week),
        };
        let mut labelled: Vec<NaiveDate> = program
            .sessions
            .iter()
            .filter(in_current)
            .filter(|session| session.date.is_some_and(|date| date <= as_of))
            .filter(|session| {
                session
                    .week_number
                    .is_some_and(|week| week >= first && week <= last)
            })
            .filter_map(|session| session.date)
            .collect();
        labelled.sort();
        let mut start = week_start_date(start_date, first, week_start);
        if let Some(earliest) = labelled.first().filter(|earliest| **earliest < start) {
            start = *earliest;
        }
        let mut end = week_start_date(start_date, last, week_start) + Duration::days(6);
        if let Some(latest) = labelled.last().filter(|latest| **latest > end) {
            end = *latest;
        }
        windows.insert(
            key,
            Window {
                key,
                label: key.label().to_owned(),
                start: start.max(start_date).to_string(),
                end: end.to_string(),
                week_start: first,
                week_end: last,
                weeks: (last - first + 1).max(1),
                current_week,
            },
        );
    }
    Ok(windows)
}

pub fn source_key(version: &str, start: Option<&str>, end: Option<&str>) -> String {
    format!(
        "s{SECTION_CACHE_SCHEMA_VERSION}-v{version}-{}-{}",
        start.unwrap_or_default(),
        end.unwrap_or_default()
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn unknown_window_keys_fall_back_to_current() {
        assert_eq!(WindowKey::parse("nonsense"), WindowKey::Current);
        assert_eq!(WindowKey::parse("previous_8"), WindowKey::Previous8);
    }

    #[test]
    fn week_anchor_follows_the_configured_start_day() {
        let wednesday = NaiveDate::from_ymd_opt(2026, 11, 11).expect("valid date");
        assert_eq!(anchor(wednesday, 0).to_string(), "2026-11-08");
        assert_eq!(anchor(wednesday, 1).to_string(), "2026-11-09");
    }
}
