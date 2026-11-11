use super::format::{grouped, number, optional, plural};
use super::types::{ExerciseRoi, Finding, Pattern, Row, TrainingDays, TrendPoint};

fn pattern(kind: &str, finding: String, evidence: String, confidence: &str) -> Pattern {
    Pattern {
        kind: kind.to_owned(),
        finding,
        evidence,
        confidence: confidence.to_owned(),
    }
}

fn first_extreme<'a, T>(items: &[&'a T], key: impl Fn(&T) -> f64, highest: bool) -> Option<&'a T> {
    let mut chosen: Option<&'a T> = None;
    for item in items {
        let better = match chosen {
            None => true,
            Some(current) => {
                if highest {
                    key(item) > key(current)
                } else {
                    key(item) < key(current)
                }
            }
        };
        if better {
            chosen = Some(item);
        }
    }
    chosen
}

pub fn build(
    rows: &[Row],
    roi: &[ExerciseRoi],
    findings: &[Finding],
    days: &[TrainingDays],
    series: &[TrendPoint],
) -> Vec<Pattern> {
    let mut patterns = Vec::new();
    if let Some(top) = roi.first() {
        patterns.push(pattern(
            "roi",
            format!(
                "{} has the strongest consolidated exercise ROI signal in the source data.",
                top.exercise
            ),
            top.summary.clone(),
            &top.confidence,
        ));
    }
    if let Some(repeated) = roi
        .iter()
        .find(|row| row.block_count >= 2 && row.positive_signals >= 2)
    {
        let lifts = if repeated.correlated_lifts.is_empty() {
            "not specified".to_owned()
        } else {
            repeated.correlated_lifts.join(", ")
        };
        patterns.push(pattern(
            "roi",
            format!(
                "{} has repeated positive transfer signals across source blocks.",
                repeated.exercise
            ),
            format!(
                "{} positive correlation findings across {} blocks; lifts: {lifts}.",
                repeated.positive_signals, repeated.block_count
            ),
            &repeated.confidence,
        ));
    }
    let completed: Vec<&Row> = rows.iter().filter(|row| row.e1rm_delta_kg.is_some()).collect();
    if completed.len() >= 2 {
        let delta = |row: &Row| row.e1rm_delta_kg.unwrap_or(f64::NEG_INFINITY);
        let worst_delta = |row: &Row| row.e1rm_delta_kg.unwrap_or(f64::INFINITY);
        let best = first_extreme(&completed, delta, true);
        let worst = first_extreme(&completed, worst_delta, false);
        if let Some((best, worst)) = best.zip(worst)
            && best.block_key != worst.block_key
        {
            patterns.push(pattern(
                "training_response",
                format!("{} had the strongest total response among source blocks.", best.label),
                format!(
                    "{}: {} kg total delta, {} compliance, {} kg volume. {}: {} kg total delta.",
                    best.label,
                    optional(best.e1rm_delta_kg, "null"),
                    optional(best.compliance_pct, "unknown"),
                    grouped(best.total_volume_kg),
                    worst.label,
                    optional(worst.e1rm_delta_kg, "null"),
                ),
                if rows.len() >= 3 { "medium" } else { "low" },
            ));
        }
    }
    let with_compliance: Vec<&Row> = rows
        .iter()
        .filter(|row| row.compliance_pct.is_some() && row.e1rm_delta_kg.is_some())
        .collect();
    if with_compliance.len() >= 2 {
        let value = |row: &Row| row.compliance_pct.unwrap_or(0.0);
        let high = first_extreme(&with_compliance, value, true);
        let low = first_extreme(&with_compliance, value, false);
        if let Some((high, low)) = high.zip(low)
            && high.block_key != low.block_key
        {
            patterns.push(pattern(
                "compliance",
                "Compliance is a major confound in the lifetime comparison.".to_owned(),
                format!(
                    "{}: {:.1}% compliance and {} kg total delta. {}: {:.1}% compliance and {} kg total delta.",
                    high.label,
                    high.compliance_pct.unwrap_or(0.0),
                    optional(high.e1rm_delta_kg, "null"),
                    low.label,
                    low.compliance_pct.unwrap_or(0.0),
                    optional(low.e1rm_delta_kg, "null"),
                ),
                "medium",
            ));
        }
    }
    let cached: Vec<&str> = findings.iter().map(|f| f.block_key.as_str()).collect();
    let missing: Vec<&str> = rows
        .iter()
        .filter(|row| !cached.contains(&row.block_key.as_str()))
        .map(|row| row.label.as_str())
        .collect();
    if !missing.is_empty() {
        patterns.push(pattern(
            "data_quality",
            "Some selected blocks do not have ROI correlation reports.".to_owned(),
            format!(
                "Missing correlation data for: {}. Exercise ROI still uses block exercise stats, but pattern confidence is lower without correlation findings.",
                missing.join(", ")
            ),
            "high",
        ));
    }
    let day_rows: Vec<&TrainingDays> = days
        .iter()
        .filter(|row| row.avg_training_days_per_week.is_some() && row.strength_delta_kg.is_some())
        .collect();
    if day_rows.len() >= 2 {
        let value = |row: &TrainingDays| row.avg_training_days_per_week.unwrap_or(0.0);
        let high = first_extreme(&day_rows, value, true);
        let low = first_extreme(&day_rows, value, false);
        if let Some((high, low)) = high.zip(low)
            && high.block_key != low.block_key
        {
            patterns.push(pattern(
                "training_response",
                "Average training days per week differs across selected source blocks.".to_owned(),
                format!(
                    "{}: {} days/week and {} kg total delta. {}: {} days/week and {} kg total delta.",
                    high.label,
                    optional(high.avg_training_days_per_week, "null"),
                    optional(high.strength_delta_kg, "null"),
                    low.label,
                    optional(low.avg_training_days_per_week, "null"),
                    optional(low.strength_delta_kg, "null"),
                ),
                if day_rows.len() >= 3 { "medium" } else { "low" },
            ));
        }
    }
    for row in rows {
        let mut points: Vec<&TrendPoint> = series
            .iter()
            .filter(|point| point.block_key == row.block_key)
            .collect();
        points.sort_by_key(|point| point.week_number);
        let Some(first_zero) = points
            .iter()
            .enumerate()
            .position(|(index, point)| {
                index > 0 && point.training_days == 0 && points[index - 1].training_days > 0
            })
        else {
            continue;
        };
        let run = points[first_zero..]
            .iter()
            .position(|point| point.training_days > 0);
        let zero_weeks = run.unwrap_or(points.len() - first_zero) as i64;
        if zero_weeks >= 2 {
            patterns.push(pattern(
                "training_response",
                format!(
                    "{} has a training-day dropoff in the block-to-date series.",
                    row.label
                ),
                format!(
                    "Training days fell to 0 starting W{} ({}) for {} consecutive week{} in the selected source data.",
                    points[first_zero].week_number,
                    points[first_zero].week_start,
                    number(zero_weeks as f64),
                    plural(zero_weeks),
                ),
                "high",
            ));
        }
    }
    patterns
}
