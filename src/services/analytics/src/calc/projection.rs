use std::collections::BTreeMap;

use chrono::NaiveDate;
use serde::Serialize;
use serde_json::{Map, Value};

use super::weeks::{current_week, infer_program_start};
use super::{Computed, Env, Sessions, deload, e1rm, progression, scoring};
use crate::model::{Competition, Lift, Maxes, ProgramData};
use crate::util::{clamp, median, num, num_of, present, round, round_even};

const MIN_MULTIPLIER: f64 = 0.92;
const MAX_MULTIPLIER: f64 = 1.05;
const MIN_CALIBRATED_MEETS: usize = 2;

#[derive(Debug, Clone, Serialize)]
pub struct Calibration {
    pub calibrated: bool,
    pub meets: usize,
    pub median_prr: Option<f64>,
    pub lambda_multiplier: Option<f64>,
}

pub fn calibration(competitions: &[Competition], reference: NaiveDate) -> Calibration {
    let mut ordered: Vec<&Competition> = competitions.iter().collect();
    ordered.sort_by(|a, b| b.date_text.cmp(&a.date_text));
    let totals: Vec<f64> = ordered
        .into_iter()
        .filter(|competition| competition.date.is_some_and(|date| date <= reference))
        .filter(|competition| competition.status == "completed")
        .filter_map(Competition::prr_total)
        .filter(|total| *total > 0.0)
        .collect();
    let meets = totals.len();
    let median_prr = (!totals.is_empty()).then(|| round(median(&totals[..totals.len().min(3)]), 3));
    let calibrated = meets >= MIN_CALIBRATED_MEETS && median_prr.is_some();
    Calibration {
        calibrated,
        meets,
        median_prr,
        lambda_multiplier: median_prr
            .filter(|_| calibrated)
            .map(|value| round(clamp(value, MIN_MULTIPLIER, MAX_MULTIPLIER), 3)),
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct LiftProjection {
    pub current: f64,
    pub projected: f64,
    pub slope_kg_per_week: f64,
    pub confidence: f64,
    pub ceiling_clamped: bool,
}

#[derive(Debug, Clone, Serialize)]
pub struct Projection {
    pub total: f64,
    pub confidence: f64,
    pub weeks_to_comp: f64,
    pub method: &'static str,
    pub lifts: BTreeMap<&'static str, LiftProjection>,
    pub projection_calibration: Calibration,
}

pub fn meet_projection(
    env: Env<'_>,
    program: &ProgramData,
    sessions: Sessions<'_>,
    comp_date: &str,
    reference: NaiveDate,
) -> Computed<Projection> {
    if comp_date.is_empty() {
        return Computed::insufficient("No competition date set");
    }
    let Some(comp) = crate::util::parse_date(comp_date) else {
        return Computed::insufficient(format!("Invalid competition date: {comp_date}"));
    };
    if comp <= reference {
        return Computed::insufficient("Competition date is in the past");
    }
    let weeks_to_comp = (comp - reference).num_days() as f64 / 7.0;
    let meta = &program.meta;
    let owned_start;
    let program_start = {
        let configured = meta.program_start();
        if configured.is_empty() {
            owned_start = infer_program_start(sessions);
            owned_start.as_str()
        } else {
            owned_start = configured;
            owned_start.as_str()
        }
    };
    let competitions: Vec<&Competition> = program.competitions.iter().collect();
    let from_competitions = e1rm::from_competitions(&competitions, reference);
    let from_sessions = e1rm::from_sessions(sessions, 42, reference);
    let maxes = if from_competitions.is_empty() {
        from_sessions
    } else {
        from_competitions
    };
    if maxes.is_empty() {
        return Computed::insufficient("No session data to estimate maxes from");
    }
    let calibration = calibration(&program.competitions, reference);
    let bodyweight = first_number(&meta.map, &["current_body_weight_kg", "bodyweight_kg"]);
    let sex = match meta.get("sex") {
        None => "male".to_owned(),
        Some(value) => value.as_str().unwrap_or_default().to_lowercase(),
    };
    let total_now: f64 = Lift::ALL
        .iter()
        .map(|lift| maxes.get(*lift).unwrap_or(0.0))
        .sum();
    let dots_now = if bodyweight > 0.0 && total_now > 0.0 {
        scoring::dots(total_now, bodyweight, &sex).unwrap_or(0.0)
    } else {
        0.0
    };
    let (base_lambda, peak_factor) = if dots_now >= 400.0 {
        (0.85, 1.05)
    } else if dots_now < 300.0 {
        (0.96, 1.01)
    } else {
        (0.90, 1.03)
    };
    let mut lambda = base_lambda;
    if let Some(multiplier) = calibration.lambda_multiplier {
        lambda = (base_lambda * multiplier).min(0.995);
    }
    let taper = if weeks_to_comp >= 12.0 {
        3.0
    } else if weeks_to_comp >= 8.0 {
        2.0
    } else {
        1.0
    };
    let week_now = current_week(program_start, sessions, env.today);
    let comp_week = week_now as f64 + weeks_to_comp;
    let remaining = deload::detect(sessions, program_start)
        .iter()
        .filter(|load| load.is_deload && week_now <= load.week && (load.week as f64) <= comp_week)
        .count() as f64;
    let planned_deloads = if remaining == 0.0 && weeks_to_comp > 4.0 {
        (weeks_to_comp / 4.0).floor()
    } else {
        remaining
    };
    let n_t = (weeks_to_comp - taper - planned_deloads).max(0.0);
    let ceiling_pct = 0.20_f64.min(0.10 + 0.005 * (weeks_to_comp - 8.0).max(0.0));

    let mut lifts: BTreeMap<&'static str, LiftProjection> = BTreeMap::new();
    let mut has_progression = false;
    for lift in Lift::ALL {
        let Some(current) = maxes.get(lift) else {
            continue;
        };
        let progression =
            progression::progression_rate(sessions, lift.key(), program_start, reference);
        let (slope, fit) = match &progression {
            Computed::Ready(result) => {
                has_progression = true;
                (result.slope_kg_per_week, result.fit_quality)
            }
            Computed::Insufficient(_) => (0.0, 0.0),
        };
        lambda = lambda.min(0.995);
        let gain = if n_t > 0.0 && slope > 0.0 {
            if lambda < 0.999999 {
                slope * lambda * (1.0 - lambda.powf(n_t)) / (1.0 - lambda)
            } else {
                slope * n_t
            }
        } else {
            0.0
        };
        let mut projected = (current + gain) * peak_factor;
        let ceiling = current * (1.0 + ceiling_pct);
        let clamped = projected > ceiling;
        projected = current.max(projected.min(ceiling));
        lifts.insert(
            lift.key(),
            LiftProjection {
                current: round(current, 1),
                projected: round(projected, 1),
                slope_kg_per_week: slope,
                confidence: round(clamp(fit, 0.0, 1.0), 2),
                ceiling_clamped: clamped,
            },
        );
    }
    if lifts.is_empty() {
        return Computed::insufficient("No lift maxes found (squat, bench, deadlift)");
    }
    if !has_progression {
        return Computed::insufficient("Insufficient session data to estimate progression");
    }
    let total = lifts.values().map(|lift| lift.projected).sum::<f64>();
    let confidence = lifts.values().map(|lift| lift.confidence).sum::<f64>() / lifts.len() as f64;
    Computed::Ready(Projection {
        total: round(total, 1),
        confidence: round(confidence, 2),
        weeks_to_comp: round(weeks_to_comp, 1),
        method: "session_estimated",
        lifts,
        projection_calibration: calibration,
    })
}

pub fn first_number(map: &Map<String, Value>, keys: &[&str]) -> f64 {
    keys.iter().find_map(|key| map.get(*key)).map_or(0.0, num)
}

#[derive(Debug, Serialize)]
pub struct Attempts {
    pub opener: f64,
    pub second: f64,
    pub third: f64,
}

#[derive(Debug, Serialize)]
pub struct AttemptPercents {
    pub opener: f64,
    pub second: f64,
    pub third: f64,
}

#[derive(Debug, Serialize)]
pub struct AttemptSelection {
    #[serde(flatten)]
    pub lifts: BTreeMap<&'static str, Attempts>,
    pub total: f64,
    pub attempt_pct_used: AttemptPercents,
}

fn to_plate(value: f64) -> f64 {
    round_even(value / 2.5) * 2.5
}

pub fn attempt_selection(
    projected: &Maxes,
    attempt_pct: Option<&Map<String, Value>>,
) -> Option<AttemptSelection> {
    if projected.is_empty() {
        return None;
    }
    let raw = attempt_pct.filter(|map| !map.is_empty());
    let pick =
        |key: &str, default: f64| raw.map_or(default, |map| map.get(key).map_or(default, num));
    let percents = AttemptPercents {
        opener: pick("opener", 0.90),
        second: pick("second", 0.955),
        third: pick("third", 1.00),
    };
    let mut lifts = BTreeMap::new();
    let mut third_total = 0.0;
    for lift in Lift::ALL {
        let Some(max) = projected.get(lift) else {
            continue;
        };
        let attempts = Attempts {
            opener: to_plate(max * percents.opener),
            second: to_plate(max * percents.second),
            third: to_plate(max * percents.third),
        };
        third_total += attempts.third;
        lifts.insert(lift.key(), attempts);
    }
    Some(AttemptSelection {
        lifts,
        total: round(third_total, 1),
        attempt_pct_used: percents,
    })
}

#[derive(Debug, Serialize)]
pub struct MultiplierSuggestion {
    pub lift: &'static str,
    pub suggested_multiplier: f64,
    pub current_multiplier: f64,
    pub difference: f64,
    pub basis: String,
    pub sample_size: usize,
}

#[derive(Debug, Serialize)]
pub struct MultiplierSuggestions {
    pub squat: Option<MultiplierSuggestion>,
    pub bench: Option<MultiplierSuggestion>,
    pub deadlift: Option<MultiplierSuggestion>,
}

struct Actual {
    date: NaiveDate,
    source: String,
    kg: [f64; 3],
}

pub fn multiplier_suggestions(
    program: &ProgramData,
    sessions: Sessions<'_>,
    max_history: &[Value],
    reference: NaiveDate,
) -> MultiplierSuggestions {
    let mut current = [1.0_f64; 3];
    for profile in &program.lift_profiles {
        if let Some(lift) = Lift::from_name(&profile.lift) {
            let value = profile.e1rm_multiplier.unwrap_or(1.0);
            if value > 0.0 {
                current[lift as usize] = value;
            }
        }
    }
    let mut actuals: Vec<Actual> = program
        .competitions
        .iter()
        .filter(|competition| competition.status == "completed")
        .filter_map(|competition| {
            let date = competition.date?;
            let results = competition.results.as_ref()?;
            Some(Actual {
                date,
                source: format!(
                    "Competition: {}",
                    competition
                        .name
                        .clone()
                        .unwrap_or_else(|| "None".to_owned())
                ),
                kg: [
                    num_of(results.get("squat_kg")),
                    num_of(results.get("bench_kg")),
                    num_of(results.get("deadlift_kg")),
                ],
            })
        })
        .collect();
    for entry in max_history.iter().filter_map(Value::as_object) {
        let Some(date) = crate::util::parse_date(&crate::util::text(entry, "date")) else {
            continue;
        };
        let context = present(entry.get("context")).map_or_else(
            || "Manual".to_owned(),
            |value| {
                value
                    .as_str()
                    .map_or_else(|| value.to_string(), str::to_owned)
            },
        );
        actuals.push(Actual {
            date,
            source: format!("Max History: {context}"),
            kg: [
                num_of(entry.get("squat_kg")),
                num_of(entry.get("bench_kg")),
                num_of(entry.get("deadlift_kg")),
            ],
        });
    }
    actuals.sort_by(|a, b| b.date.cmp(&a.date));
    let mut ratios: [Vec<f64>; 3] = Default::default();
    let mut sources: [Vec<String>; 3] = Default::default();
    for actual in actuals.iter().filter(|actual| actual.date <= reference) {
        let raw = e1rm::from_sessions(sessions, 42, actual.date);
        for lift in Lift::ALL {
            let given = actual.kg[lift as usize];
            let estimated = raw.get(lift).unwrap_or(0.0);
            if given > 0.0 && estimated > 0.0 {
                let ratio = given / estimated;
                if (0.80..=1.15).contains(&ratio) {
                    ratios[lift as usize].push(ratio);
                    sources[lift as usize].push(actual.source.clone());
                }
            }
        }
    }
    let suggest = |lift: Lift| {
        let index = lift as usize;
        if ratios[index].is_empty() {
            return None;
        }
        let clamped = round(clamp(median(&ratios[index]), 0.85, 1.10), 2);
        let mut unique = sources[index].clone();
        unique.sort();
        unique.dedup();
        let mut basis = format!("Based on {} comparison point(s) from ", ratios[index].len());
        if unique.len() > 2 {
            basis.push_str(&format!(
                "{}, {}, and {} more.",
                unique[0],
                unique[1],
                unique.len() - 2
            ));
        } else {
            basis.push_str(&unique.join(" and "));
            basis.push('.');
        }
        Some(MultiplierSuggestion {
            lift: lift.key(),
            suggested_multiplier: clamped,
            current_multiplier: current[index],
            difference: round(clamped - current[index], 2),
            basis,
            sample_size: ratios[index].len(),
        })
    };
    MultiplierSuggestions {
        squat: suggest(Lift::Squat),
        bench: suggest(Lift::Bench),
        deadlift: suggest(Lift::Deadlift),
    }
}
