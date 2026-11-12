use std::collections::HashMap;

use jsonschema::Validator;
use serde::Deserialize;
use serde_json::{Map, Value, json};
use thiserror::Error;

use crate::access;
use crate::auth;
use crate::caller::Caller;
use crate::config::{Config, DOMAIN};
use crate::error::Error;
use crate::ops::{Engine, Handler};

const CONTRACT: &str = include_str!("../../operations/rankings.json");
const RESERVED: [&str; 3] = ["_person_pk", "_access", "_if_job_id"];
const PERMISSIONS: &str = include_str!("../../runtime/permissions.json");

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
        if caller.generation.is_some() && caller.active_job().is_empty() {
            return Err(Error::GenerationWithoutTurn);
        }
        let operation = self.registry.get(name).ok_or(Error::UnknownOperation)?;
        if RESERVED.iter().any(|key| arguments.contains_key(*key)) {
            return Err(Error::Forbidden(
                "Reserved authorization fields cannot be supplied",
            ));
        }
        if operation.ownership != Ownership::Public && caller.person.is_empty() {
            return Err(Error::Forbidden("Authenticated Person required"));
        }
        let access = access::fetch(
            &self.http,
            &self.config.profile_url,
            name,
            &arguments,
            caller,
        )
        .await?;
        if operation.internal_only && !caller.is_backend() {
            return Err(Error::Forbidden("Operation is internal to the gateway"));
        }
        let scoped = auth::scope(operation, &arguments, caller, &access)?;
        operation.validate_input(&scoped)?;
        if caller.nested && caller.active_job().is_empty() {
            return Err(Error::NestedWithoutExecution);
        }
        let result = self.engine.run(operation.handler, &scoped).await?;
        operation.validate_result(&result)?;
        if caller.nested || caller.active_job().is_empty() {
            Ok(result)
        } else {
            Ok(json!({"status": "succeeded", "result": result}))
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::caller::Generation;
    use crate::testing::{profile, service};

    const OPERATION: &str = "powerlifting_filter_categories";

    fn caller() -> Caller {
        Caller {
            person: "person_1".to_owned(),
            athlete: "athlete_1".to_owned(),
            ..Caller::default()
        }
    }

    fn arguments(value: Value) -> Map<String, Value> {
        value.as_object().cloned().unwrap()
    }

    fn forbidden(result: Result<Value, Error>) -> bool {
        matches!(result, Err(ref error) if error.status() == axum::http::StatusCode::FORBIDDEN)
    }

    #[tokio::test]
    async fn unknown_operation_is_not_found() {
        let stub = profile(200, json!({})).await;
        let result = service(&stub)
            .call("nope", Map::new(), &caller())
            .await
            .unwrap_err();
        assert_eq!(result.status(), axum::http::StatusCode::NOT_FOUND);
        assert!(stub.hits.lock().unwrap().is_empty());
    }

    #[tokio::test]
    async fn reserved_arguments_are_forbidden_before_access() {
        let stub = profile(200, json!({})).await;
        let service = service(&stub);
        for key in RESERVED {
            let result = service
                .call(OPERATION, arguments(json!({ key: "x" })), &caller())
                .await;
            assert!(forbidden(result), "{key}");
        }
        assert!(stub.hits.lock().unwrap().is_empty());
    }

    #[tokio::test]
    async fn generation_without_a_job_is_forbidden() {
        let stub = profile(200, json!({})).await;
        let caller = Caller {
            generation: Some(Generation {
                id: "gen_1".to_owned(),
                attempt: 1,
            }),
            ..caller()
        };
        let result = service(&stub).call(OPERATION, Map::new(), &caller).await;
        assert!(forbidden(result));
        assert!(stub.hits.lock().unwrap().is_empty());
    }

    #[tokio::test]
    async fn generation_with_a_turn_reaches_access() {
        let stub = profile(200, json!({"settings_pk": "person_1"})).await;
        let caller = Caller {
            turn_id: "turn_1".to_owned(),
            generation: Some(Generation {
                id: "gen_1".to_owned(),
                attempt: 1,
            }),
            ..caller()
        };
        service(&stub)
            .call(OPERATION, Map::new(), &caller)
            .await
            .unwrap();
        assert_eq!(stub.hits.lock().unwrap().len(), 1);
    }

    #[tokio::test]
    async fn missing_person_is_denied_without_access_call() {
        let stub = profile(200, json!({})).await;
        let anonymous = Caller {
            athlete: "athlete_1".to_owned(),
            ..Caller::default()
        };
        let result = service(&stub).call(OPERATION, Map::new(), &anonymous).await;
        assert!(forbidden(result));
        assert!(stub.hits.lock().unwrap().is_empty());
    }

    #[tokio::test]
    async fn access_context_receives_headers_and_operation() {
        let stub = profile(200, json!({"settings_pk": "person_1"})).await;
        service(&stub)
            .call(OPERATION, arguments(json!({"pk": "athlete_1"})), &caller())
            .await
            .unwrap();
        let hits = stub.hits.lock().unwrap();
        let (headers, body) = &hits[0];
        assert_eq!(headers["x-person-pk"], "person_1");
        assert_eq!(headers["x-athlete-pk"], "athlete_1");
        assert_eq!(body["operation"], OPERATION);
        assert_eq!(body["arguments"], json!({"pk": "athlete_1"}));
    }

    #[tokio::test]
    async fn non_200_access_context_denies_and_is_never_cached() {
        let stub = profile(403, json!({"detail": "no"})).await;
        let service = service(&stub);
        for _ in 0..2 {
            let error = service
                .call(OPERATION, Map::new(), &caller())
                .await
                .unwrap_err();
            assert_eq!(error.status(), axum::http::StatusCode::FORBIDDEN);
        }
        assert_eq!(stub.hits.lock().unwrap().len(), 2);
    }

    #[tokio::test]
    async fn server_error_from_access_context_denies() {
        let stub = profile(500, json!({})).await;
        let result = service(&stub).call(OPERATION, Map::new(), &caller()).await;
        assert!(matches!(result, Err(Error::AccessDenied(_))));
    }

    #[tokio::test]
    async fn unreachable_access_context_is_unavailable() {
        let mut stub = profile(200, json!({})).await;
        stub.url = "http://127.0.0.1:1".to_owned();
        let result = service(&stub).call(OPERATION, Map::new(), &caller()).await;
        assert!(matches!(result, Err(Error::AccessUnavailable)));
    }

    #[tokio::test]
    async fn internal_only_requires_the_backend_account() {
        let stub = profile(200, json!({"settings_pk": "person_1"})).await;
        let mut service = service(&stub);
        service
            .registry
            .operations
            .get_mut(OPERATION)
            .unwrap()
            .internal_only = true;
        assert!(forbidden(
            service.call(OPERATION, Map::new(), &caller()).await
        ));
        let other = Caller {
            source: "cluster.local/ns/pl/sa/pl-analytics-ai".to_owned(),
            ..caller()
        };
        assert!(forbidden(service.call(OPERATION, Map::new(), &other).await));
        let backend = Caller {
            source: "spiffe://cluster.local/ns/pl/sa/powerlifting-app-backend".to_owned(),
            ..caller()
        };
        service.call(OPERATION, Map::new(), &backend).await.unwrap();
    }
}
