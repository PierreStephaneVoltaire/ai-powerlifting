use std::collections::BTreeMap;

use super::correlate::LOW_N;
use super::tolerance::Point;
use super::types::{Correlation, Evidence, Signal, Tolerance};
use crate::compare::format::number;

const MIN_SIGNAL_TAU: f64 = 0.3;
const MIN_SIGNAL_N: i64 = 4;
const SIGNIFICANT_P: f64 = 0.05;

pub struct BlockFacts {
    pub label: String,
    pub classification: BTreeMap<String, String>,
}

fn phrase(name: &str) -> String {
    name.replace(['_', '.'], " ")
}

fn strength(correlation: &Correlation) -> &'static str {
    let tau = correlation.kendall.tau.map_or(0.0, f64::abs);
    if correlation.kendall.p.is_some_and(|p| p < SIGNIFICANT_P) || tau >= 0.6 {
        "strong"
    } else if tau >= 0.4 {
        "moderate"
    } else {
        "weak"
    }
}

fn evidence(correlation: &Correlation, facts: &BTreeMap<String, BlockFacts>) -> Vec<Evidence> {
    let key = correlation
        .lift
        .clone()
        .unwrap_or_else(|| "total".to_owned());
    correlation
        .observations
        .iter()
        .map(|observation| {
            let fact = facts.get(&observation.block_key);
            Evidence {
                block_key: observation.block_key.clone(),
                label: fact.map(|fact| fact.label.clone()).unwrap_or_default(),
                exposure: observation.x,
                outcome: observation.y,
                classification: fact
                    .and_then(|fact| fact.classification.get(&key).cloned())
                    .unwrap_or_else(|| "insufficient_data".to_owned()),
            }
        })
        .collect()
}

fn from_correlation(correlation: &Correlation, facts: &BTreeMap<String, BlockFacts>) -> Signal {
    let positive = correlation.direction == "positive";
    let target = correlation
        .lift
        .clone()
        .unwrap_or_else(|| "total".to_owned());
    let statement = format!(
        "Blocks with higher {} had {} {target} e1RM progress per week (tau {}, n {}).",
        phrase(&correlation.exposure),
        if positive { "larger" } else { "smaller" },
        number(correlation.kendall.tau.unwrap_or(0.0)),
        correlation.n,
    );
    Signal {
        variable: correlation.exposure.clone(),
        outcome: correlation.outcome.clone(),
        lift: correlation.lift.clone(),
        statement,
        strength: strength(correlation).to_owned(),
        n: correlation.n,
        low_n: correlation.low_n,
        tau: correlation.kendall.tau,
        p: correlation.kendall.p,
        evidence: evidence(correlation, facts),
    }
}

fn tolerance_signals(
    tolerance: &Tolerance,
    points: &BTreeMap<String, BTreeMap<String, Vec<Point>>>,
) -> Vec<Signal> {
    let mut stalls = Vec::new();
    for (lift, variables) in &tolerance.by_lift {
        for (name, item) in variables {
            let (Some(onset), Some(range)) = (item.stall_onset, item.positive_range.as_ref())
            else {
                continue;
            };
            let members = points
                .get(lift)
                .and_then(|map| map.get(name))
                .map(Vec::as_slice)
                .unwrap_or_default();
            stalls.push(Signal {
                variable: format!("{lift}.{name}"),
                outcome: format!("{lift}_e1rm_delta_per_week"),
                lift: Some(lift.clone()),
                statement: format!(
                    "{lift} improved between {} and {} {}; progress stalled from {} upward.",
                    number(range.min),
                    number(range.max),
                    phrase(name),
                    number(onset),
                ),
                strength: if item.low_n { "weak" } else { "moderate" }.to_owned(),
                n: item.sample_size,
                low_n: item.sample_size < LOW_N as i64,
                tau: None,
                p: None,
                evidence: members
                    .iter()
                    .map(|point| Evidence {
                        block_key: point.block_key.clone(),
                        label: String::new(),
                        exposure: point.x,
                        outcome: point.delta_per_week,
                        classification: point.label.clone(),
                    })
                    .collect(),
            });
        }
    }
    stalls
}

pub fn build(
    correlations: &[Correlation],
    tolerance: &Tolerance,
    points: &BTreeMap<String, BTreeMap<String, Vec<Point>>>,
    facts: &BTreeMap<String, BlockFacts>,
) -> (Vec<Signal>, Vec<Signal>) {
    let mut worked = Vec::new();
    let mut did_not_work = Vec::new();
    for correlation in correlations {
        let Some(tau) = correlation.kendall.tau else {
            continue;
        };
        if correlation.n < MIN_SIGNAL_N || tau.abs() < MIN_SIGNAL_TAU {
            continue;
        }
        let signal = from_correlation(correlation, facts);
        if tau > 0.0 {
            worked.push(signal);
        } else {
            did_not_work.push(signal);
        }
    }
    did_not_work.extend(tolerance_signals(tolerance, points));
    (worked, did_not_work)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::lifetime::correlate::{Row, analyse};
    use crate::lifetime::tolerance;

    fn rows(sign: f64) -> Vec<Row> {
        (0..8)
            .map(|index| Row {
                block_key: format!("block_{index}"),
                exposures: BTreeMap::from([("squat.weekly_hard_sets".to_owned(), index as f64)]),
                outcomes: BTreeMap::from([
                    ("squat".to_owned(), sign * index as f64),
                    ("total".to_owned(), sign * index as f64),
                ]),
            })
            .collect()
    }

    fn facts() -> BTreeMap<String, BlockFacts> {
        (0..8)
            .map(|index| {
                (
                    format!("block_{index}"),
                    BlockFacts {
                        label: format!("Block {index}"),
                        classification: BTreeMap::from([(
                            "squat".to_owned(),
                            "improved".to_owned(),
                        )]),
                    },
                )
            })
            .collect()
    }

    fn signals(sign: f64) -> (Vec<Signal>, Vec<Signal>) {
        let correlations = analyse(&rows(sign));
        build(
            &correlations,
            &tolerance::build(&BTreeMap::new()),
            &BTreeMap::new(),
            &facts(),
        )
    }

    #[test]
    fn positive_dose_response_is_worked_with_evidence_and_strength() {
        let (worked, did_not_work) = signals(1.0);
        assert!(did_not_work.is_empty());
        let signal = worked
            .iter()
            .find(|signal| signal.outcome == "squat_e1rm_delta_per_week")
            .expect("squat signal");
        assert_eq!(signal.strength, "strong");
        assert_eq!(signal.n, 8);
        assert!(!signal.low_n);
        assert_eq!(signal.evidence.len(), 8);
        assert_eq!(signal.evidence[3].label, "Block 3");
        assert_eq!(signal.evidence[3].classification, "improved");
    }

    #[test]
    fn negative_dose_response_did_not_work() {
        let (worked, did_not_work) = signals(-1.0);
        assert!(worked.is_empty());
        assert!(!did_not_work.is_empty());
        assert!(did_not_work.iter().all(|signal| signal.tau.unwrap() < 0.0));
    }

    #[test]
    fn weak_or_tiny_samples_produce_no_signal() {
        let tiny: Vec<Row> = rows(1.0).into_iter().take(3).collect();
        let (worked, did_not_work) = build(
            &analyse(&tiny),
            &tolerance::build(&BTreeMap::new()),
            &BTreeMap::new(),
            &facts(),
        );
        assert!(worked.is_empty() && did_not_work.is_empty());
    }
}
