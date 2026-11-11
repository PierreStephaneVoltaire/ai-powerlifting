use serde::Serialize;

use super::Context;
use super::{fatigue_readiness, overview, peaking, workload};
use crate::calc::Computed;
use crate::calc::alerts::{self, Alert, AlertInput, rounded_maxes};

#[derive(Debug, Serialize)]
pub struct Alerts {
    pub alerts: Vec<Alert>,
    pub flags: Vec<String>,
}

pub fn build(context: &Context<'_>) -> Alerts {
    let (_, mut flags) = workload::build(context);
    let fatigue = fatigue_readiness::fatigue_of(context);
    let score = fatigue.ready().map(|result| result.score);
    if let Some(result) = fatigue.ready() {
        flags.extend(result.flags.iter().map(|flag| (*flag).to_owned()));
    }
    let projections = overview::projections(context);
    let acwr = fatigue_readiness::acwr_of(context);
    let readiness = fatigue_readiness::readiness_of(context);
    let banister = peaking::banister_of(context);
    let monotony = peaking::monotony_of(context);
    let decoupling = peaking::decoupling_of(context);
    let inol = fatigue_readiness::inol_of(context);
    if let Computed::Ready(inol) = &inol {
        for flag in &inol.flags {
            if !flags.contains(flag) {
                flags.push(flag.clone());
            }
        }
    }
    for week in &monotony.weekly {
        for flag in &week.flags {
            if !flags.iter().any(|existing| existing == flag) {
                flags.push((*flag).to_owned());
            }
        }
    }
    if let Computed::Ready(decoupling) = &decoupling {
        for flag in &decoupling.flags {
            if !flags.iter().any(|existing| existing == flag) {
                flags.push((*flag).to_owned());
            }
        }
    }
    let (specificity, _) = peaking::specificity_of(context);
    let banister = Some(banister);
    let decoupling = Some(decoupling);
    let monotony = Some(monotony);
    let maxes = rounded_maxes(&context.maxes);
    let input = AlertInput {
        week: context.current_week,
        fatigue_index: score,
        maxes: &maxes,
        projections: &projections.entries,
        banister: &banister,
        acwr: &acwr,
        decoupling: &decoupling,
        specificity: specificity.as_ref(),
        monotony: &monotony,
        readiness: &readiness,
    };
    Alerts {
        alerts: alerts::generate(
            context.env,
            &input,
            context.program,
            &context.completed_history,
            context.end,
            context.selected_week_count,
        ),
        flags,
    }
}
