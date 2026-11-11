use std::collections::BTreeMap;

use serde::Serialize;
use serde_json::{Value, json};

use super::Context;
use crate::calc::acwr::{self, Acwr};
use crate::calc::fatigue::{self, FatigueWindow, Spike};
use crate::calc::inol::{self, Inol, InolInput};
use crate::calc::intensity::{self, Distribution};
use crate::calc::landmarks::{self, Landmarks};
use crate::calc::readiness::{self, Readiness};
use crate::calc::{Computed, DIMENSION_WEIGHTS, Dims};
use crate::util::round;

#[derive(Debug, Serialize)]
pub struct FatigueDimensions {
    pub weekly: BTreeMap<i64, Dims>,
    pub acwr: Computed<Acwr>,
    pub spike: Spike,
    pub dimension_weights: Dims,
    pub label: &'static str,
}

#[derive(Debug, Serialize)]
pub struct FatigueReadiness {
    pub fatigue_index: Option<f64>,
    pub fatigue_components: Value,
    pub fatigue_dimensions: FatigueDimensions,
    pub inol: Option<Inol>,
    pub acwr: Computed<Acwr>,
    pub ri_distribution: Option<Distribution>,
    pub volume_landmarks: Landmarks,
    pub readiness_score: Readiness,
}

pub fn fatigue_of(context: &Context<'_>) -> Computed<fatigue::FatigueIndex> {
    fatigue::fatigue_index(
        context.env,
        &context.completed_history,
        FatigueWindow {
            days: context.selected_week_count * 7,
            reference: Some(context.end),
            start: context.window_start.as_deref(),
            end: context.window_end.as_deref(),
            target_rpe_midpoint: context.target_rpe_midpoint(),
        },
        &context.maxes,
        &context.program_start,
    )
}

pub fn acwr_of(context: &Context<'_>) -> Computed<Acwr> {
    acwr::compute(
        context.env,
        &context.completed_history,
        &context.program_start,
        &context.maxes,
        Some(context.phases),
        Some(context.current_week),
        Some(context.end),
    )
}

pub fn inol_of(context: &Context<'_>) -> Computed<Inol> {
    inol::compute(InolInput {
        sessions: &context.completed_in_window,
        history: &context.completed_history,
        program_start: &context.program_start,
        maxes: &context.maxes,
        profiles: &context.program.lift_profiles,
        phases: context.phases,
        selected_weeks: context.selected_week_count,
        reference: Some(context.end),
        today: context.env.today,
    })
}

pub fn readiness_of(context: &Context<'_>) -> Readiness {
    readiness::compute(
        context.env,
        &context.all_to_ref,
        context.program,
        &context.program_start,
        Some(context.end),
    )
}

pub fn build(context: &Context<'_>) -> FatigueReadiness {
    let fatigue = fatigue_of(context);
    let weekly = fatigue::weekly_by_dimension(
        context.env,
        &context.completed_in_window,
        &context.program_start,
        &context.maxes,
    );
    let spike = fatigue::dimensional_spike(&weekly);
    let acwr = acwr_of(context);
    let fatigue_dimensions = FatigueDimensions {
        weekly: weekly
            .into_iter()
            .map(|(week, dims)| (week, dims.map(|value| round(value, 1))))
            .collect(),
        acwr: acwr_of(context),
        spike,
        dimension_weights: DIMENSION_WEIGHTS,
        label: "selected_window_dimensions_current_state_acwr",
    };
    let (score, components) = match fatigue.into_ready() {
        Some(result) => (
            Some(result.score),
            serde_json::to_value(&result.components).unwrap_or_else(|_| json!({})),
        ),
        None => (None, json!({})),
    };
    FatigueReadiness {
        fatigue_index: score,
        fatigue_components: components,
        fatigue_dimensions,
        inol: inol_of(context).into_ready(),
        acwr,
        ri_distribution: intensity::distribution(&context.completed_in_window, &context.maxes)
            .into_ready(),
        volume_landmarks: landmarks::compute(
            context.env,
            &context.completed_history,
            &context.maxes,
            &context.program_start,
            context.end,
        ),
        readiness_score: readiness_of(context),
    }
}
