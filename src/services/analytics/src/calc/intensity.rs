use serde::Serialize;

use super::{ByLift, Computed, Sessions};
use crate::model::{Lift, Maxes};
use crate::util::round;

#[derive(Debug, Clone, Copy, Default)]
struct Counts {
    heavy: i64,
    moderate: i64,
    light: i64,
}

impl Counts {
    fn total(self) -> i64 {
        self.heavy + self.moderate + self.light
    }

    fn add(&mut self, intensity: f64, sets: i64) {
        if intensity > 0.85 {
            self.heavy += sets;
        } else if intensity >= 0.70 {
            self.moderate += sets;
        } else {
            self.light += sets;
        }
    }
}

#[derive(Debug, Serialize)]
pub struct Bucket {
    pub count: i64,
    pub pct: f64,
}

#[derive(Debug, Serialize)]
pub struct Buckets {
    pub heavy: Bucket,
    pub moderate: Bucket,
    pub light: Bucket,
}

fn buckets(counts: Counts, total: i64) -> Buckets {
    let bucket = |count: i64| Bucket {
        count,
        pct: round(count as f64 / total as f64 * 100.0, 1),
    };
    Buckets {
        heavy: bucket(counts.heavy),
        moderate: bucket(counts.moderate),
        light: bucket(counts.light),
    }
}

#[derive(Debug, Serialize)]
pub struct Distribution {
    pub overall: Buckets,
    pub per_lift: ByLift<Buckets>,
}

pub fn distribution(sessions: Sessions<'_>, maxes: &Maxes) -> Computed<Distribution> {
    if maxes.is_empty() {
        return Computed::insufficient("No current maxes for RI distribution");
    }
    let mut overall = Counts::default();
    let mut per_lift: ByLift<Counts> = ByLift::new();
    for session in sessions.iter().filter(|session| session.completed) {
        for exercise in &session.exercises {
            let Some(lift) = Lift::from_name(&exercise.key) else {
                continue;
            };
            let Some(max) = maxes.get(lift).filter(|max| *max > 0.0) else {
                continue;
            };
            let sets = exercise.sets_int();
            if exercise.kg <= 0.0 || sets <= 0 {
                continue;
            }
            let intensity = exercise.kg / max;
            overall.add(intensity, sets);
            per_lift.entry(lift, Counts::default).add(intensity, sets);
        }
    }
    let total = overall.total();
    if total == 0 {
        return Computed::insufficient("No qualifying sets for RI distribution");
    }
    Computed::Ready(Distribution {
        overall: buckets(overall, total),
        per_lift: ByLift(
            per_lift
                .0
                .into_iter()
                .map(|(lift, counts)| (lift, buckets(counts, counts.total().max(1))))
                .collect(),
        ),
    })
}
