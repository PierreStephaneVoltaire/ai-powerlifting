use std::fmt::Write as _;
use std::path::Path;
use std::time::Duration;

use pl_rankings::cache::Cache;
use pl_rankings::dataset::{Phase, Readiness, prepare};
use pl_rankings::ops::Engine;
use pl_rankings::query::current_year;
use pl_rankings::store::NoStore;
use serde_json::{Map, Value};

#[derive(Clone, Debug)]
pub struct Row {
    pub name: String,
    pub sex: &'static str,
    pub event: &'static str,
    pub equipment: &'static str,
    pub age_class: &'static str,
    pub bodyweight: f32,
    pub squat: f32,
    pub bench: f32,
    pub deadlift: f32,
    pub total: Option<f32>,
    pub dots: f32,
    pub federation: &'static str,
    pub country: &'static str,
    pub state: &'static str,
    pub year: i32,
}

pub fn synthetic_rows(count: usize) -> Vec<Row> {
    let year = current_year();
    (0..count)
        .map(|i| {
            let id = i % 120;
            let squat = (100 + (id * 13 + i * 3) % 150) as f32;
            let bench = (60 + (id * 7 + i) % 100) as f32;
            let deadlift = (120 + (id * 11 + i * 5) % 160) as f32;
            Row {
                name: format!("Lifter {id}"),
                sex: if id % 2 == 0 { "M" } else { "F" },
                event: if id % 11 == 0 { "B" } else { "SBD" },
                equipment: if id % 3 == 0 { "Single-ply" } else { "Raw" },
                age_class: if id % 5 == 0 { "40-44" } else { "24-34" },
                bodyweight: 52.0 + ((id * 7) % 60) as f32 + (i / 120) as f32 * 0.5,
                squat,
                bench,
                deadlift,
                total: (i % 17 != 0).then_some(squat + bench + deadlift),
                dots: (squat + bench + deadlift) / 4.0,
                federation: if id % 4 == 0 { "IPF" } else { "USAPL" },
                country: if id % 4 < 2 { "Canada" } else { "USA" },
                state: match id % 4 {
                    0 => "ON",
                    1 => "QC",
                    _ => "CA",
                },
                year: year - ((i / 120) % 4) as i32,
            }
        })
        .collect()
}

pub fn write_csv(path: &Path, rows: &[Row]) {
    let mut out = String::from(
        "Name,Sex,Event,Equipment,Age,AgeClass,Division,BodyweightKg,Best3SquatKg,Best3BenchKg,Best3DeadliftKg,TotalKg,Place,Dots,State,Federation,Date,MeetCountry,MeetName\n",
    );
    for row in rows {
        let total = row.total.map(|total| total.to_string()).unwrap_or_default();
        writeln!(
            out,
            "{},{},{},{},30,{},Open,{},{},{},{},{},1,{},{},{},{}-05-05,{},Meet",
            row.name,
            row.sex,
            row.event,
            row.equipment,
            row.age_class,
            row.bodyweight,
            row.squat,
            row.bench,
            row.deadlift,
            total,
            row.dots,
            row.state,
            row.federation,
            row.year,
            row.country,
        )
        .unwrap();
    }
    std::fs::write(path, out).unwrap();
}

pub async fn ready_engine(data_dir: &Path) -> Engine {
    let loaded = prepare(&NoStore, data_dir).await.unwrap();
    let readiness = Readiness::new();
    readiness.set(Phase::Ready(std::sync::Arc::new(loaded)));
    Engine::new(readiness, Cache::disabled(), Duration::from_secs(5), 2)
}

pub fn args(value: Value) -> Map<String, Value> {
    value.as_object().cloned().unwrap()
}
