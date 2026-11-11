use std::collections::HashMap;

use jsonschema::Validator;
use serde::Deserialize;
use serde_json::{Map, Value, json};
use thiserror::Error;

use crate::auth;
use crate::config::{Config, DOMAIN};
use crate::error::Error;
use crate::ops::{Engine, Handler};

const CONTRACT: &str = include_str!("../../operations/rankings.json");
const PERMISSIONS: &str = include_str!("../../permissions.json");

#[derive(Debug, Error)]
pub enum ContractError {
    #[error("invalid contract: {0}")]
    Invalid(String),
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum Ownership {
    Athlete,
    Public,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "lowercase")]
enum Execution {
    Deterministic,
}

#[derive(Deserialize)]
struct Record {
    name: String,
    domain: String,
    description: String,
    input_schema: Value,
    result_schema: Value,
    ownership: Ownership,
    execution: Execution,
}

pub struct Operation {
    pub name: String,
    pub description: String,
    pub ownership: Ownership,
    pub input_schema: Value,
    pub result_schema: Value,
    pub internal_only: bool,
    pub handler: Handler,
    input: Validator,
    result: Validator,
}

impl Operation {
    pub fn validate_input(&self, arguments: &Map<String, Value>) -> Result<(), Error> {
        let instance = Value::Object(arguments.clone());
        self.input
            .validate(&instance)
            .map_err(|error| Error::Validation(error.to_string()))
    }

    pub fn validate_result(&self, result: &Value) -> Result<(), Error> {
        self.result
            .validate(result)
            .map_err(|_| Error::InvalidResult)
    }

    pub fn has_input(&self, name: &str) -> bool {
        self.input_schema
            .pointer(&format!("/properties/{name}"))
            .is_some()
    }
}

pub struct Registry {
    order: Vec<String>,
    operations: HashMap<String, Operation>,
}

impl Registry {
    pub fn load() -> Result<Self, ContractError> {
        let records: Vec<Record> = serde_json::from_str(CONTRACT).map_err(invalid)?;
        let permissions: Value = serde_json::from_str(PERMISSIONS).map_err(invalid)?;
        let mut registry = Self {
            order: Vec::new(),
            operations: HashMap::new(),
        };
        for record in records {
            let internal_only = permissions
                .pointer(&format!("/{}/internal_only", record.name))
                .and_then(Value::as_bool)
                .unwrap_or(false);
            let operation = build(record, internal_only)?;
            registry.order.push(operation.name.clone());
            if registry
                .operations
                .insert(operation.name.clone(), operation)
                .is_some()
            {
                return Err(ContractError::Invalid("duplicate operation".to_owned()));
            }
        }
        Ok(registry)
    }

    pub fn get(&self, name: &str) -> Option<&Operation> {
        self.operations.get(name)
    }

    pub fn iter(&self) -> impl Iterator<Item = &Operation> {
        self.order
            .iter()
            .filter_map(|name| self.operations.get(name))
    }
}

fn invalid(error: impl std::fmt::Display) -> ContractError {
    ContractError::Invalid(error.to_string())
}

fn compile(schema: &Value) -> Result<Validator, ContractError> {
    jsonschema::draft202012::options()
        .should_validate_formats(true)
        .build(schema)
        .map_err(invalid)
}

fn default_pk(schema: &mut Value) {
    let properties = schema
        .as_object_mut()
        .map(|schema| schema.entry("properties").or_insert_with(|| json!({})))
        .and_then(Value::as_object_mut);
    if let Some(properties) = properties {
        properties
            .entry("pk")
            .or_insert_with(|| json!({"type": "string", "minLength": 1}));
    }
}

fn build(record: Record, internal_only: bool) -> Result<Operation, ContractError> {
    let Execution::Deterministic = record.execution;
    if record.domain != DOMAIN {
        return Err(ContractError::Invalid(format!(
            "operation {} belongs to {}",
            record.name, record.domain
        )));
    }
    let handler = Handler::for_operation(&record.name)
        .ok_or_else(|| ContractError::Invalid(format!("no handler for {}", record.name)))?;
    let mut input_schema = record.input_schema;
    if record.ownership != Ownership::Public {
        default_pk(&mut input_schema);
    }
    Ok(Operation {
        input: compile(&input_schema)?,
        result: compile(&record.result_schema)?,
        name: record.name,
        description: record.description,
        ownership: record.ownership,
        input_schema,
        result_schema: record.result_schema,
        internal_only,
        handler,
    })
}

#[derive(Clone, Debug, Default)]
pub struct Caller {
    pub athlete: String,
    pub person: String,
    pub principal: String,
    pub job_id: String,
    pub generation_id: String,
    pub nested: bool,
}

pub struct Service {
    pub config: Config,
    pub registry: Registry,
    engine: Engine,
    http: reqwest::Client,
}

impl Service {
    pub fn new(config: Config, registry: Registry, engine: Engine) -> Self {
        Self {
            config,
            registry,
            engine,
            http: reqwest::Client::new(),
        }
    }

    pub fn readiness(&self) -> &crate::dataset::Readiness {
        self.engine.readiness()
    }

    pub async fn call(
        &self,
        name: &str,
        arguments: Map<String, Value>,
        caller: &Caller,
    ) -> Result<Value, Error> {
        if !caller.generation_id.is_empty() && caller.job_id.is_empty() {
            return Err(Error::GenerationWithoutTurn);
        }
        let operation = self.registry.get(name).ok_or(Error::UnknownOperation)?;
        let claims = auth::verify_principal(&self.config.principal_secret, name, caller)?;
        let access = auth::fetch_access(&self.http, &self.config, name, &arguments, caller).await?;
        let scoped = auth::scope(operation, &arguments, &claims, &access)?;
        operation.validate_input(&scoped)?;
        if caller.nested && caller.job_id.is_empty() {
            return Err(Error::NestedWithoutExecution);
        }
        let result = self.engine.run(operation.handler, &scoped).await?;
        operation.validate_result(&result)?;
        if caller.nested || caller.job_id.is_empty() {
            Ok(result)
        } else {
            Ok(json!({"status": "succeeded", "result": result}))
        }
    }
}
