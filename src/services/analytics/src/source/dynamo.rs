use std::collections::HashMap;

use aws_sdk_dynamodb::Client;
use aws_sdk_dynamodb::types::AttributeValue;
use serde_json::Value;

use super::{Fetching, Loading, RawData, Source, Window};
use crate::config::Tables;
use crate::error::Error;

const COMPETITIONS_INDEX: &str = "entries-by-date";

pub struct DynamoSource {
    client: Client,
    tables: Tables,
}

type Item = HashMap<String, AttributeValue>;

fn storage(error: impl std::fmt::Display) -> Error {
    Error::Internal(format!("storage: {error}"))
}

fn decode(item: Item) -> Result<Value, Error> {
    serde_dynamo::from_item(item).map_err(storage)
}

fn key(pk: &str, sk: &str) -> Item {
    HashMap::from([
        ("pk".to_owned(), AttributeValue::S(pk.to_owned())),
        ("sk".to_owned(), AttributeValue::S(sk.to_owned())),
    ])
}

impl DynamoSource {
    pub async fn connect(tables: Tables, region: String) -> Self {
        let config = aws_config::defaults(aws_config::BehaviorVersion::latest())
            .region(aws_config::Region::new(region))
            .load()
            .await;
        Self {
            client: Client::new(&config),
            tables,
        }
    }

    async fn get(&self, table: &str, pk: &str, sk: &str, consistent: bool) -> Result<Value, Error> {
        let output = self
            .client
            .get_item()
            .table_name(table)
            .set_key(Some(key(pk, sk)))
            .consistent_read(consistent)
            .send()
            .await
            .map_err(storage)?;
        output.item.map_or(Ok(Value::Null), decode)
    }

    async fn query_all(
        &self,
        table: &str,
        index: Option<&str>,
        condition: &str,
        names: HashMap<String, String>,
        values: Item,
    ) -> Result<Vec<Value>, Error> {
        let mut items = Vec::new();
        let mut start = None;
        loop {
            let output = self
                .client
                .query()
                .table_name(table)
                .set_index_name(index.map(str::to_owned))
                .key_condition_expression(condition)
                .set_expression_attribute_names((!names.is_empty()).then(|| names.clone()))
                .set_expression_attribute_values(Some(values.clone()))
                .set_exclusive_start_key(start.take())
                .send()
                .await
                .map_err(storage)?;
            for item in output.items.unwrap_or_default() {
                items.push(decode(item)?);
            }
            match output.last_evaluated_key {
                Some(last) if !last.is_empty() => start = Some(last),
                _ => return Ok(items),
            }
        }
    }

    async fn sessions(
        &self,
        athlete: &str,
        program_sk: &str,
        window: &Window,
    ) -> Result<Vec<Value>, Error> {
        let (lower, upper) = window.session_bounds(program_sk);
        let values = HashMap::from([
            (":pk".to_owned(), AttributeValue::S(athlete.to_owned())),
            (":lower".to_owned(), AttributeValue::S(lower)),
            (":upper".to_owned(), AttributeValue::S(upper)),
        ]);
        self.query_all(
            &self.tables.sessions,
            None,
            "pk = :pk AND sk BETWEEN :lower AND :upper",
            HashMap::new(),
            values,
        )
        .await
    }

    async fn competitions(&self, athlete: &str, window: &Window) -> Result<Vec<Value>, Error> {
        let mut values = HashMap::from([(":pk".to_owned(), AttributeValue::S(athlete.to_owned()))]);
        let mut condition = "pk = :pk".to_owned();
        match (&window.start, &window.end) {
            (Some(start), Some(end)) => {
                condition.push_str(" AND entry_date BETWEEN :start AND :end");
                values.insert(":start".to_owned(), AttributeValue::S(start.clone()));
                values.insert(":end".to_owned(), AttributeValue::S(end.clone()));
            }
            (Some(start), None) => {
                condition.push_str(" AND entry_date >= :start");
                values.insert(":start".to_owned(), AttributeValue::S(start.clone()));
            }
            (None, Some(end)) => {
                condition.push_str(" AND entry_date <= :end");
                values.insert(":end".to_owned(), AttributeValue::S(end.clone()));
            }
            (None, None) => {}
        }
        self.query_all(
            &self.tables.competitions,
            Some(COMPETITIONS_INDEX),
            &condition,
            HashMap::new(),
            values,
        )
        .await
    }

    async fn goals(&self, athlete: &str) -> Result<Vec<Value>, Error> {
        let values = HashMap::from([
            (":pk".to_owned(), AttributeValue::S(athlete.to_owned())),
            (":prefix".to_owned(), AttributeValue::S("GOAL#".to_owned())),
        ]);
        self.query_all(
            &self.tables.goals,
            None,
            "pk = :pk AND begins_with(sk, :prefix)",
            HashMap::new(),
            values,
        )
        .await
    }

    async fn load_all(&self, athlete: &str, window: &Window) -> Result<RawData, Error> {
        let health = &self.tables.health;
        let pointer = self.get(health, athlete, "program#current", true).await?;
        let program_sk = pointer
            .get("ref_sk")
            .and_then(Value::as_str)
            .ok_or_else(|| Error::NotFound(format!("No program pointer found for pk={athlete}")))?
            .to_owned();
        let program = self.get(health, athlete, &program_sk, true).await?;
        if !program.is_object() {
            return Err(Error::NotFound(format!("Program not found: {program_sk}")));
        }
        let (sessions, competitions, goals, weight_log, glossary) = tokio::try_join!(
            self.sessions(athlete, &program_sk, window),
            self.competitions(athlete, window),
            self.goals(athlete),
            self.get(health, athlete, "weight_log#current", false),
            self.get(health, athlete, "glossary#v1", false),
        )?;
        Ok(RawData {
            pointer,
            program,
            program_sk,
            sessions,
            weight_log,
            glossary,
            competitions,
            goals,
        })
    }
}

impl Source for DynamoSource {
    fn load<'a>(&'a self, athlete: &'a str, window: &'a Window) -> Loading<'a> {
        Box::pin(self.load_all(athlete, window))
    }

    fn glossary<'a>(&'a self, athlete: &'a str) -> Fetching<'a> {
        Box::pin(self.get(&self.tables.health, athlete, "glossary#v1", false))
    }
}
