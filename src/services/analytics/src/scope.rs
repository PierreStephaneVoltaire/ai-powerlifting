use chrono::NaiveDate;
use serde_json::{Map, Value};

use crate::model::{DEFAULT_BLOCK, Meta};
use crate::util::{text, truthy_of};

pub const ALL_BLOCKS: &str = "all";
const DATE_FIELDS: [&str; 5] = [
    "date",
    "start_date",
    "meet_date",
    "competition_date",
    "entry_date",
];

pub fn block_key(map: &Map<String, Value>) -> String {
    let id = text(map, "block_id");
    if id.is_empty() {
        text(map, "block")
    } else {
        id
    }
}

fn iso_prefix(value: &str) -> Option<NaiveDate> {
    value
        .get(..10)
        .and_then(|prefix| NaiveDate::parse_from_str(prefix, "%Y-%m-%d").ok())
}

pub fn record_day(map: &Map<String, Value>) -> Option<NaiveDate> {
    DATE_FIELDS
        .iter()
        .find(|field| truthy_of(map.get(**field)))
        .and_then(|field| iso_prefix(&text(map, field)))
}

pub struct BlockScope {
    ordered: Vec<(Option<NaiveDate>, String)>,
    active: String,
}

impl BlockScope {
    pub fn new(meta: &Meta) -> Self {
        let mut ordered: Vec<(Option<NaiveDate>, String, bool)> = meta
            .blocks
            .iter()
            .filter(|block| !block.id.is_empty())
            .map(|block| {
                (
                    iso_prefix(&block.start_date),
                    block.id.clone(),
                    block.status == "active",
                )
            })
            .collect();
        ordered.sort_by(|a, b| (a.0, &a.1).cmp(&(b.0, &b.1)));
        let configured = text(&meta.map, "current_block_id");
        let active = if !configured.is_empty() && configured != DEFAULT_BLOCK {
            configured
        } else {
            ordered
                .iter()
                .rfind(|block| block.2)
                .map(|block| block.1.clone())
                .unwrap_or_else(|| {
                    if configured.is_empty() {
                        DEFAULT_BLOCK.to_owned()
                    } else {
                        configured
                    }
                })
        };
        Self {
            ordered: ordered
                .into_iter()
                .map(|block| (block.0, block.1))
                .collect(),
            active,
        }
    }

    pub fn active(&self) -> &str {
        &self.active
    }

    pub fn resolve(&self, block: &str) -> String {
        if block.is_empty() || block == DEFAULT_BLOCK {
            self.active.clone()
        } else {
            block.to_owned()
        }
    }

    fn block_for_date(&self, day: NaiveDate) -> String {
        let dated: Vec<&(Option<NaiveDate>, String)> = self
            .ordered
            .iter()
            .filter(|block| block.0.is_some())
            .collect();
        let Some(first) = dated.first() else {
            return self.active.clone();
        };
        let active_start = dated
            .iter()
            .find(|block| block.1 == self.active)
            .and_then(|block| block.0);
        if active_start.is_some_and(|start| day >= start) {
            return self.active.clone();
        }
        if first.0.is_some_and(|start| day < start) {
            return first.1.clone();
        }
        for (index, block) in dated.iter().enumerate() {
            let next = dated.get(index + 1).and_then(|next| next.0);
            if block.0.is_some_and(|start| start <= day) && next.is_none_or(|next| day < next) {
                return block.1.clone();
            }
        }
        dated
            .last()
            .map_or_else(|| self.active.clone(), |block| block.1.clone())
    }

    pub fn record_block(&self, day: Option<NaiveDate>, stamped: &str) -> String {
        if let Some(day) = day.filter(|_| !self.ordered.is_empty()) {
            return self.block_for_date(day);
        }
        if stamped.is_empty() {
            return self.active.clone();
        }
        if stamped == DEFAULT_BLOCK {
            self.active.clone()
        } else {
            stamped.to_owned()
        }
    }

    pub fn in_block(&self, key: &str, block: &str) -> bool {
        if block == self.active || block == DEFAULT_BLOCK {
            key == self.active || key == DEFAULT_BLOCK
        } else {
            key == block
        }
    }
}
