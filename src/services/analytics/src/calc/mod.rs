use chrono::NaiveDate;
use serde::Serialize;

use crate::model::{Glossary, Lift, Session};

pub mod acwr;
pub mod alerts;
pub mod banister;
pub mod compliance;
pub mod deload;
pub mod e1rm;
pub mod fatigue;
pub mod inol;
pub mod intensity;
pub mod landmarks;
pub mod peaking;
pub mod progression;
pub mod projection;
pub mod readiness;
pub mod scoring;
pub mod weeks;

pub type Sessions<'a> = &'a [&'a Session];

#[derive(Clone, Copy)]
pub struct Env<'a> {
    pub today: NaiveDate,
    pub glossary: &'a Glossary,
}

#[derive(Debug, Clone, Serialize)]
pub struct Insufficient {
    pub status: &'static str,
    pub reason: String,
}

impl Insufficient {
    pub fn new(reason: impl Into<String>) -> Self {
        Self {
            status: "insufficient_data",
            reason: reason.into(),
        }
    }
}

#[derive(Debug, Clone, Serialize)]
#[serde(untagged)]
pub enum Computed<T> {
    Ready(T),
    Insufficient(Insufficient),
}

impl<T> Computed<T> {
    pub fn insufficient(reason: impl Into<String>) -> Self {
        Self::Insufficient(Insufficient::new(reason))
    }

    pub fn ready(&self) -> Option<&T> {
        match self {
            Self::Ready(value) => Some(value),
            Self::Insufficient(_) => None,
        }
    }

    pub fn into_ready(self) -> Option<T> {
        match self {
            Self::Ready(value) => Some(value),
            Self::Insufficient(_) => None,
        }
    }
}

#[derive(Debug, Clone, Copy, Default, Serialize, PartialEq)]
pub struct Dims {
    pub axial: f64,
    pub neural: f64,
    pub peripheral: f64,
    pub systemic: f64,
}

pub const DIMENSION_WEIGHTS: Dims = Dims {
    axial: 0.30,
    neural: 0.30,
    peripheral: 0.25,
    systemic: 0.15,
};

impl Dims {
    pub fn each(self) -> [f64; 4] {
        [self.axial, self.neural, self.peripheral, self.systemic]
    }

    pub fn from_each(values: [f64; 4]) -> Self {
        Self {
            axial: values[0],
            neural: values[1],
            peripheral: values[2],
            systemic: values[3],
        }
    }

    pub fn map(self, f: impl Fn(f64) -> f64) -> Self {
        Self::from_each(self.each().map(f))
    }

    pub fn add(&mut self, other: Self, scale: f64) {
        self.axial += other.axial * scale;
        self.neural += other.neural * scale;
        self.peripheral += other.peripheral * scale;
        self.systemic += other.systemic * scale;
    }

    pub fn weighted(self) -> f64 {
        self.axial * DIMENSION_WEIGHTS.axial
            + self.neural * DIMENSION_WEIGHTS.neural
            + self.peripheral * DIMENSION_WEIGHTS.peripheral
            + self.systemic * DIMENSION_WEIGHTS.systemic
    }

    pub fn max(self) -> f64 {
        self.each().into_iter().fold(f64::MIN, f64::max)
    }
}

pub const PRIMARY_LIFTS: [&str; 2] = ["squat", "deadlift"];

pub fn is_primary(key: &str) -> bool {
    PRIMARY_LIFTS.contains(&key)
}

#[derive(Debug, Clone)]
pub struct ByLift<T>(pub Vec<(Lift, T)>);

impl<T> ByLift<T> {
    pub fn new() -> Self {
        Self(Vec::new())
    }

    pub fn get(&self, lift: Lift) -> Option<&T> {
        self.0
            .iter()
            .find(|(key, _)| *key == lift)
            .map(|(_, value)| value)
    }

    pub fn entry(&mut self, lift: Lift, make: impl FnOnce() -> T) -> &mut T {
        let index = match self.0.iter().position(|(key, _)| *key == lift) {
            Some(index) => index,
            None => {
                self.0.push((lift, make()));
                self.0.len() - 1
            }
        };
        &mut self.0[index].1
    }

    pub fn is_empty(&self) -> bool {
        self.0.is_empty()
    }
}

impl<T> Default for ByLift<T> {
    fn default() -> Self {
        Self::new()
    }
}

impl<T: Serialize> Serialize for ByLift<T> {
    fn serialize<S: serde::Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        use serde::ser::SerializeMap;
        let mut map = serializer.serialize_map(Some(self.0.len()))?;
        for (lift, value) in &self.0 {
            map.serialize_entry(lift.key(), value)?;
        }
        map.end()
    }
}
