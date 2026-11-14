use std::collections::BTreeMap;

use crate::model::Session;

const BIG_LIFTS: [&str; 4] = ["squat", "bench", "bench press", "deadlift"];

#[derive(Debug, Default)]
pub struct Inputs {
    pub weekly_e1rm: BTreeMap<i64, [Option<f64>; 3]>,
    pub weekly_accessory: BTreeMap<i64, Vec<(String, f64)>>,
}

fn lift_slot(name: &str) -> Option<usize> {
    if name.contains("squat") && !name.replace("backout", "").contains("back") {
        return Some(0);
    }
    let bench = name == "bench press"
        || name == "bench"
        || (name.contains("bench")
            && name.contains("press")
            && !["incline", "close", "pause", "spoto"]
                .iter()
                .any(|word| name.contains(word)));
    if bench {
        return Some(1);
    }
    (name.contains("deadlift") && !name.contains("rdl") && !name.contains("romanian")).then_some(2)
}

pub fn build(sessions: &[Session], cutoff: &str) -> Inputs {
    let mut inputs = Inputs::default();
    for session in sessions {
        if !session.completed || session.date_text.as_str() < cutoff {
            continue;
        }
        let Some(week) = session.week_number.filter(|week| *week > 0) else {
            continue;
        };
        for exercise in &session.exercises {
            let sets = exercise.executed_sets();
            let name_lower = exercise.key.as_str();
            if exercise.kg > 0.0 && exercise.reps > 0.0 && sets > 0.0 {
                let e1rm = if exercise.reps < 30.0 {
                    exercise.kg * (1.0 + exercise.reps / 30.0)
                } else {
                    exercise.kg
                };
                if let Some(slot) = lift_slot(name_lower) {
                    let entry = inputs.weekly_e1rm.entry(week).or_default();
                    entry[slot] = Some(entry[slot].map_or(e1rm, |current| current.max(e1rm)));
                }
            }
            if BIG_LIFTS.contains(&name_lower.trim()) {
                continue;
            }
            let volume = sets * exercise.reps * exercise.kg;
            if volume <= 0.0 {
                continue;
            }
            let week_entry = inputs.weekly_accessory.entry(week).or_default();
            match week_entry
                .iter_mut()
                .find(|(name, _)| *name == exercise.name)
            {
                Some(slot) => slot.1 += volume,
                None => week_entry.push((exercise.name.clone(), volume)),
            }
        }
    }
    inputs
}
