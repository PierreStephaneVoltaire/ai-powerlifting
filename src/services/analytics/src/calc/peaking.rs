use std::collections::BTreeMap;

use chrono::{Duration, NaiveDate};
use serde::Serialize;
use serde_json::{Map, Value, json};

use super::banister::{self, Banister, BanisterPoint};
use super::fatigue::{self, FatigueWindow};
use super::weeks::{infer_program_start, week_start_for};
use super::{Computed, Dims, Env, Sessions, e1rm};
use crate::constants;
use crate::model::{Competition, Lift, Maxes, ProgramData, Session};
use crate::util::{
    clamp, int_of, median, num, num_of, ols_slope, parse_date, present, round, truthy_of,
};

const TAPER_WINDOW_WEEKS: f64 = 3.0;
const PRE_TAPER_WEEKS: i64 = 4;
const INTENSITY_RATIO_FLOOR: f64 = 0.95;
const FI_SLOPE_SCALE: f64 = 0.10;
const FI_DIFF_SCALE: f64 = 0.20;
const CTL_LAMBDA: f64 = 2.0 / 43.0;
const ATL_LAMBDA: f64 = 2.0 / 8.0;

#[derive(Debug, Clone, Copy, Serialize)]
pub struct Range {
    pub min: f64,
    pub max: f64,
}

#[derive(Debug, Clone, Copy)]
struct Band {
    label: &'static str,
    min_weeks: f64,
    max_weeks: Option<f64>,
    narrow: Range,
    broad: Range,
}

const BANDS: [Band; 5] = [
    Band {
        label: "16_plus",
        min_weeks: 16.0,
        max_weeks: None,
        narrow: Range {
            min: 0.30,
            max: 0.50,
        },
        broad: Range {
            min: 0.60,
            max: 0.75,
        },
    },
    Band {
        label: "12_to_16",
        min_weeks: 12.0,
        max_weeks: Some(16.0),
        narrow: Range {
            min: 0.40,
            max: 0.55,
        },
        broad: Range {
            min: 0.65,
            max: 0.80,
        },
    },
    Band {
        label: "8_to_12",
        min_weeks: 8.0,
        max_weeks: Some(12.0),
        narrow: Range {
            min: 0.50,
            max: 0.65,
        },
        broad: Range {
            min: 0.75,
            max: 0.85,
        },
    },
    Band {
        label: "4_to_8",
        min_weeks: 4.0,
        max_weeks: Some(8.0),
        narrow: Range {
            min: 0.60,
            max: 0.75,
        },
        broad: Range {
            min: 0.80,
            max: 0.90,
        },
    },
    Band {
        label: "0_to_4",
        min_weeks: 0.0,
        max_weeks: Some(4.0),
        narrow: Range {
            min: 0.70,
            max: 0.85,
        },
        broad: Range {
            min: 0.85,
            max: 0.95,
        },
    },
];

fn expected_band(weeks_to_comp: Option<f64>) -> Option<Band> {
    let weeks = weeks_to_comp.filter(|weeks| *weeks >= 0.0)?;
    BANDS
        .iter()
        .find(|band| weeks >= band.min_weeks && band.max_weeks.is_none_or(|max| weeks < max))
        .copied()
}

#[derive(Debug, Clone, Serialize)]
pub struct ExpectedBand {
    pub weeks_to_comp: f64,
    pub narrow: Range,
    pub broad: Range,
}

#[derive(Debug, Serialize)]
pub struct Specificity {
    pub narrow: f64,
    pub broad: f64,
    pub total_sets: i64,
    pub sbd_sets: i64,
    pub secondary_sets: i64,
    pub expected_band: Option<ExpectedBand>,
    pub narrow_status: &'static str,
    pub broad_status: &'static str,
    pub flags: Vec<&'static str>,
}

pub fn specificity_ratio(
    env: Env<'_>,
    sessions: Sessions<'_>,
    weeks_to_comp: Option<f64>,
) -> Computed<Specificity> {
    let (mut total, mut sbd, mut secondary) = (0i64, 0i64, 0i64);
    for session in sessions.iter().filter(|session| session.completed) {
        for exercise in &session.exercises {
            let sets = exercise.sets_int();
            if sets <= 0 {
                continue;
            }
            total += sets;
            if matches!(
                exercise.key.as_str(),
                "squat" | "bench press" | "bench" | "deadlift"
            ) {
                sbd += sets;
            } else if !env.glossary.is_empty()
                && matches!(
                    env.glossary.category(&exercise.key),
                    "squat" | "bench" | "deadlift"
                )
            {
                secondary += sets;
            }
        }
    }
    if total == 0 {
        return Computed::insufficient("No working sets for specificity ratio");
    }
    let narrow = round(sbd as f64 / total as f64, 3);
    let broad = round((sbd + secondary) as f64 / total as f64, 3);
    let band = expected_band(weeks_to_comp);
    let mut flags = Vec::new();
    let (mut narrow_status, mut broad_status) = ("unknown", "unknown");
    if let Some(band) = band {
        narrow_status = if narrow < band.narrow.min {
            flags.push("specificity_below_expected");
            "below_expected"
        } else if narrow > band.narrow.max {
            flags.push("specificity_above_expected");
            "above_expected"
        } else {
            "within_expected"
        };
        broad_status = if broad < band.broad.min {
            "below_expected"
        } else if broad > band.broad.max {
            "above_expected"
        } else {
            "within_expected"
        };
    }
    Computed::Ready(Specificity {
        narrow,
        broad,
        total_sets: total,
        sbd_sets: sbd,
        secondary_sets: secondary,
        expected_band: band.zip(weeks_to_comp).map(|(band, weeks)| ExpectedBand {
            weeks_to_comp: round(weeks, 1),
            narrow: band.narrow,
            broad: band.broad,
        }),
        narrow_status,
        broad_status,
        flags,
    })
}

pub fn target_competition(program: &ProgramData, reference: NaiveDate) -> Option<Value> {
    let mut upcoming: Vec<&Competition> = program
        .competitions
        .iter()
        .filter(|competition| matches!(competition.status.as_str(), "confirmed" | "optional"))
        .filter(|competition| competition.date.is_some_and(|date| date > reference))
        .collect();
    upcoming.sort_by(|a, b| a.date_text.cmp(&b.date_text));
    let selected = upcoming
        .iter()
        .find(|competition| {
            let notes = competition.notes.to_lowercase();
            notes.contains("qualifier") || notes.contains("primary")
        })
        .map(|competition| (*competition, "competition_notes"))
        .or_else(|| {
            upcoming
                .first()
                .map(|competition| (*competition, "nearest_confirmed"))
        })?;
    let mut value = selected.0.raw.clone();
    if let Value::Object(map) = &mut value {
        map.insert("selection_reason".to_owned(), json!(selected.1));
    }
    Some(value)
}

fn max_intensity_between(
    sessions: Sessions<'_>,
    from: NaiveDate,
    to: NaiveDate,
    maxes: &Maxes,
) -> Option<f64> {
    let mut best = 0.0_f64;
    for session in sessions.iter().filter(|session| session.completed) {
        if session.date.is_none_or(|date| date < from || date > to) {
            continue;
        }
        for exercise in &session.exercises {
            let Some(lift) = Lift::from_name(&exercise.key) else {
                continue;
            };
            let max = maxes.get(lift).unwrap_or(0.0);
            if max <= 0.0 || exercise.kg <= 0.0 {
                continue;
            }
            best = best.max(exercise.kg / max);
        }
    }
    (best > 0.0).then_some(best)
}

fn window_sum(series: &[banister::DailyLoad], from: NaiveDate, to: NaiveDate) -> f64 {
    series
        .iter()
        .filter(|row| from <= row.date && row.date <= to)
        .map(|row| row.load)
        .sum()
}

fn taper_start(
    program: &ProgramData,
    comp: NaiveDate,
    reference: Option<NaiveDate>,
    program_start: &str,
) -> Option<NaiveDate> {
    let configured = program.meta.program_start();
    let basis = if configured.is_empty() {
        program_start
    } else {
        configured.as_str()
    };
    let resolved = parse_date(basis).or(reference)?;
    let mut phases: Vec<&crate::model::Phase> = program.phases.iter().collect();
    phases.sort_by_key(|phase| int_of(phase.start_week));
    let named = phases.into_iter().find_map(|phase| {
        let start_week = int_of(phase.start_week);
        (phase.text().contains("taper") && start_week > 0)
            .then(|| resolved + Duration::weeks(start_week - 1))
    });
    let window_start = comp - Duration::days(21);
    Some(named.map_or(window_start, |named| named.min(window_start)))
}

#[derive(Debug, Serialize)]
pub struct TaperComponents {
    pub volume_reduction: f64,
    pub intensity_maintained: f64,
    pub fatigue_trend: f64,
    pub tsb: f64,
}

#[derive(Debug, Serialize)]
pub struct Taper {
    pub score: f64,
    pub label: &'static str,
    pub weeks_to_comp: f64,
    pub components: TaperComponents,
}

pub fn taper_quality(
    env: Env<'_>,
    program: &ProgramData,
    sessions: Sessions<'_>,
    maxes: &Maxes,
    program_start: &str,
    reference: Option<NaiveDate>,
) -> Option<Computed<Taper>> {
    let estimated;
    let maxes = if maxes.is_empty() {
        estimated = e1rm::from_sessions_default(sessions, env.today);
        &estimated
    } else {
        maxes
    };
    let reference = reference.unwrap_or(env.today);
    let resolved = if program_start.is_empty() {
        infer_program_start(sessions)
    } else {
        program_start.to_owned()
    };
    let competitions: Vec<&Competition> = program.competitions.iter().collect();
    let upcoming = super::readiness::next_competition(&competitions, reference)?;
    let Some(comp) = upcoming.date else {
        return Some(Computed::insufficient(
            "Invalid competition date for taper quality",
        ));
    };
    let weeks_to_comp = (comp - reference).num_days() as f64 / 7.0;
    if weeks_to_comp > TAPER_WINDOW_WEEKS || weeks_to_comp <= 0.0 {
        return None;
    }
    let (series, _) =
        banister::composite_daily_loads(env, sessions, &resolved, maxes, Some(reference));
    let Some(first) = series.first() else {
        return Some(Computed::insufficient(
            "No completed training load available for taper quality",
        ));
    };
    let Some(mut start) = taper_start(
        program,
        comp,
        parse_date(&resolved).or(Some(first.date)),
        &resolved,
    ) else {
        return Some(Computed::insufficient("Could not determine taper start"));
    };
    if start > reference {
        start = reference - Duration::days(1);
    }
    let pre_windows: Vec<(NaiveDate, NaiveDate)> = (1..=PRE_TAPER_WEEKS)
        .rev()
        .map(|index| {
            let end = start - Duration::days(7 * (index - 1) + 1);
            (end - Duration::days(6), end)
        })
        .collect();
    let mut taper_windows: Vec<(NaiveDate, NaiveDate)> = Vec::new();
    let mut cursor = start;
    while cursor <= reference {
        let end = std::cmp::min(cursor + Duration::days(6), reference);
        taper_windows.push((cursor, end));
        cursor = end + Duration::days(1);
    }
    if taper_windows.is_empty() {
        return Some(Computed::insufficient("No taper-period sessions available"));
    }
    let weekly_volume = |(from, to): &(NaiveDate, NaiveDate)| {
        let days = ((*to - *from).num_days() + 1).max(1) as f64;
        window_sum(&series, *from, *to) * 7.0 / days
    };
    let pre_peak = pre_windows
        .iter()
        .map(weekly_volume)
        .fold(0.0_f64, f64::max);
    if pre_peak <= 0.0 {
        return Some(Computed::insufficient(
            "No pre-taper volume baseline available",
        ));
    }
    let taper_volumes: Vec<f64> = taper_windows.iter().map(weekly_volume).collect();
    let taper_weekly = taper_volumes.iter().sum::<f64>() / taper_volumes.len() as f64;
    let volume_reduction = clamp((pre_peak - taper_weekly) / (pre_peak * 0.5), 0.0, 1.0);
    let peak_intensity = |windows: &[(NaiveDate, NaiveDate)]| {
        windows
            .iter()
            .filter_map(|(from, to)| max_intensity_between(sessions, *from, *to, maxes))
            .fold(0.0_f64, f64::max)
    };
    let pre_intensity = peak_intensity(&pre_windows);
    let taper_intensity = peak_intensity(&taper_windows);
    if pre_intensity <= 0.0 || taper_intensity <= 0.0 {
        return Some(Computed::insufficient(
            "No taper intensity baseline available",
        ));
    }
    let intensity_maintained = if taper_intensity >= pre_intensity * INTENSITY_RATIO_FLOOR {
        1.0
    } else {
        clamp(
            taper_intensity / (pre_intensity * INTENSITY_RATIO_FLOOR),
            0.0,
            1.0,
        )
    };
    let scores = |windows: &[(NaiveDate, NaiveDate)]| -> Vec<f64> {
        windows
            .iter()
            .filter_map(|(_, end)| {
                fatigue::fatigue_index(
                    env,
                    sessions,
                    FatigueWindow {
                        days: 14,
                        reference: Some(*end),
                        ..Default::default()
                    },
                    maxes,
                    &resolved,
                )
                .ready()
                .map(|result| result.score)
            })
            .collect()
    };
    let pre_fi = scores(&pre_windows);
    let taper_fi = scores(&taper_windows);
    if taper_fi.is_empty() {
        return Some(Computed::insufficient("No taper fatigue data available"));
    }
    let fatigue_trend = if taper_fi.len() >= 2 {
        let xs: Vec<f64> = (0..taper_fi.len()).map(|index| index as f64).collect();
        clamp(-ols_slope(&xs, &taper_fi) / FI_SLOPE_SCALE, -1.0, 1.0)
    } else {
        let baseline = if pre_fi.is_empty() {
            taper_fi[0]
        } else {
            median(&pre_fi)
        };
        clamp(
            (baseline - taper_fi[taper_fi.len() - 1]) / FI_DIFF_SCALE,
            -1.0,
            1.0,
        )
    };
    let banister = match banister::banister_ffm(env, sessions, &resolved, maxes, Some(reference)) {
        Computed::Ready(banister) => banister,
        Computed::Insufficient(insufficient) => return Some(Computed::Insufficient(insufficient)),
    };
    let tsb = clamp((banister.tsb_today + 5.0) / 20.0, 0.0, 1.0);
    let score = clamp(
        0.30 * volume_reduction + 0.25 * intensity_maintained + 0.25 * fatigue_trend + 0.20 * tsb,
        0.0,
        1.0,
    );
    let score_pct = round(score * 100.0, 1);
    let label = if score_pct < 40.0 {
        "poor"
    } else if score_pct < 60.0 {
        "acceptable"
    } else if score_pct < 80.0 {
        "good"
    } else {
        "excellent"
    };
    Some(Computed::Ready(Taper {
        score: score_pct,
        label,
        weeks_to_comp: round(weeks_to_comp, 3),
        components: TaperComponents {
            volume_reduction: round(volume_reduction, 3),
            intensity_maintained: round(intensity_maintained, 3),
            fatigue_trend: round(fatigue_trend, 3),
            tsb: round(tsb, 3),
        },
    }))
}

fn chain<'a>(map: &'a Map<String, Value>, keys: &[&str]) -> Option<&'a Value> {
    let mut last = None;
    for key in keys {
        let value = map.get(*key);
        if truthy_of(value) {
            return value;
        }
        last = value;
    }
    last
}

fn planned_weight(exercise: &Map<String, Value>, maxes: &Maxes) -> Option<f64> {
    let load_type = chain(exercise, &["load_type", "loadSource", "load_source"])
        .filter(|value| truthy_of(Some(*value)))
        .map(|value| {
            value
                .as_str()
                .map_or_else(|| value.to_string(), str::to_owned)
        })
        .unwrap_or_default()
        .to_lowercase()
        .trim()
        .to_owned();
    let kg_value = exercise.get("kg").or_else(|| exercise.get("load_value"));
    let kg = num_of(kg_value);
    if kg > 0.0 && matches!(load_type.as_str(), "" | "absolute" | "kg") {
        return Some(round(kg, 3));
    }
    let name = exercise
        .get("name")
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_lowercase();
    let lift = Lift::from_name(name.trim())?;
    let max = maxes.get(lift).unwrap_or(0.0);
    if max <= 0.0 {
        return None;
    }
    let mut percent = chain(exercise, &["percent", "percentage", "pct"]);
    if percent.is_none() && matches!(load_type.as_str(), "percent" | "percentage" | "pct") {
        percent = exercise.get("load_value");
    }
    if let Some(percent) = percent {
        let mut value = num(percent);
        if value > 1.5 {
            value /= 100.0;
        }
        if value > 0.0 && value <= 1.2 {
            return Some(round(max * value, 3));
        }
    }
    let mut rpe = chain(exercise, &["rpe_target", "rpe"]);
    if rpe.is_none() && load_type == "rpe" {
        rpe = exercise.get("load_value");
    }
    let rpe = rpe?;
    let reps = int_of(num_of(exercise.get("reps")));
    let rpe_int = int_of(num(rpe));
    if (1..=10).contains(&reps) && (6..=10).contains(&rpe_int) {
        return constants::rpe_percent(reps, rpe_int).map(|pct| round(max * pct, 3));
    }
    None
}

fn future_planned(
    env: Env<'_>,
    sessions: Sessions<'_>,
    maxes: &Maxes,
    reference: NaiveDate,
    end: NaiveDate,
) -> (BTreeMap<NaiveDate, Dims>, i64) {
    let mut daily: BTreeMap<NaiveDate, Dims> = BTreeMap::new();
    let mut unresolved = 0;
    for session in sessions {
        let Some(date) = session
            .date
            .filter(|date| *date > reference && *date <= end)
        else {
            continue;
        };
        let planned = if session.planned_exercises().is_empty() {
            session.exercise_values()
        } else {
            session.planned_exercises()
        };
        if planned.is_empty() {
            continue;
        }
        let day = daily.entry(date).or_default();
        for item in planned.iter().filter_map(Value::as_object) {
            let sets = int_of(num_of(item.get("sets")));
            let reps = int_of(num_of(item.get("reps")));
            if sets <= 0 || reps <= 0 {
                continue;
            }
            let Some(weight) = planned_weight(item, maxes).filter(|weight| *weight > 0.0) else {
                unresolved += sets;
                continue;
            };
            let name = item.get("name").and_then(Value::as_str).unwrap_or_default();
            let key = name.to_lowercase();
            let key = key.trim();
            let profile = fatigue::profile_for(env, key);
            let max = Lift::from_name(key)
                .and_then(|lift| maxes.get(lift))
                .unwrap_or(0.0);
            let mut rpe = chain(item, &["rpe_target", "rpe"]);
            if rpe.is_none()
                && item
                    .get("load_type")
                    .and_then(Value::as_str)
                    .is_some_and(|kind| kind.to_lowercase().trim() == "rpe")
            {
                rpe = item.get("load_value");
            }
            let rpe = present(rpe).map(num);
            let intensity = if max > 0.0 {
                1.0_f64.min(weight / max)
            } else {
                fatigue::resolve_intensity(env, &name.to_lowercase(), weight, reps, rpe, maxes)
            };
            day.add(
                fatigue::per_set(weight, reps, profile, intensity, rpe),
                sets as f64,
            );
        }
    }
    (daily, unresolved)
}

#[derive(Debug, Serialize)]
pub struct TimelinePoint {
    pub date: String,
    pub actual_tsb: Option<f64>,
    pub projected_tsb: Option<f64>,
}

#[derive(Debug, Serialize)]
pub struct SpecificityPoint {
    pub date: String,
    pub narrow: f64,
    pub broad: f64,
    pub weeks_to_comp: f64,
    pub expected_band: Option<ExpectedBand>,
}

#[derive(Debug, Serialize)]
pub struct BandSegment {
    pub label: &'static str,
    pub start_date: String,
    pub end_date: String,
    pub narrow: Range,
    pub broad: Range,
}

#[derive(Debug, Serialize)]
pub struct PeakWindow {
    pub min: f64,
    pub max: f64,
}

const PEAK_WINDOW: PeakWindow = PeakWindow {
    min: 5.0,
    max: 15.0,
};

#[derive(Debug, Serialize)]
pub struct TimelineStub {
    pub status: &'static str,
    pub reason: &'static str,
    pub status_color: &'static str,
    pub status_label: &'static str,
    pub status_message: &'static str,
    pub comp_date: Option<String>,
    pub current_date: String,
    pub current_tsb: Option<f64>,
    pub peak_date: Option<String>,
    pub peak_delta_days: Option<i64>,
    pub peak_window: PeakWindow,
    pub series: Vec<TimelinePoint>,
    pub specificity_points: Vec<SpecificityPoint>,
    pub specificity_bands: Vec<BandSegment>,
}

#[derive(Debug, Serialize)]
pub struct TimelineFull {
    pub status: &'static str,
    pub status_color: &'static str,
    pub status_label: &'static str,
    pub status_message: String,
    pub comp_date: String,
    pub current_date: String,
    pub current_tsb: f64,
    pub peak_date: Option<String>,
    pub peak_delta_days: Option<i64>,
    pub peak_type: &'static str,
    pub closest_peak_date: Option<String>,
    pub closest_projected_tsb: Option<f64>,
    pub future_unresolved_sets: i64,
    pub peak_window: PeakWindow,
    pub series: Vec<TimelinePoint>,
    pub specificity_points: Vec<SpecificityPoint>,
    pub specificity_bands: Vec<BandSegment>,
}

#[derive(Debug, Serialize)]
#[serde(untagged)]
pub enum Timeline {
    Stub(TimelineStub),
    Full(TimelineFull),
}

fn stub(
    reason: &'static str,
    label: &'static str,
    message: &'static str,
    comp_date: Option<String>,
    reference: NaiveDate,
) -> Timeline {
    Timeline::Stub(TimelineStub {
        status: "insufficient_data",
        reason,
        status_color: "gray",
        status_label: label,
        status_message: message,
        comp_date,
        current_date: reference.to_string(),
        current_tsb: None,
        peak_date: None,
        peak_delta_days: None,
        peak_window: PEAK_WINDOW,
        series: Vec::new(),
        specificity_points: Vec::new(),
        specificity_bands: Vec::new(),
    })
}

fn band_segments(program_start: &str, comp: NaiveDate) -> Vec<BandSegment> {
    let Some(start) = parse_date(program_start) else {
        return Vec::new();
    };
    BANDS
        .iter()
        .filter_map(|band| {
            let seg_start = match band.max_weeks {
                None => start,
                Some(max) => start.max(comp - Duration::weeks(max as i64)),
            };
            let seg_end = if band.min_weeks == 0.0 {
                comp
            } else {
                comp - Duration::weeks(band.min_weeks as i64)
            };
            (seg_start <= seg_end).then(|| BandSegment {
                label: band.label,
                start_date: seg_start.to_string(),
                end_date: seg_end.to_string(),
                narrow: band.narrow,
                broad: band.broad,
            })
        })
        .collect()
}

fn specificity_points(
    env: Env<'_>,
    sessions: Sessions<'_>,
    program_start: &str,
    comp: NaiveDate,
    reference: NaiveDate,
) -> Vec<SpecificityPoint> {
    let start = parse_date(program_start);
    let mut weeks: BTreeMap<NaiveDate, Vec<&Session>> = BTreeMap::new();
    for session in sessions.iter().filter(|session| session.completed) {
        let Some(date) = session.date.filter(|date| *date <= reference) else {
            continue;
        };
        let key = start.map_or(date, |start| week_start_for(date, start));
        weeks.entry(key).or_default().push(session);
    }
    weeks
        .values()
        .filter_map(|members| {
            let end = members.iter().filter_map(|session| session.date).max()?;
            let weeks_to_comp = (comp - end).num_days() as f64 / 7.0;
            let ratio = specificity_ratio(env, members, Some(weeks_to_comp)).into_ready()?;
            let band = expected_band(Some(weeks_to_comp));
            Some(SpecificityPoint {
                date: end.to_string(),
                narrow: ratio.narrow,
                broad: ratio.broad,
                weeks_to_comp: round(weeks_to_comp, 1),
                expected_band: band.map(|band| ExpectedBand {
                    weeks_to_comp: round(weeks_to_comp, 1),
                    narrow: band.narrow,
                    broad: band.broad,
                }),
            })
        })
        .collect()
}

pub fn timeline(
    env: Env<'_>,
    program: &ProgramData,
    sessions: Sessions<'_>,
    reference: NaiveDate,
    banister: Option<&Banister>,
    maxes: &Maxes,
) -> Timeline {
    let program_start = program.meta.program_start();
    let mut upcoming: Vec<&Competition> = program
        .competitions
        .iter()
        .filter(|competition| matches!(competition.status.as_str(), "confirmed" | "optional"))
        .filter(|competition| competition.date.is_some_and(|date| date > reference))
        .collect();
    upcoming.sort_by(|a, b| a.date_text.cmp(&b.date_text));
    let Some(competition) = upcoming.first() else {
        return stub(
            "No upcoming competition date set",
            "No upcoming competition",
            "Set a competition date to view the peaking timeline.",
            None,
            reference,
        );
    };
    let Some(comp) = competition.date.filter(|date| *date > reference) else {
        return stub(
            "Competition date is in the past or invalid",
            "No upcoming competition",
            "Set a future competition date to view the peaking timeline.",
            Some(competition.date_text.clone()),
            reference,
        );
    };
    let comp_text = competition.date_text.clone();
    let Some(banister) = banister.filter(|banister| !banister.series.is_empty()) else {
        return stub(
            "No Banister data available",
            "No Banister data",
            "Need Banister data to project the peaking timeline.",
            Some(comp_text),
            reference,
        );
    };
    let current = banister
        .series
        .iter()
        .find(|row| parse_date(&row.date) == Some(reference));
    let Some(current) = current else {
        return stub(
            "No Banister point found for the reference date",
            "No Banister data",
            "Need a current Banister point to project the peaking timeline.",
            Some(comp_text),
            reference,
        );
    };
    let horizon = comp + Duration::days(14);
    let (future, unresolved) = future_planned(env, sessions, maxes, reference, horizon);
    let mut series: Vec<TimelinePoint> = banister
        .series
        .iter()
        .filter_map(|row: &BanisterPoint| {
            let date = parse_date(&row.date).filter(|date| *date <= horizon)?;
            Some(TimelinePoint {
                date: date.to_string(),
                actual_tsb: (date <= reference).then(|| round(row.tsb, 3)),
                projected_tsb: (date == reference).then(|| round(row.tsb, 3)),
            })
        })
        .collect();
    let (mut ctl, mut atl) = (current.ctl, current.atl);
    let baselines = banister.load_baselines;
    let mut day = reference + Duration::days(1);
    while day <= horizon {
        let dims = future.get(&day).copied().unwrap_or_default();
        let load = banister::normalized_load(dims, baselines);
        ctl = CTL_LAMBDA * load + (1.0 - CTL_LAMBDA) * ctl;
        atl = ATL_LAMBDA * load + (1.0 - ATL_LAMBDA) * atl;
        series.push(TimelinePoint {
            date: day.to_string(),
            actual_tsb: None,
            projected_tsb: Some(round(ctl - atl, 3)),
        });
        day += Duration::days(1);
    }
    let peak = series.iter().find(|point| {
        point
            .projected_tsb
            .is_some_and(|tsb| (5.0..=15.0).contains(&tsb))
    });
    let peak_date = peak.and_then(|point| parse_date(&point.date));
    let peak_delta = peak_date.map(|date| (comp - date).num_days());
    let closest = series
        .iter()
        .filter_map(|point| Some((point, point.projected_tsb?)))
        .fold(
            None::<(&TimelinePoint, f64)>,
            |best, candidate| match best {
                Some(best) if (best.1 - 10.0).abs() <= (candidate.1 - 10.0).abs() => Some(best),
                _ => Some(candidate),
            },
        );
    let (status, color, label, message) = match peak_delta {
        None => (
            "significant_deviation",
            "red",
            "Significant deviation",
            "Projected TSB never reaches the peaking window.".to_owned(),
        ),
        Some(delta) if delta.abs() <= 3 => (
            "on_track",
            "green",
            "On track",
            "On track - peak window lands within \u{b1}3 days of comp.".to_owned(),
        ),
        Some(delta) if delta.abs() <= 10 => (
            "misaligned",
            "yellow",
            "Peak misaligned",
            format!(
                "Peak misaligned - currently projected to peak {} days {}.",
                delta.abs(),
                if delta > 0 { "early" } else { "late" }
            ),
        ),
        Some(delta) => (
            "significant_deviation",
            "red",
            "Significant deviation",
            format!(
                "Significant deviation - projected to peak {} days {}.",
                delta.abs(),
                if delta > 0 { "early" } else { "late" }
            ),
        ),
    };
    Timeline::Full(TimelineFull {
        status,
        status_color: color,
        status_label: label,
        status_message: message,
        comp_date: comp_text,
        current_date: reference.to_string(),
        current_tsb: round(current.tsb, 3),
        peak_date: peak_date.map(|date| date.to_string()),
        peak_delta_days: peak_delta,
        peak_type: if peak_date.is_some() {
            "inside_window"
        } else {
            "not_reached"
        },
        closest_peak_date: closest
            .and_then(|(point, _)| parse_date(&point.date))
            .map(|date| date.to_string()),
        closest_projected_tsb: closest.map(|(_, tsb)| round(tsb, 3)),
        future_unresolved_sets: unresolved,
        peak_window: PEAK_WINDOW,
        series,
        specificity_points: specificity_points(env, sessions, &program_start, comp, reference),
        specificity_bands: band_segments(&program_start, comp),
    })
}
