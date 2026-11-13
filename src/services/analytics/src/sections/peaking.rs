use serde::Serialize;
use serde_json::Value;

use super::Context;
use crate::calc::Computed;
use crate::calc::banister::{self, Banister, Decoupling, MonotonyStrain};
use crate::calc::peaking::{self, Specificity, Taper, Timeline};
use crate::util::parse_date;

#[derive(Debug, Serialize)]
pub struct Peaking {
    pub banister: Computed<Banister>,
    pub monotony_strain: MonotonyStrain,
    pub decoupling: Computed<Decoupling>,
    pub taper_quality: Option<Computed<Taper>>,
    pub specificity_ratio: Option<Specificity>,
    pub specificity_target_competition: Option<Value>,
    pub peaking_timeline: Timeline,
}

pub fn banister_of(context: &Context<'_>) -> Computed<Banister> {
    let window_start = context.window_start.as_deref().and_then(parse_date);
    let mut banister = banister::banister_ffm(
        context.env,
        &context.full_history,
        &context.program_start,
        &context.maxes,
        Some(context.end),
    );
    if let Computed::Ready(result) = &mut banister {
        result.tsb_label = banister::tsb_label(result.tsb_today, context.planned_overreach);
        if let Some(start) = window_start {
            result
                .series
                .retain(|point| parse_date(&point.date).is_some_and(|date| date >= start));
        }
    }
    banister
}

pub fn monotony_of(context: &Context<'_>) -> MonotonyStrain {
    banister::monotony_strain(
        context.env,
        &context.full_history,
        &context.program_start,
        &context.maxes,
        Some(context.end),
        context.window_start.as_deref().and_then(parse_date),
    )
}

pub fn decoupling_of(context: &Context<'_>) -> Computed<Decoupling> {
    banister::decoupling(
        context.env,
        &context.completed_history,
        &context.program_start,
        &context.maxes,
        Some(context.end),
    )
}

pub fn specificity_of(context: &Context<'_>) -> (Option<Specificity>, Option<Value>) {
    let target = peaking::target_competition(context.program, context.end);
    let weeks_to_comp = target
        .as_ref()
        .and_then(|target| target.get("date"))
        .and_then(Value::as_str)
        .and_then(parse_date)
        .filter(|date| *date > context.end)
        .map(|date| (date - context.end).num_days() as f64 / 7.0);
    let ratio =
        peaking::specificity_ratio(context.env, &context.completed_in_window, weeks_to_comp)
            .into_ready();
    (ratio, target)
}

pub fn build(context: &Context<'_>) -> Peaking {
    let banister = banister_of(context);
    let (specificity, target) = specificity_of(context);
    let timeline = peaking::timeline(
        context.env,
        context.program,
        &context.sessions,
        context.end,
        banister.ready(),
        &context.maxes,
    );
    Peaking {
        monotony_strain: monotony_of(context),
        decoupling: decoupling_of(context),
        taper_quality: peaking::taper_quality(
            context.env,
            context.program,
            &context.completed_history,
            &context.maxes,
            &context.program_start,
            Some(context.end),
        ),
        banister,
        specificity_ratio: specificity,
        specificity_target_competition: target,
        peaking_timeline: timeline,
    }
}
