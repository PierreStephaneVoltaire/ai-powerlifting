use std::collections::BTreeMap;
use std::sync::LazyLock;

use serde::{Deserialize, Serialize};
use serde_json::Value;

use super::{Env, Sessions};
use crate::util::round;

const LANDMARKS_JSON: &str = include_str!("../../data/muscle_landmarks.json");

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct Landmark {
    pub mv: f64,
    pub mev: f64,
    pub mav_low: f64,
    pub mav_high: f64,
    pub mrv: f64,
    pub basis: String,
}

#[derive(Debug, Deserialize)]
struct LandmarkFile {
    sources: Vec<Value>,
    muscles: BTreeMap<String, Landmark>,
}

static LANDMARKS: LazyLock<LandmarkFile> =
    LazyLock::new(|| serde_json::from_str(LANDMARKS_JSON).expect("muscle_landmarks.json is valid"));

#[derive(Debug, Serialize)]
pub struct MuscleEntry {
    pub weekly_sets: f64,
    pub total_sets: f64,
    pub landmarks: Option<Landmark>,
    pub status: &'static str,
}

#[derive(Debug, Serialize)]
pub struct MuscleVolume {
    pub weeks: i64,
    pub muscles: BTreeMap<String, MuscleEntry>,
    pub sources: Vec<Value>,
}

fn status(weekly: f64, landmark: Option<&Landmark>) -> &'static str {
    match landmark {
        None => "unrated",
        Some(landmark) if weekly < landmark.mev => "below_mev",
        Some(landmark) if weekly <= landmark.mav_high => "productive",
        Some(landmark) if weekly <= landmark.mrv => "near_mrv",
        Some(_) => "above_mrv",
    }
}

pub fn compute(env: Env<'_>, sessions: Sessions<'_>, weeks: i64) -> MuscleVolume {
    let weeks = weeks.max(1);
    let mut totals: BTreeMap<String, f64> = LANDMARKS
        .muscles
        .keys()
        .map(|muscle| (muscle.clone(), 0.0))
        .collect();
    for exercise in sessions.iter().flat_map(|session| &session.exercises) {
        let sets = exercise.executed_sets();
        let Some(entry) = env.glossary.entry(&exercise.key).filter(|_| sets > 0.0) else {
            continue;
        };
        for (muscles, weight) in [
            (&entry.primary_muscles, 1.0),
            (&entry.secondary_muscles, 0.5),
            (&entry.tertiary_muscles, 0.25),
        ] {
            for muscle in muscles {
                *totals.entry(muscle.clone()).or_insert(0.0) += sets * weight;
            }
        }
    }
    let muscles = totals
        .into_iter()
        .map(|(muscle, total)| {
            let weekly = total / weeks as f64;
            let landmarks = LANDMARKS.muscles.get(&muscle).cloned();
            let state = status(weekly, landmarks.as_ref());
            (
                muscle,
                MuscleEntry {
                    weekly_sets: round(weekly, 1),
                    total_sets: round(total, 2),
                    landmarks,
                    status: state,
                },
            )
        })
        .collect();
    MuscleVolume {
        weeks,
        muscles,
        sources: LANDMARKS.sources.clone(),
    }
}
