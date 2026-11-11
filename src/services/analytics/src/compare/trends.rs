use std::collections::BTreeSet;

use chrono::Duration;
use serde_json::Value;

use super::context::Context;
use super::types::{
    CompetitionSummary, GoalSummary, Point, Row, TrainingDays, TrendPoint, Trends,
};
use crate::blocks::outcome::dots;
use crate::blocks::scope::{exercise_volume, latest_bodyweight};
use crate::blocks::strength::{canonical_lift, set_e1rm};
use crate::blocks::types::Bundle;
use crate::js::{iso_date, number, round_digits, round_or_null};

fn competition_summary(competition: &Value) -> CompetitionSummary {
    let text = |key: &str| {
        competition
            .get(key)
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_owned()
    };
    let nested = |path: &str| number(competition.pointer(path));
    CompetitionSummary {
        name: text("name"),
        date: text("date"),
        status: text("status"),
        federation: competition.get("federation").cloned(),
        weight_class_kg: number(competition.get("weight_class_kg")),
        bodyweight_kg: number(competition.get("body_weight_kg")),
        target_total_kg: nested("/targets/total_kg"),
        result_total_kg: nested("/results/total_kg"),
        projected_total_kg: nested("/projected_at_t_minus_1w/total_kg")
            .or_else(|| nested("/results/projected_at_t_minus_1w/total_kg")),
    }
}

pub fn row(bundle: &Bundle, context: Option<&Context>) -> Row {
    let outcome = bundle.historical.competition_outcome.as_ref();
    let summary = &bundle.historical.analytics_summary;
    Row {
        block_key: bundle.block.block_key.clone(),
        label: bundle.block.label.clone(),
        start_date: bundle.block.start_date.clone(),
        end_date: bundle.block.end_date.clone(),
        training_only: bundle.block.training_only,
        competition_name: outcome.map(|item| item.competition_name.clone()),
        competition_date: outcome.map(|item| item.competition_date.clone()),
        actual_total_kg: outcome
            .and_then(|item| item.results.as_ref())
            .and_then(|results| number(results.get("total_kg"))),
        actual_dots: outcome.and_then(|item| item.dots),
        actual_ipf_gl: outcome.and_then(|item| item.ipf_gl),
        estimated_dots: number(bundle.weekly.get("estimated_dots")),
        start_total_kg: bundle.historical.start_strength.total,
        end_total_kg: bundle.historical.end_strength.total,
        e1rm_delta_kg: bundle.historical.strength_delta.total,
        compliance_pct: summary.compliance_pct,
        fatigue_index: summary.fatigue_index,
        acwr_composite: summary.acwr_composite,
        total_volume_kg: summary.total_volume_kg,
        avg_inol: summary.avg_inol.clone(),
        projection_total_delta_kg: outcome
            .and_then(|item| item.projection_accuracy.as_ref())
            .and_then(|accuracy| accuracy.get("total_kg"))
            .and_then(|total| number(total.get("deltaKg"))),
        data_quality_flags: bundle.historical.missing_data.clone(),
        competitions: context
            .map(|context| context.competitions.iter().map(competition_summary).collect())
            .unwrap_or_default(),
        goals: context
            .map(|context| {
                context
                    .goals
                    .iter()
                    .map(|goal| GoalSummary {
                        id: goal.id.clone(),
                        title: goal.title.clone(),
                        goal_type: goal.goal_type.clone(),
                        priority: goal.priority.clone(),
                        target_total_kg: goal.target_total_kg,
                        target_dots: goal.target_dots,
                        target_ipf_gl: goal.target_ipf_gl,
                        target_date: goal.target_date.clone(),
                    })
                    .collect()
            })
            .unwrap_or_default(),
    }
}

pub fn trends(rows: &[Row]) -> Trends {
    let points = |pick: &dyn Fn(&Row) -> Option<f64>| -> Vec<Point> {
        rows.iter()
            .map(|row| Point {
                block_key: row.block_key.clone(),
                label: row.label.clone(),
                value: pick(row),
            })
            .collect()
    };
    Trends {
        actual_total: points(&|row| row.actual_total_kg),
        dots: points(&|row| row.actual_dots.or(row.estimated_dots)),
        ipf_gl: points(&|row| row.actual_ipf_gl),
        e1rm_total: points(&|row| row.end_total_kg),
        compliance: points(&|row| row.compliance_pct),
        fatigue: points(&|row| row.fatigue_index),
        volume: points(&|row| Some(row.total_volume_kg)),
    }
}

fn strain_by_date(bundle: &Bundle) -> Vec<(String, f64)> {
    bundle
        .weekly
        .pointer("/monotony_strain/weekly")
        .and_then(Value::as_array)
        .map(|rows| {
            rows.iter()
                .filter_map(|row| {
                    Some((
                        row.get("week_start")?.as_str()?.to_owned(),
                        row.get("strain")?.as_f64()?,
                    ))
                })
                .collect()
        })
        .unwrap_or_default()
}

pub fn series_for_block(bundle: &Bundle, context: Option<&Context>) -> Vec<TrendPoint> {
    let Some(context) = context else {
        return Vec::new();
    };
    let mut sessions: Vec<&crate::model::Session> =
        context.sessions.iter().filter(|s| s.completed).collect();
    sessions.sort_by(|a, b| a.date_text.cmp(&b.date_text));
    if sessions.is_empty() {
        return Vec::new();
    }
    let strain = strain_by_date(bundle);
    let start = &bundle.historical.start_strength;
    let mut carried = [start.squat, start.bench, start.deadlift];
    let mut rows: Vec<TrendPoint> = Vec::new();
    for week in bundle.block.week_start..=bundle.block.week_end {
        let in_week: Vec<&&crate::model::Session> = sessions
            .iter()
            .filter(|session| session.week_number.unwrap_or(0) == week && week > 0)
            .collect();
        let mut best: [Option<f64>; 3] = [None; 3];
        for session in &in_week {
            for exercise in &session.exercises {
                let Some(lift) = canonical_lift(&exercise.name) else {
                    continue;
                };
                let slot = match lift {
                    "squat" => 0,
                    "bench" => 1,
                    _ => 2,
                };
                let rpe = exercise.rpe.or(session.session_rpe);
                if let Some(value) = set_e1rm(exercise.kg, exercise.reps, rpe)
                    && best[slot].is_none_or(|current| value > current)
                {
                    best[slot] = round_or_null(Some(value), 1);
                }
            }
        }
        for slot in 0..3 {
            if best[slot].is_some() {
                carried[slot] = best[slot];
            }
        }
        let mut dates: Vec<&str> = in_week.iter().map(|s| s.date_text.as_str()).collect();
        dates.sort_unstable();
        let previous = rows
            .last()
            .and_then(|row| iso_date(&row.week_start))
            .map(|date| (date + Duration::days(7)).to_string());
        let week_start = dates
            .first()
            .map(|date| (*date).to_owned())
            .or(previous)
            .unwrap_or_else(|| bundle.block.start_date.clone());
        let total = match carried {
            [Some(squat), Some(bench), Some(deadlift)] => {
                round_or_null(Some(squat + bench + deadlift), 1)
            }
            _ => None,
        };
        let bodyweight = latest_bodyweight(
            &sessions,
            context.fallback_bodyweight,
            &week_start,
            &context.weight_log,
        );
        let volume: f64 = in_week.iter().map(|session| exercise_volume(session)).sum();
        rows.push(TrendPoint {
            block_key: bundle.block.block_key.clone(),
            label: bundle.block.label.clone(),
            week_number: week,
            squat_kg: carried[0],
            bench_kg: carried[1],
            deadlift_kg: carried[2],
            e1rm_total_kg: total,
            estimated_dots: total
                .zip(bodyweight)
                .and_then(|(total, weight)| dots(total, weight, context.sex)),
            volume_kg: round_digits(volume, 0) as i64,
            training_days: dates.iter().collect::<BTreeSet<_>>().len() as i64,
            strain: strain
                .iter()
                .find(|(date, _)| *date == week_start)
                .map(|(_, value)| *value),
            week_start,
        });
    }
    rows
}

pub fn training_days(rows: &[Row], series: &[TrendPoint]) -> Vec<TrainingDays> {
    rows.iter()
        .map(|row| {
            let points: Vec<&TrendPoint> = series
                .iter()
                .filter(|point| point.block_key == row.block_key)
                .collect();
            let total: i64 = points.iter().map(|point| point.training_days).sum();
            TrainingDays {
                block_key: row.block_key.clone(),
                label: row.label.clone(),
                completed_weeks: points.len() as i64,
                total_training_days: total,
                avg_training_days_per_week: (!points.is_empty())
                    .then(|| round_digits(total as f64 / points.len() as f64, 2)),
                strength_delta_kg: row.e1rm_delta_kg,
                compliance_pct: row.compliance_pct,
            }
        })
        .collect()
}
