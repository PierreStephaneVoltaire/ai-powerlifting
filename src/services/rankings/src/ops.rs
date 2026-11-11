use std::path::Path;
use std::sync::Arc;
use std::time::Duration;

use polars::prelude::DataFrame;
use serde_json::{Map, Number, Value, json};
use tokio::sync::Semaphore;

use crate::api::{Computed, PercentileCard, PercentileMeta, PercentileResponse, StatsResponse};
use crate::cache::{self, Cache};
use crate::classes::{self, Sex};
use crate::dataset::{DatasetError, Loaded, Phase, Readiness};
use crate::error::Error;
use crate::query::{self, Filters, Ranking};
use crate::scoring;

const RECENT_YEARS: i32 = 2;
const MIN_POOL: usize = 10;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Handler {
    Stats,
    Categories,
    Percentile,
}

impl Handler {
    pub fn for_operation(name: &str) -> Option<Self> {
        match name {
            "analyze_powerlifting_stats" => Some(Self::Stats),
            "powerlifting_filter_categories" => Some(Self::Categories),
            "powerlifting_ranking_percentile" => Some(Self::Percentile),
            _ => None,
        }
    }
}

pub struct Engine {
    readiness: Readiness,
    cache: Cache,
    ready_timeout: Duration,
    gate: Arc<Semaphore>,
}

impl Engine {
    pub fn new(
        readiness: Readiness,
        cache: Cache,
        ready_timeout: Duration,
        concurrency: usize,
    ) -> Self {
        Self {
            readiness,
            cache,
            ready_timeout,
            gate: Arc::new(Semaphore::new(concurrency.max(1))),
        }
    }

    pub fn readiness(&self) -> &Readiness {
        &self.readiness
    }

    pub async fn run(&self, handler: Handler, args: &Map<String, Value>) -> Result<Value, Error> {
        match handler {
            Handler::Categories => Ok(match self.readiness.current() {
                Phase::Ready(loaded) => loaded.categories.clone(),
                phase => unavailable(&phase),
            }),
            Handler::Stats => self.stats(args).await,
            Handler::Percentile => self.percentile(args).await,
        }
    }

    async fn stats(&self, args: &Map<String, Value>) -> Result<Value, Error> {
        let Phase::Ready(loaded) = self.readiness.current() else {
            return Ok(unavailable(&self.readiness.current()));
        };
        let request = StatsRequest::parse(args)?;
        self.compute(loaded, move |path| stats(path, &request))
            .await
    }

    async fn percentile(&self, args: &Map<String, Value>) -> Result<Value, Error> {
        let Phase::Ready(loaded) = self.readiness.settled(self.ready_timeout).await else {
            return Ok(unavailable(&self.readiness.current()));
        };
        let key = cache::ranking_key(&loaded.identity, query::current_year(), args);
        if let Some(cached) = self.cache.get(&key).await {
            return Ok(cached);
        }
        let request = PercentileRequest::parse(args)?;
        let result = self
            .compute(loaded, move |path| percentile(path, &request))
            .await?;
        self.cache.set(&key, &result).await;
        Ok(result)
    }

    async fn compute<F>(&self, loaded: Arc<Loaded>, work: F) -> Result<Value, Error>
    where
        F: FnOnce(&Path) -> Result<Value, Error> + Send + 'static,
    {
        let _permit = self
            .gate
            .acquire()
            .await
            .map_err(|error| Error::Internal(error.to_string()))?;
        tokio::task::spawn_blocking(move || work(&loaded.parquet))
            .await
            .map_err(|error| Error::Internal(error.to_string()))?
    }
}

pub fn unavailable(phase: &Phase) -> Value {
    let message = match phase {
        Phase::Failed(DatasetError::Missing(pattern)) => {
            format!("ERROR: Dataset missing. No powerlifting datasets found in sandbox matching: {pattern}")
        }
        Phase::Failed(DatasetError::Failed(reason)) => {
            format!("ERROR: Dataset not ready. The dataset failed to load: {reason}")
        }
        _ => "ERROR: Dataset not ready. The dataset is still loading in the background. Try again in a moment."
            .to_owned(),
    };
    Value::String(message)
}

fn invalid(key: &str, expected: &str) -> Error {
    Error::Validation(format!("{key} must be {expected}"))
}

fn number(args: &Map<String, Value>, key: &str) -> Result<Option<Number>, Error> {
    match args.get(key) {
        None | Some(Value::Null) => Ok(None),
        Some(Value::Number(value)) => Ok(Some(value.clone())),
        Some(_) => Err(invalid(key, "a number")),
    }
}

fn float(args: &Map<String, Value>, key: &str) -> Result<Option<f64>, Error> {
    Ok(number(args, key)?.and_then(|value| value.as_f64()))
}

fn text(args: &Map<String, Value>, key: &str) -> Result<Option<String>, Error> {
    match args.get(key) {
        None | Some(Value::Null) => Ok(None),
        Some(Value::String(value)) => Ok(Some(value.clone()).filter(|value| !value.is_empty())),
        Some(_) => Err(invalid(key, "a string")),
    }
}

fn present(value: Option<f64>) -> Option<f64> {
    value.filter(|value| *value != 0.0)
}

struct PercentileRequest {
    squat: Option<f64>,
    bench: Option<f64>,
    deadlift: Option<f64>,
    bodyweight: Option<f64>,
    sex_code: Option<String>,
    country: Option<String>,
    region: Option<String>,
    age_class: Option<String>,
    equipment: Option<String>,
}

impl PercentileRequest {
    fn parse(args: &Map<String, Value>) -> Result<Self, Error> {
        Ok(Self {
            squat: float(args, "squat_kg")?,
            bench: float(args, "bench_kg")?,
            deadlift: float(args, "deadlift_kg")?,
            bodyweight: float(args, "bodyweight_kg")?,
            sex_code: text(args, "sex_code")?,
            country: text(args, "country")?,
            region: text(args, "region")?,
            age_class: text(args, "age_class")?,
            equipment: text(args, "equipment")?,
        })
    }

    fn total(&self) -> Option<f64> {
        Some(present(self.squat)? + present(self.bench)? + present(self.deadlift)?)
    }

    fn band_sex(&self) -> Option<(f64, Sex)> {
        let bodyweight = present(self.bodyweight).filter(|value| *value > 0.0)?;
        let sex = Sex::from_code(self.sex_code.as_deref()?)?;
        Some((bodyweight, sex))
    }
}

fn percentile(path: &Path, request: &PercentileRequest) -> Result<Value, Error> {
    let band_sex = request.band_sex();
    let year = query::current_year();
    let ranking = Ranking {
        band: band_sex.map(|(bodyweight, sex)| classes::bounds(bodyweight, sex)),
        sex: request.sex_code.clone(),
        age_class: request.age_class.clone(),
        equipment: request.equipment.clone(),
        years: (year - RECENT_YEARS, year),
    };
    let global = query::ranking_frame(path, &ranking)?;
    let national = request
        .country
        .as_deref()
        .map(|country| query::within(global.clone(), "MeetCountry", country))
        .transpose()?;
    let regional = match (&national, request.region.as_deref()) {
        (Some(frame), Some(region)) => Some(query::within(frame.clone(), "State", region)?),
        _ => None,
    };
    to_value(&PercentileResponse {
        global: card(Some(&global), request)?,
        national: card(national.as_ref(), request)?,
        regional: card(regional.as_ref(), request)?,
        weight_class_label: band_sex.map(|(bodyweight, sex)| classes::label(bodyweight, sex)),
        meta: PercentileMeta {
            global_n: global.height(),
            national_n: national.as_ref().map(DataFrame::height),
            regional_n: regional.as_ref().map(DataFrame::height),
        },
    })
}

fn to_value(response: &impl serde::Serialize) -> Result<Value, Error> {
    serde_json::to_value(response).map_err(|error| Error::Internal(error.to_string()))
}

fn percentile_for(value: Option<f64>, pool: &[f32]) -> Option<i64> {
    let value = value.filter(|value| *value > 0.0)?;
    (pool.len() >= MIN_POOL).then(|| scoring::percent_below(pool, value as f32))
}

fn card(frame: Option<&DataFrame>, request: &PercentileRequest) -> Result<PercentileCard, Error> {
    let Some(frame) = frame.filter(|frame| frame.height() > 0) else {
        return Ok(PercentileCard {
            squat: None,
            bench: None,
            deadlift: None,
            total: None,
            top10_mean_squat: None,
            top10_mean_bench: None,
            top10_mean_deadlift: None,
            top10_mean_total: None,
        });
    };
    let squat = query::values(frame, "Best3SquatKg")?;
    let bench = query::values(frame, "Best3BenchKg")?;
    let deadlift = query::values(frame, "Best3DeadliftKg")?;
    let total = query::values(frame, "TotalKg")?;
    Ok(PercentileCard {
        squat: percentile_for(request.squat, &squat),
        bench: percentile_for(request.bench, &bench),
        deadlift: percentile_for(request.deadlift, &deadlift),
        total: percentile_for(request.total(), &total),
        top10_mean_squat: scoring::top_quartile_mean(&squat),
        top10_mean_bench: scoring::top_quartile_mean(&bench),
        top10_mean_deadlift: scoring::top_quartile_mean(&deadlift),
        top10_mean_total: scoring::top_quartile_mean(&total),
    })
}

struct StatsRequest {
    filters: Filters,
    squat: Option<Number>,
    bench: Option<Number>,
    deadlift: Option<Number>,
    bodyweight: Option<f64>,
    sex_code: Option<String>,
}

impl StatsRequest {
    fn parse(args: &Map<String, Value>) -> Result<Self, Error> {
        Ok(Self {
            filters: Filters {
                federation: text(args, "federation")?,
                country: text(args, "country")?,
                region: text(args, "region")?,
                equipment: text(args, "equipment")?,
                sex: text(args, "sex")?,
                age_class: text(args, "age_class")?,
                year: present(float(args, "year")?),
                event_type: text(args, "event_type")?,
                min_dots: float(args, "min_dots")?,
            },
            squat: number(args, "squat_kg")?,
            bench: number(args, "bench_kg")?,
            deadlift: number(args, "deadlift_kg")?,
            bodyweight: float(args, "bodyweight_kg")?,
            sex_code: text(args, "sex_code")?,
        })
    }

    fn total(&self) -> Option<Number> {
        let lifts = [&self.squat, &self.bench, &self.deadlift];
        let numbers: Vec<&Number> = lifts
            .iter()
            .filter_map(|lift| lift.as_ref())
            .filter(|lift| lift.as_f64() != Some(0.0))
            .collect();
        if numbers.len() != lifts.len() {
            return None;
        }
        let integers: Option<i64> = numbers
            .iter()
            .try_fold(0i64, |sum, lift| sum.checked_add(lift.as_i64()?));
        match integers {
            Some(sum) => Some(Number::from(sum)),
            None => Number::from_f64(numbers.iter().filter_map(|lift| lift.as_f64()).sum()),
        }
    }

    fn dots(&self, total: Option<&Number>) -> Option<f64> {
        let total = total?.as_f64().filter(|value| *value != 0.0)?;
        let bodyweight = present(self.bodyweight)?;
        let sex = Sex::from_code(self.sex_code.as_deref()?)?;
        scoring::dots(total, bodyweight, sex)
    }
}

fn stats(path: &Path, request: &StatsRequest) -> Result<Value, Error> {
    let total = request.total();
    let dots = request.dots(total.as_ref());
    let metrics: Vec<(&str, f64, &str)> = [
        (
            "Squat",
            request.squat.as_ref().and_then(Number::as_f64),
            query::METRIC_COLUMNS[0],
        ),
        (
            "Bench",
            request.bench.as_ref().and_then(Number::as_f64),
            query::METRIC_COLUMNS[1],
        ),
        (
            "Deadlift",
            request.deadlift.as_ref().and_then(Number::as_f64),
            query::METRIC_COLUMNS[2],
        ),
        (
            "Total",
            total.as_ref().and_then(Number::as_f64),
            query::METRIC_COLUMNS[3],
        ),
        ("Dots", dots, query::METRIC_COLUMNS[4]),
    ]
    .into_iter()
    .filter_map(|(label, value, column)| Some((label, value.filter(|v| *v > 0.0)?, column)))
    .collect();
    let columns: Vec<&str> = metrics.iter().map(|(_, _, column)| *column).collect();
    let frame = query::filtered_columns(path, &request.filters, &columns)?;
    let size = query::row_count(&frame, &columns)?;
    let mut analysis = Map::new();
    if size > 0 {
        for (label, value, column) in metrics {
            analysis.insert(
                label.to_owned(),
                rank_value(value, &query::values(&frame, column)?),
            );
        }
    }
    to_value(&StatsResponse {
        dataset_size: size,
        computed: Computed {
            total_kg: total,
            dots,
        },
        analysis,
    })
}

fn single_precision_text(value: f32) -> Value {
    Value::String(format!("{:?}", scoring::round_f32_hundredths(value)))
}

fn rank_value(value: f64, pool: &[f32]) -> Value {
    if pool.is_empty() {
        return json!({"n": 0});
    }
    let target = value as f32;
    let n = pool.len();
    let beat = pool.iter().filter(|v| **v < target).count();
    let tied = pool.iter().filter(|v| **v == target).count();
    let max = pool.iter().copied().fold(f32::MIN, f32::max);
    let mean = scoring::mean_f32(pool);
    let relative = |reference: f32| {
        if reference > 0.0 {
            single_precision_text(target / reference * 100.0)
        } else {
            json!(0)
        }
    };
    json!({
        "n": n,
        "rank": n - beat,
        "beat": beat,
        "tied": tied,
        "percentile": scoring::round_half_even(beat as f64 / n as f64 * 100.0),
        "pct_of_max": relative(max),
        "pct_of_mean": relative(mean),
        "median": scoring::round_to(f64::from(scoring::median_f32(pool)), 2),
        "mean": scoring::round_to(f64::from(mean), 2),
        "max": scoring::round_to(f64::from(max), 2),
    })
}
