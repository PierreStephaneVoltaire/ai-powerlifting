use chrono::{Duration, NaiveDate};
use serde::Serialize;

use super::weeks::{current_week, find_phase};
use super::{Env, Sessions, e1rm, fatigue};
use crate::model::{Competition, Maxes, ProgramData, Session};
use crate::util::{clamp, mean, num_of, round, theil_sen};

#[derive(Debug, Serialize)]
pub struct ReadinessComponents {
    pub fatigue_norm: f64,
    pub rpe_drift: f64,
    pub wellness: f64,
    pub performance_trend: f64,
    pub bw_deviation: f64,
}

#[derive(Debug, Serialize)]
pub struct Readiness {
    pub score: f64,
    pub training_score: f64,
    pub external_score: f64,
    pub zone: &'static str,
    pub components: ReadinessComponents,
    pub readiness_confidence: f64,
    pub training_readiness_confidence: f64,
    pub external_readiness_confidence: f64,
}

fn wellness_penalty(sessions: Sessions<'_>, days: i64, reference: NaiveDate) -> f64 {
    let cutoff = reference - Duration::days(days);
    let values: Vec<f64> = sessions
        .iter()
        .filter(|session| {
            session
                .date
                .is_some_and(|date| cutoff <= date && date <= reference)
        })
        .flat_map(|session| session.wellness.iter().copied())
        .collect();
    if values.is_empty() {
        return 0.5;
    }
    round(clamp(1.0 - mean(&values) / 5.0, 0.0, 1.0), 3)
}

fn performance_penalty(
    env: Env<'_>,
    sessions: Sessions<'_>,
    maxes: &Maxes,
    days: i64,
    reference: NaiveDate,
) -> f64 {
    let cutoff = reference - Duration::days(days);
    let mut days_map: std::collections::BTreeMap<NaiveDate, [Option<f64>; 3]> =
        std::collections::BTreeMap::new();
    for session in sessions.iter().filter(|session| session.completed) {
        let Some(date) = session
            .date
            .filter(|date| cutoff <= *date && *date <= reference)
        else {
            continue;
        };
        let lifts = days_map.entry(date).or_default();
        for exercise in &session.exercises {
            let Some(lift) = crate::model::Lift::from_name(&exercise.key) else {
                continue;
            };
            if exercise.failed_sets() > 0
                || exercise.executed_sets() <= 0.0
                || exercise.kg <= 0.0
                || exercise.reps_int() <= 0
            {
                continue;
            }
            let Some(value) = e1rm::estimate(exercise.kg, exercise.reps_int(), session.session_rpe)
            else {
                continue;
            };
            let slot = &mut lifts[lift as usize];
            if slot.is_none_or(|current| value > current) {
                *slot = Some(value);
            }
        }
    }
    let series: Vec<(NaiveDate, f64)> = days_map
        .into_iter()
        .filter_map(|(date, lifts)| {
            let present: Vec<f64> = lifts.into_iter().flatten().collect();
            (!present.is_empty())
                .then(|| (date, present.iter().sum::<f64>() / present.len() as f64))
        })
        .collect();
    if series.len() < 2 {
        return 0.5;
    }
    let xs: Vec<f64> = series
        .iter()
        .map(|(date, _)| (*date - series[0].0).num_days() as f64 / 7.0)
        .collect();
    let ys: Vec<f64> = series.iter().map(|(_, value)| *value).collect();
    let slope = theil_sen(&ys, &xs).slope;
    let estimated;
    let maxes = if maxes.is_empty() {
        estimated = e1rm::from_sessions_default(sessions, env.today);
        &estimated
    } else {
        maxes
    };
    let values: Vec<f64> = crate::model::Lift::ALL
        .iter()
        .filter_map(|lift| maxes.get(*lift))
        .filter(|value| *value > 0.0)
        .collect();
    let denominator = if values.is_empty() {
        2.5
    } else {
        (mean(&values) * 0.01).max(2.5)
    };
    let penalty = if slope < 0.0 {
        clamp(-slope / denominator, 0.0, 1.0)
    } else {
        0.0
    };
    round(penalty, 3)
}

pub fn next_competition<'a>(
    competitions: &[&'a Competition],
    reference: NaiveDate,
) -> Option<&'a Competition> {
    let mut ordered: Vec<&Competition> = competitions.to_vec();
    ordered.sort_by(|a, b| a.date_text.cmp(&b.date_text));
    ordered.into_iter().find(|competition| {
        competition.status == "confirmed" && competition.date.is_some_and(|date| date > reference)
    })
}

fn bodyweight_penalty(
    sessions: Sessions<'_>,
    program: &ProgramData,
    days: i64,
    reference: NaiveDate,
) -> f64 {
    let cutoff = reference - Duration::days(days);
    let mut entries: Vec<(NaiveDate, f64)> = sessions
        .iter()
        .filter_map(|session| {
            let date = session
                .date
                .filter(|date| cutoff <= *date && *date <= reference)?;
            Some((date, session.body_weight_kg?))
        })
        .collect();
    entries.sort_by_key(|(date, _)| *date);
    if entries.len() < 2 {
        return 0.5;
    }
    let recent = &entries[entries.len() - entries.len().min(7)..];
    let xs: Vec<f64> = recent
        .iter()
        .map(|(date, _)| (*date - recent[0].0).num_days() as f64 / 7.0)
        .collect();
    let ys: Vec<f64> = recent.iter().map(|(_, value)| *value).collect();
    let actual = theil_sen(&ys, &xs).slope;
    let weight_class = num_of(program.meta.get("weight_class_kg"));
    let current = recent[recent.len() - 1].1;
    let competitions: Vec<&Competition> = program.competitions.iter().collect();
    if let Some(upcoming) = next_competition(&competitions, reference)
        && let Some(date) = upcoming.date
        && weight_class > 0.0
        && current > weight_class
    {
        let weeks = ((date - reference).num_days() as f64 / 7.0).max(1.0 / 7.0);
        if weeks <= 6.0 {
            let expected = (weight_class - current) / weeks;
            return round(clamp((actual - expected).abs() / 0.5, 0.0, 1.0), 3);
        }
    }
    let center = mean(&ys);
    if center <= 0.0 {
        return 0.5;
    }
    let cv = (ys.iter().map(|value| (value - center).powi(2)).sum::<f64>() / ys.len() as f64)
        .sqrt()
        / center;
    round(clamp(cv / 0.03, 0.0, 1.0), 3)
}

fn score_from(components: &[(f64, f64)]) -> (f64, f64) {
    let available: f64 = components.iter().map(|(weight, _)| weight).sum();
    if available <= 0.0 {
        return (50.0, 0.0);
    }
    let penalty = components
        .iter()
        .map(|(weight, value)| weight * value)
        .sum::<f64>()
        / available;
    (
        round(clamp((1.0 - penalty) * 100.0, 0.0, 100.0), 1),
        round(available, 2),
    )
}

pub fn compute(
    env: Env<'_>,
    sessions: Sessions<'_>,
    program: &ProgramData,
    program_start: &str,
    reference: Option<NaiveDate>,
) -> Readiness {
    let owned_start;
    let program_start = if program_start.is_empty() {
        owned_start = program.meta.program_start();
        owned_start.as_str()
    } else {
        program_start
    };
    let reference = reference.unwrap_or(env.today);
    let eligible: Vec<&Session> = sessions
        .iter()
        .copied()
        .filter(|session| session.date.is_some_and(|date| date <= reference))
        .collect();
    let maxes = e1rm::from_sessions_default(&eligible, env.today);
    let fatigue_score = fatigue::fatigue_index(
        env,
        &eligible,
        fatigue::FatigueWindow {
            days: 14,
            reference: Some(reference),
            ..Default::default()
        },
        &maxes,
        program_start,
    )
    .ready()
    .map(|result| result.score);

    let cutoff = reference - Duration::days(14);
    let rpes: Vec<f64> = eligible
        .iter()
        .filter(|session| {
            session
                .date
                .is_some_and(|date| cutoff <= date && date <= reference)
                && session.completed
        })
        .filter_map(|session| session.session_rpe)
        .collect();
    let week = current_week(program_start, &eligible, env.today);
    let target = find_phase(&program.phases, week)
        .and_then(|phase| phase.target_midpoint())
        .unwrap_or(7.5);
    let rpe_penalty = (!rpes.is_empty()).then(|| clamp((mean(&rpes) - target) / 2.0, 0.0, 1.0));

    let wellness = wellness_penalty(&eligible, 14, reference);
    let performance = performance_penalty(env, &eligible, &maxes, 14, reference);
    let bodyweight = bodyweight_penalty(&eligible, program, 14, reference);

    let mut training = Vec::new();
    if let Some(score) = fatigue_score {
        training.push((0.45, score));
    }
    if let Some(penalty) = rpe_penalty {
        training.push((0.30, penalty));
    }
    training.push((0.25, performance));
    let external = [(0.60, wellness), (0.40, bodyweight)];
    let (training_score, training_confidence) = score_from(&training);
    let (external_score, external_confidence) = score_from(&external);
    let (score, confidence) = if training_confidence > 0.0 && external_confidence > 0.0 {
        (
            round(0.70 * training_score + 0.30 * external_score, 1),
            round(0.70 * training_confidence + 0.30 * external_confidence, 2),
        )
    } else if training_confidence > 0.0 {
        (training_score, training_confidence)
    } else if external_confidence > 0.0 {
        (external_score, external_confidence)
    } else {
        (50.0, 0.0)
    };
    Readiness {
        score,
        training_score,
        external_score,
        zone: if score > 75.0 {
            "green"
        } else if score >= 50.0 {
            "yellow"
        } else {
            "red"
        },
        components: ReadinessComponents {
            fatigue_norm: fatigue_score.map_or(0.5, |value| round(value, 3)),
            rpe_drift: rpe_penalty.map_or(0.5, |value| round(value, 3)),
            wellness: round(wellness, 3),
            performance_trend: round(performance, 3),
            bw_deviation: round(bodyweight, 3),
        },
        readiness_confidence: confidence,
        training_readiness_confidence: training_confidence,
        external_readiness_confidence: external_confidence,
    }
}
