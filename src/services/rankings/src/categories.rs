use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;

use polars::prelude::*;
use serde_json::{Map, Value, json};

use crate::query::{collect, scan};

const LISTS: [(&str, &str); 7] = [
    ("federations", "Federation"),
    ("countries", "MeetCountry"),
    ("regions", "State"),
    ("equipment", "Equipment"),
    ("sex", "Sex"),
    ("age_classes", "AgeClass"),
    ("event_types", "Event"),
];
const GROUPS: [(&str, &str, &str); 3] = [
    ("country_federations", "MeetCountry", "Federation"),
    ("country_regions", "MeetCountry", "State"),
    ("region_federations", "State", "Federation"),
];

pub fn compute(parquet: &Path) -> PolarsResult<Value> {
    let mut options = Map::new();
    for (key, column) in LISTS {
        options.insert(key.to_owned(), json!(distinct(parquet, column)?));
    }
    options.insert("years".to_owned(), json!(years(parquet)?));
    for (key, group, value) in GROUPS {
        options.insert(key.to_owned(), grouped(parquet, group, value)?);
    }
    Ok(Value::Object(options))
}

fn distinct(parquet: &Path, column: &str) -> PolarsResult<BTreeSet<String>> {
    let frame = collect(
        scan(parquet)?
            .select([col(column)])
            .drop_nulls(None)
            .unique(None, UniqueKeepStrategy::Any),
    )?;
    Ok(frame
        .column(column)?
        .str()?
        .iter()
        .flatten()
        .map(str::to_owned)
        .collect())
}

fn years(parquet: &Path) -> PolarsResult<Vec<i64>> {
    let frame = collect(
        scan(parquet)?
            .select([col("Year")])
            .drop_nulls(None)
            .unique(None, UniqueKeepStrategy::Any),
    )?;
    let mut years: Vec<i64> = frame
        .column("Year")?
        .f32()?
        .iter()
        .flatten()
        .filter(|year| !year.is_nan())
        .map(|year| year as i64)
        .collect();
    years.sort_unstable_by(|a, b| b.cmp(a));
    years.dedup();
    Ok(years)
}

fn grouped(parquet: &Path, group: &str, value: &str) -> PolarsResult<Value> {
    let frame = collect(
        scan(parquet)?
            .select([col(group), col(value)])
            .drop_nulls(None)
            .unique(None, UniqueKeepStrategy::Any),
    )?;
    let mut map: BTreeMap<&str, BTreeSet<&str>> = BTreeMap::new();
    let groups = frame.column(group)?.str()?;
    let values = frame.column(value)?.str()?;
    for (key, item) in groups.iter().zip(values.iter()) {
        if let (Some(key), Some(item)) = (key, item) {
            map.entry(key).or_default().insert(item);
        }
    }
    Ok(json!(map))
}
