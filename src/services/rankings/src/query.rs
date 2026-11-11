use std::path::Path;
use std::time::{SystemTime, UNIX_EPOCH};

use polars::prelude::*;

pub const METRIC_COLUMNS: [&str; 5] = [
    "Best3SquatKg",
    "Best3BenchKg",
    "Best3DeadliftKg",
    "TotalKg",
    "Dots",
];

pub fn scan(parquet: &Path) -> PolarsResult<LazyFrame> {
    LazyFrame::scan_parquet(
        PlRefPath::try_from_path(parquet)?,
        ScanArgsParquet::default(),
    )
}

pub fn collect(frame: LazyFrame) -> PolarsResult<DataFrame> {
    frame.collect_with_engine(Engine::Streaming)
}

pub fn current_year() -> i32 {
    let days = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_or(0, |elapsed| (elapsed.as_secs() / 86_400) as i64);
    let shifted = days + 719_468;
    let era = shifted.div_euclid(146_097);
    let day_of_era = shifted.rem_euclid(146_097);
    let year_of_era =
        (day_of_era - day_of_era / 1_460 + day_of_era / 36_524 - day_of_era / 146_096) / 365;
    let day_of_year = day_of_era - (365 * year_of_era + year_of_era / 4 - year_of_era / 100);
    let month_shifted = (5 * day_of_year + 2) / 153;
    let year = year_of_era + era * 400 + i64::from(month_shifted >= 10);
    year as i32
}

pub struct Ranking {
    pub band: Option<(f64, f64)>,
    pub sex: Option<String>,
    pub age_class: Option<String>,
    pub equipment: Option<String>,
    pub years: (i32, i32),
}

pub fn ranking_frame(parquet: &Path, ranking: &Ranking) -> PolarsResult<DataFrame> {
    let mut predicate = col("Event")
        .eq(lit("SBD"))
        .and(col("Year").gt_eq(lit(ranking.years.0 as f32)))
        .and(col("Year").lt_eq(lit(ranking.years.1 as f32)));
    if let Some((lower, upper)) = ranking.band {
        predicate = predicate
            .and(col("BodyweightKg").gt(lit(lower as f32)))
            .and(col("BodyweightKg").lt_eq(lit(upper as f32)));
    }
    predicate = equals(predicate, "Sex", ranking.sex.as_deref());
    predicate = equals(predicate, "AgeClass", ranking.age_class.as_deref());
    predicate = equals(predicate, "Equipment", ranking.equipment.as_deref());
    let ordering = SortMultipleOptions::default()
        .with_order_descending(true)
        .with_nulls_last(true)
        .with_maintain_order(true);
    collect(
        scan(parquet)?
            .filter(predicate)
            .select([
                col("Name"),
                col("MeetCountry"),
                col("State"),
                col("Best3SquatKg"),
                col("Best3BenchKg"),
                col("Best3DeadliftKg"),
                col("TotalKg"),
            ])
            .sort(["TotalKg"], ordering)
            .unique_stable(Some(cols(["Name"])), UniqueKeepStrategy::First),
    )
}

pub fn within(frame: DataFrame, column: &str, wanted: &str) -> PolarsResult<DataFrame> {
    frame
        .lazy()
        .filter(
            col(column)
                .str()
                .to_lowercase()
                .eq(lit(wanted.trim().to_lowercase())),
        )
        .collect()
}

pub struct Filters {
    pub federation: Option<String>,
    pub country: Option<String>,
    pub region: Option<String>,
    pub equipment: Option<String>,
    pub sex: Option<String>,
    pub age_class: Option<String>,
    pub year: Option<f64>,
    pub event_type: Option<String>,
    pub min_dots: Option<f64>,
}

impl Filters {
    fn predicate(&self) -> Expr {
        let mut predicate = lit(true);
        predicate = equals(predicate, "Federation", self.federation.as_deref());
        predicate = equals(predicate, "Equipment", self.equipment.as_deref());
        predicate = equals(predicate, "Sex", self.sex.as_deref());
        predicate = equals(predicate, "AgeClass", self.age_class.as_deref());
        predicate = equals(predicate, "Event", self.event_type.as_deref());
        predicate = folded(predicate, "MeetCountry", self.country.as_deref());
        predicate = folded(predicate, "State", self.region.as_deref());
        if let Some(year) = self.year {
            predicate = predicate.and(col("Year").eq(lit(year as f32)));
        }
        if let Some(min_dots) = self.min_dots {
            predicate = predicate.and(col("Dots").gt_eq(lit(min_dots as f32)));
        }
        predicate
    }
}

fn equals(predicate: Expr, column: &str, wanted: Option<&str>) -> Expr {
    match wanted {
        Some(value) => predicate.and(col(column).eq(lit(value))),
        None => predicate,
    }
}

fn folded(predicate: Expr, column: &str, wanted: Option<&str>) -> Expr {
    match wanted {
        Some(value) => predicate.and(
            col(column)
                .str()
                .to_lowercase()
                .eq(lit(value.trim().to_lowercase())),
        ),
        None => predicate,
    }
}

pub fn filtered_columns(
    parquet: &Path,
    filters: &Filters,
    columns: &[&str],
) -> PolarsResult<DataFrame> {
    let selection: Vec<Expr> = if columns.is_empty() {
        vec![len().alias("rows")]
    } else {
        columns.iter().map(|name| col(*name)).collect()
    };
    collect(scan(parquet)?.filter(filters.predicate()).select(selection))
}

pub fn values(frame: &DataFrame, column: &str) -> PolarsResult<Vec<f32>> {
    Ok(frame
        .column(column)?
        .f32()?
        .iter()
        .flatten()
        .filter(|value| !value.is_nan())
        .collect())
}

pub fn row_count(frame: &DataFrame, columns: &[&str]) -> PolarsResult<usize> {
    if columns.is_empty() {
        let rows = frame.column("rows")?.cast(&DataType::UInt64)?;
        Ok(rows.u64()?.get(0).unwrap_or(0) as usize)
    } else {
        Ok(frame.height())
    }
}
