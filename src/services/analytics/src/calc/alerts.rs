use std::collections::HashMap;

use chrono::{Duration, NaiveDate};
use serde::Serialize;

use super::acwr::Acwr;
use super::banister::{Banister, Decoupling, MonotonyStrain};
use super::peaking::Specificity;
use super::projection::Projection;
use super::readiness::Readiness;
use super::weeks::planned_overreach;
use super::{Computed, Env, Sessions, fatigue, readiness};
use crate::model::{Maxes, ProgramData, Session};
use crate::util::round;

#[derive(Debug, Clone, Serialize)]
pub struct Alert {
    pub severity: &'static str,
    pub source: &'static str,
    pub message: &'static str,
    pub raw_detail: String,
}

#[derive(Debug, Serialize)]
pub struct ProjectionEntry {
    #[serde(flatten)]
    pub projection: Projection,
    pub comp_name: Option<String>,
}

pub struct AlertInput<'a> {
    pub week: i64,
    pub fatigue_index: Option<f64>,
    pub maxes: &'a Maxes,
    pub projections: &'a [ProjectionEntry],
    pub banister: &'a Option<Computed<Banister>>,
    pub acwr: &'a Computed<Acwr>,
    pub decoupling: &'a Option<Computed<Decoupling>>,
    pub specificity: Option<&'a Specificity>,
    pub monotony: &'a Option<MonotonyStrain>,
    pub readiness: &'a Readiness,
}

fn alert(
    severity: &'static str,
    source: &'static str,
    message: &'static str,
    raw_detail: String,
) -> Alert {
    Alert {
        severity,
        source,
        message,
        raw_detail,
    }
}

fn py_float(value: f64) -> String {
    format!("{value:?}")
}

pub fn generate(
    env: Env<'_>,
    input: &AlertInput<'_>,
    program: &ProgramData,
    sessions: Sessions<'_>,
    reference: NaiveDate,
    window_weeks: i64,
) -> Vec<Alert> {
    let program_start = program.meta.program_start();
    let overreach = planned_overreach(
        &program.phases,
        Some(input.week).filter(|week| *week != 0),
        &program_start,
        env.today,
    );
    let lookback_weeks = window_weeks.max(1);
    let past: Vec<&Session> = sessions
        .iter()
        .copied()
        .filter(|session| session.date.is_some_and(|date| date <= reference))
        .collect();
    let mut alerts: Vec<Alert> = Vec::new();

    if let Some(score) = input.fatigue_index.filter(|score| *score >= 0.60) {
        let previous = fatigue::fatigue_index(
            env,
            &past,
            fatigue::FatigueWindow {
                days: (lookback_weeks * 7).max(7),
                reference: Some(reference - Duration::days(7)),
                ..Default::default()
            },
            input.maxes,
            &program_start,
        )
        .ready()
        .map(|result| result.score);
        if let Some(previous) = previous.filter(|previous| score > *previous) {
            alerts.push(alert(
                "warning",
                "fatigue",
                "Fatigue is elevated. Consider a lighter session or deload this week.",
                format!(
                    "fatigue_index={score:.3}, previous_window={previous:.3}, delta={:+.3}",
                    score - previous
                ),
            ));
        }
    }

    if let Some(composite) = input
        .acwr
        .ready()
        .and_then(|acwr| acwr.composite)
        .filter(|value| *value > 1.5)
    {
        alerts.push(if overreach {
            alert(
                "info",
                "acwr",
                "Load spike is consistent with your planned overreach.",
                format!("acwr_composite={composite:.3}, phase_intent=planned overreach"),
            )
        } else {
            alert(
                "warning",
                "acwr",
                "Training load jumped sharply. Monitor recovery closely.",
                format!("acwr_composite={composite:.3}, phase_intent=not overreach"),
            )
        });
    }

    if let Some(banister) = input.banister.as_ref().and_then(Computed::ready) {
        let tsb = banister.tsb_today;
        if tsb < -30.0 {
            alerts.push(alert(
                "warning",
                "banister",
                "You are in deep overload. Performance should rebound after a deload.",
                format!("tsb_today={tsb:.3}"),
            ));
        }
        if let Some(first) = input.projections.first()
            && first.projection.weeks_to_comp <= 2.0
            && (5.0..=15.0).contains(&tsb)
        {
            alerts.push(alert(
                "info",
                "banister",
                "You're in the peaking window for your upcoming meet.",
                format!(
                    "tsb_today={tsb:.3}, weeks_to_comp={:.1}",
                    first.projection.weeks_to_comp
                ),
            ));
        }
    }

    if let Some(decoupling) = input
        .decoupling
        .as_ref()
        .and_then(Computed::ready)
        .filter(|decoupling| decoupling.flags.contains(&"decoupling_fatigue_dominant"))
    {
        let detail = decoupling.series.last().map_or_else(
            || "decoupling_fatigue_dominant".to_owned(),
            |latest| {
                format!(
                    "decoupling_fatigue_dominant; current={:.3}, e1rm_slope={:.3}, fi_slope={:.3}",
                    latest.decoupling,
                    latest.e1rm_slope_pct_per_week,
                    latest.fi_slope_pct_points_per_week
                )
            },
        );
        alerts.push(alert(
            "warning",
            "decoupling",
            "Strength is flat but fatigue is climbing. Accumulated stress is outpacing adaptation.",
            detail,
        ));
    }

    if input.readiness.score < 50.0 {
        let previous = readiness::compute(
            env,
            &past,
            program,
            &program_start,
            Some(reference - Duration::days(7)),
        );
        if previous.score < 50.0 {
            alerts.push(alert(
                "warning",
                "readiness",
                "Readiness has been low consistently. Check sleep and stress.",
                format!(
                    "readiness={:.1}, previous_window={:.1}",
                    input.readiness.score, previous.score
                ),
            ));
        }
    }

    if let Some(specificity) = input
        .specificity
        .filter(|ratio| ratio.flags.contains(&"specificity_below_expected"))
    {
        let (low, high, weeks) = specificity.expected_band.as_ref().map_or_else(
            || (0.0, 0.0, "None".to_owned()),
            |band| {
                (
                    band.narrow.min,
                    band.narrow.max,
                    py_float(band.weeks_to_comp),
                )
            },
        );
        alerts.push(alert(
            "caution",
            "specificity",
            "More competition-lift practice recommended given how close your meet is.",
            format!(
                "narrow={:.3}, expected_narrow={low:.2}-{high:.2}, weeks_to_comp={weeks}",
                specificity.narrow
            ),
        ));
    }

    if let Some(latest) = input
        .monotony
        .as_ref()
        .and_then(|monotony| monotony.weekly.last())
        && latest.flags.contains(&"high_monotony")
    {
        alerts.push(alert(
            "caution",
            "monotony",
            "Your daily training load is very uniform. Consider more contrast between hard and easy days.",
            format!(
                "week_start={}, monotony={:.3}, strain={:.3}",
                latest.week_start, latest.monotony, latest.strain
            ),
        ));
    }

    if let Some(extra) = qualifying_alert(program, input, reference) {
        alerts.push(extra);
    }

    let severity = |item: &Alert| match item.severity {
        "warning" => 0,
        "caution" => 1,
        "info" => 2,
        _ => 99,
    };
    let source = |item: &Alert| match item.source {
        "fatigue" => 0,
        "acwr" => 1,
        "decoupling" => 2,
        "banister" => 3,
        "readiness" => 4,
        "specificity" => 5,
        "monotony" => 6,
        "projection" => 7,
        _ => 99,
    };
    alerts.sort_by_key(|item| (severity(item), source(item)));
    alerts
}

fn qualifying_alert(
    program: &ProgramData,
    input: &AlertInput<'_>,
    reference: NaiveDate,
) -> Option<Alert> {
    let mut upcoming: Vec<_> = program
        .competitions
        .iter()
        .filter(|competition| matches!(competition.status.as_str(), "confirmed" | "optional"))
        .filter(|competition| competition.date.is_some_and(|date| date > reference))
        .collect();
    upcoming.sort_by(|a, b| a.date_text.cmp(&b.date_text));
    let by_name: HashMap<&str, &Projection> = input
        .projections
        .iter()
        .filter_map(|entry| {
            Some((
                entry.comp_name.as_deref().filter(|name| !name.is_empty())?,
                &entry.projection,
            ))
        })
        .collect();
    for competition in upcoming {
        let Some(qualifying) = competition.qualifying_total() else {
            continue;
        };
        let projection = competition
            .name
            .as_deref()
            .and_then(|name| by_name.get(name).copied())
            .or_else(|| input.projections.first().map(|entry| &entry.projection));
        let Some(projection) = projection else {
            continue;
        };
        let projected = projection.total;
        if projected <= 0.0 {
            continue;
        }
        let weeks = projection.weeks_to_comp;
        let detail = format!(
            "projected_total={projected:.1}, qualifying_total={qualifying:.1}, weeks_to_comp={weeks:.1}"
        );
        if projected >= qualifying {
            return Some(alert(
                "info",
                "projection",
                "You're projected to exceed the qualifying total for this meet.",
                detail,
            ));
        }
        if weeks < 6.0 {
            return Some(alert(
                "caution",
                "projection",
                "Your projected total is below the meet's qualifying standard.",
                detail,
            ));
        }
    }
    None
}

pub fn rounded_maxes(raw: &Maxes) -> Maxes {
    Maxes {
        squat: raw.squat.map(|value| round(value, 1)),
        bench: raw.bench.map(|value| round(value, 1)),
        deadlift: raw.deadlift.map(|value| round(value, 1)),
    }
}
