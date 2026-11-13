use std::collections::BTreeMap;

use serde::Serialize;

use super::{Env, Sessions};
use crate::model::{Lift, NARROW_TRANSFER};
use crate::util::round;

#[derive(Debug, Serialize)]
pub struct Accessory {
    pub name: String,
    pub transfer: f64,
    pub sets: f64,
    pub weighted_sets: f64,
    pub volume: f64,
}

#[derive(Debug, Serialize)]
pub struct LiftBreakdown {
    pub sets: f64,
    pub raw_sets: f64,
    pub volume: f64,
    pub raw_volume: f64,
    pub frequency: f64,
    pub exposure_frequency: f64,
    pub accessories: Vec<Accessory>,
}

struct Tally {
    sets: f64,
    raw_sets: f64,
    volume: f64,
    raw_volume: f64,
    narrow_sessions: usize,
    exposure_sessions: usize,
    accessories: BTreeMap<String, Accessory>,
}

fn tally(env: Env<'_>, sessions: Sessions<'_>, lift: Lift) -> Tally {
    let mut tally = Tally {
        sets: 0.0,
        raw_sets: 0.0,
        volume: 0.0,
        raw_volume: 0.0,
        narrow_sessions: 0,
        exposure_sessions: 0,
        accessories: BTreeMap::new(),
    };
    for session in sessions {
        let (mut narrow, mut exposed) = (false, false);
        for exercise in &session.exercises {
            let sets = exercise.executed_sets();
            let transfer = env.glossary.transfer(&exercise.key).get(lift);
            if sets <= 0.0 || transfer <= 0.0 {
                continue;
            }
            let volume = exercise.executed_volume();
            exposed = true;
            narrow |= transfer >= NARROW_TRANSFER;
            tally.sets += sets * transfer;
            tally.volume += volume * transfer;
            if Lift::from_name(&exercise.key) == Some(lift) {
                tally.raw_sets += sets;
                tally.raw_volume += volume;
                continue;
            }
            let entry = tally
                .accessories
                .entry(exercise.key.clone())
                .or_insert_with(|| Accessory {
                    name: exercise.name.trim().to_owned(),
                    transfer,
                    sets: 0.0,
                    weighted_sets: 0.0,
                    volume: 0.0,
                });
            entry.sets += sets;
            entry.weighted_sets += sets * transfer;
            entry.volume += volume;
        }
        tally.narrow_sessions += usize::from(narrow);
        tally.exposure_sessions += usize::from(exposed);
    }
    tally
}

pub fn compute(env: Env<'_>, sessions: Sessions<'_>) -> BTreeMap<String, LiftBreakdown> {
    let weeks = sessions
        .iter()
        .filter_map(|session| session.week_number)
        .collect::<std::collections::BTreeSet<_>>()
        .len()
        .max(1) as f64;
    Lift::ALL
        .into_iter()
        .map(|lift| {
            let tally = tally(env, sessions, lift);
            let mut accessories: Vec<Accessory> = tally
                .accessories
                .into_values()
                .map(|accessory| Accessory {
                    sets: round(accessory.sets, 1),
                    weighted_sets: round(accessory.weighted_sets, 1),
                    volume: round(accessory.volume, 1),
                    ..accessory
                })
                .collect();
            accessories.sort_by(|a, b| b.volume.total_cmp(&a.volume));
            (
                lift.key().to_owned(),
                LiftBreakdown {
                    sets: round(tally.sets, 1),
                    raw_sets: round(tally.raw_sets, 1),
                    volume: round(tally.volume, 1),
                    raw_volume: round(tally.raw_volume, 1),
                    frequency: round(tally.narrow_sessions as f64 / weeks, 1),
                    exposure_frequency: round(tally.exposure_sessions as f64 / weeks, 1),
                    accessories,
                },
            )
        })
        .collect()
}
