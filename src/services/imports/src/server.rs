use std::{
    collections::HashMap,
    sync::Arc,
    time::{Duration, Instant},
};

use axum::{
    Json, Router,
    extract::{DefaultBodyLimit, Path, State},
    http::{HeaderMap, StatusCode},
    response::{IntoResponse, Response},
    routing::{get, post},
};
use chrono::Utc;
use serde_json::{Map, Value, json};
use tokio::sync::Mutex;
use uuid::Uuid;

use crate::{
    contract::{self, Registry},
    domain::DomainClient,
    identity::{self, Identity},
    inference, inventory, parse,
    source::Source,
    store::ImportStore,
};

type ApiResult<T> = Result<T, ApiError>;

#[derive(Debug)]
struct ApiError(StatusCode, &'static str, String);

impl ApiError {
    fn bad(message: impl Into<String>) -> Self {
        Self(
            StatusCode::UNPROCESSABLE_ENTITY,
            "validation",
            message.into(),
        )
    }
    fn unavailable(message: impl Into<String>) -> Self {
        Self(
            StatusCode::SERVICE_UNAVAILABLE,
            "unavailable",
            message.into(),
        )
    }
    fn forbidden(message: impl Into<String>) -> Self {
        Self(StatusCode::FORBIDDEN, "forbidden", message.into())
    }
    fn uncertain(message: impl Into<String>) -> Self {
        Self(StatusCode::CONFLICT, "uncertain", message.into())
    }
}

impl IntoResponse for ApiError {
    fn into_response(self) -> Response {
        (
            self.0,
            Json(json!({"detail":{"code":self.1,"message":self.2}})),
        )
            .into_response()
    }
}

struct Pending {
    person: String,
    athlete: String,
    job: String,
    challenge: String,
    body: Value,
    args: Map<String, Value>,
    file_hash: String,
    rows: Vec<Value>,
    glossary: Vec<Value>,
    expires: Instant,
}

pub struct Service {
    registry: Registry,
    http: reqwest::Client,
    db: aws_sdk_dynamodb::Client,
    profile_url: String,
    coach_url: String,
    table: String,
    domain: DomainClient,
    source: Source,
    public_key: String,
    executions: Mutex<HashMap<String, Pending>>,
}

impl Service {
    pub fn new(
        db: aws_sdk_dynamodb::Client,
        profile_url: String,
        coach_url: String,
        table: String,
        domain_url: String,
        public_key: String,
    ) -> Result<Self, String> {
        let http = reqwest::Client::new();
        let source = Source {
            db: db.clone(),
            health: table.clone(),
            sessions: std::env::var("IF_SESSIONS_TABLE_NAME")
                .unwrap_or_else(|_| "if-sessions".into()),
            glossary: std::env::var("GLOSSARY_TABLE_NAME").unwrap_or_else(|_| "if-glossary".into()),
        };
        Ok(Self {
            registry: Registry::load()?,
            domain: DomainClient::new(http.clone(), domain_url)?,
            source,
            http,
            db,
            profile_url,
            coach_url,
            table,
            public_key,
            executions: Mutex::new(HashMap::new()),
        })
    }

    fn store(&self, athlete: &str) -> ImportStore {
        ImportStore::new(self.db.clone(), self.table.clone(), athlete.into())
    }

    async fn call(
        &self,
        name: &str,
        args: Map<String, Value>,
        identity: Identity,
        job: &str,
        nested: bool,
    ) -> ApiResult<Value> {
        let operation = self.registry.operations.get(name).ok_or(ApiError(
            StatusCode::NOT_FOUND,
            "not_found",
            "Unknown operation".into(),
        ))?;
        if args
            .keys()
            .any(|key| ["_person_pk", "_access", "_if_job_id"].contains(&key.as_str()))
        {
            return Err(ApiError::forbidden(
                "Reserved authorization fields cannot be supplied",
            ));
        }
        contract::authorize(&self.http, &self.profile_url, name, &args, &identity)
            .await
            .map_err(|error| {
                if error == "access denied" {
                    ApiError::forbidden(error)
                } else {
                    ApiError::unavailable(error)
                }
            })?;
        let args = operation.scope(args, &identity).map_err(|error| {
            if error == "Person and Athlete required"
                || error == "Acting Person differs from authenticated identity"
                || error == "Operation ownership conflicts with authenticated scope"
                || error == "Reserved authorization fields cannot be supplied"
            {
                ApiError::forbidden(error)
            } else {
                ApiError::bad(error)
            }
        })?;
        if nested && job.is_empty() {
            return Err(ApiError::uncertain(
                "Nested operation requires an active domain execution",
            ));
        }
        if operation.ai {
            if nested {
                return Err(ApiError::uncertain(
                    "Active domain execution unavailable; do not replay mutations",
                ));
            }
            if job.is_empty() {
                return self.submit(name, &args, &identity).await;
            }
            return self.start(args, identity, job).await;
        }
        let result = if name == "import_apply" {
            self.apply(&args, &identity, job).await?
        } else {
            inventory::execute(&self.store(&identity.athlete), name, &args)
                .await
                .map_err(ApiError::unavailable)?
                .ok_or_else(|| ApiError::unavailable("Operation unavailable"))?
        };
        operation
            .validate_result(&result)
            .map_err(|_| ApiError::unavailable("Operation produced an invalid result"))?;
        if !job.is_empty() && !nested {
            Ok(json!({"status":"succeeded", "result":result}))
        } else {
            Ok(result)
        }
    }

    async fn submit(
        &self,
        name: &str,
        args: &Map<String, Value>,
        identity: &Identity,
    ) -> ApiResult<Value> {
        let response = self.http.post(format!("{}/v1/jobs", self.coach_url.trim_end_matches('/'))).timeout(Duration::from_secs(40)).header("X-Person-Pk", &identity.person).header("X-Athlete-Pk", &identity.athlete).json(&json!({"conversation_id":format!("powerlifting:{}:{}", identity.athlete, Uuid::new_v4().simple()), "kind":"domain", "payload":{"domain":"imports", "operation":name, "arguments":args, "athlete":identity.athlete}})).send().await.map_err(|_| ApiError::unavailable("Coach service unavailable"))?;
        if !response.status().is_success() {
            return Err(ApiError::unavailable("Coach service rejected the job"));
        }
        let job: Value = response
            .json()
            .await
            .map_err(|_| ApiError::unavailable("Invalid coach response"))?;
        Ok(json!({"job_id":job["job_id"], "status":job["status"]}))
    }

    async fn apply(
        &self,
        args: &Map<String, Value>,
        identity: &Identity,
        job: &str,
    ) -> ApiResult<Value> {
        let id = string(args, "import_id");
        let store = self.store(&identity.athlete);
        let pending = store
            .get(id)
            .await
            .map_err(|_| ApiError::unavailable("Unable to read staged import"))?
            .ok_or_else(|| ApiError::bad(format!("Import not found: {id}")))?;
        if pending["status"] != "awaiting_review" {
            return Err(ApiError::bad(format!(
                "Import {id} is {}; do not replay this mutation",
                pending["status"]
            )));
        }
        let kind = args
            .get("classification_override")
            .and_then(Value::as_str)
            .or_else(|| pending.get("import_type").and_then(Value::as_str))
            .unwrap_or("");
        if kind != "template" && kind != "session_import" {
            return Err(ApiError::bad("Invalid import classification"));
        }
        let now = Utc::now().to_rfc3339();
        let claim = Uuid::new_v4().simple().to_string();
        let claimed = store.claim(id, &claim, &now).await.map_err(|_| {
            ApiError::uncertain("Unable to claim import; inspect its status before retrying")
        })?;
        if kind == "session_import" {
            let mut sessions = claimed["ai_parse_result"]["sessions"]
                .as_array()
                .cloned()
                .unwrap_or_default();
            for session in &mut sessions {
                for exercise in session["exercises"].as_array_mut().into_iter().flatten() {
                    let Some(name) = exercise.get("name").and_then(Value::as_str) else {
                        continue;
                    };
                    if let Some(id) = args
                        .get("glossary_overrides")
                        .and_then(|v| v.get(name))
                        .and_then(Value::as_str)
                        .filter(|s| !s.is_empty())
                    {
                        exercise["glossary_id"] = json!(id);
                    }
                }
            }
            let mut request = json!({"pk":identity.athlete,"import_id":id,"claim_id":claim,"sessions":sessions,"merge_strategy":args.get("merge_strategy").cloned().unwrap_or_else(|| json!("append")),"conflict_resolutions":args.get("conflict_resolutions").cloned().unwrap_or_else(|| json!([]))});
            if let Some(start) = args.get("start_date") {
                request["start_date"] = start.clone();
            }
            let target = self
                .domain
                .call(
                    "program",
                    "program_apply_session_import",
                    &request,
                    identity,
                    if job.is_empty() { None } else { Some(job) },
                )
                .await;
            let result = match target {
                Ok(result)
                    if result["status"] == "applied"
                        && result["applied_count"].is_u64()
                        && result["skipped_count"].is_u64() =>
                {
                    result
                }
                Ok(_) => {
                    let _ = store
                        .finish_claim(
                            id,
                            &claim,
                            "uncertain",
                            &Utc::now().to_rfc3339(),
                            Some("Program service returned an invalid result"),
                        )
                        .await;
                    return Err(ApiError::uncertain(
                        "Program import outcome uncertain; do not replay",
                    ));
                }
                Err(error) => {
                    let _ = store
                        .finish_claim(
                            id,
                            &claim,
                            "uncertain",
                            &Utc::now().to_rfc3339(),
                            Some(&error),
                        )
                        .await;
                    return Err(ApiError::uncertain(
                        "Program import outcome uncertain; do not replay",
                    ));
                }
            };
            store
                .finish_claim(id, &claim, "applied", &now, None)
                .await
                .map_err(|_| {
                    ApiError::uncertain(
                        "Program was updated but import status is uncertain; do not replay",
                    )
                })?;
            return Ok(result);
        }
        let payload = crate::template::payload(
            &claimed["ai_parse_result"],
            &claimed,
            args.get("glossary_overrides"),
        );
        let author = args
            .get("author")
            .and_then(Value::as_str)
            .filter(|s| !s.is_empty())
            .unwrap_or(&identity.person);
        let target = self.domain.call("templates", "template_create_from_import", &json!({"pk":identity.athlete,"template":payload,"author":author,"import_id":id,"claim_id":claim}), identity, if job.is_empty() { None } else { Some(job) }).await;
        let target_sk = match target {
            Ok(value) => match value
                .get("sk")
                .and_then(Value::as_str)
                .filter(|s| !s.is_empty())
            {
                Some(sk) => sk.to_owned(),
                None => {
                    let _ = store
                        .finish_claim(
                            id,
                            &claim,
                            "uncertain",
                            &Utc::now().to_rfc3339(),
                            Some("Template service returned no identifier"),
                        )
                        .await;
                    return Err(ApiError::uncertain(
                        "Template creation outcome uncertain; do not replay",
                    ));
                }
            },
            Err(error) => {
                let _ = store
                    .finish_claim(
                        id,
                        &claim,
                        "uncertain",
                        &Utc::now().to_rfc3339(),
                        Some(&error),
                    )
                    .await;
                return Err(ApiError::uncertain(
                    "Template creation outcome uncertain; do not replay",
                ));
            }
        };
        store
            .finish_claim(id, &claim, "applied", &now, None)
            .await
            .map_err(|_| {
                ApiError::uncertain(
                    "Template was created but import status is uncertain; do not replay",
                )
            })?;
        Ok(json!({"status":"applied", "target_sk":target_sk}))
    }

    async fn start(
        &self,
        args: Map<String, Value>,
        identity: Identity,
        job: &str,
    ) -> ApiResult<Value> {
        let filename = string(&args, "filename");
        let kind = string(&args, "import_type");
        if args.get("template_import") == Some(&Value::Bool(true)) && kind != "template" {
            return Err(ApiError::bad(
                "template_import requires import_type=template",
            ));
        }
        let extracted = parse::extract(
            string(&args, "base64_content"),
            filename,
            kind == "template",
        )
        .map_err(|error| ApiError::bad(error.to_string()))?;
        let exercises = self
            .source
            .glossary(&identity.athlete)
            .await
            .map_err(|_| ApiError::unavailable("Glossary unavailable"))?;
        let context = if kind == "template" {
            let summary = exercises
                .iter()
                .filter_map(|item| Some(json!({"id":item.get("id")?, "name":item.get("name")?})))
                .collect::<Vec<_>>();
            json!({"glossary":summary})
        } else {
            self.source
                .program_context(&identity.athlete)
                .await
                .unwrap_or_else(|_| json!({"current_maxes":{},"current_program_weeks":0}))
        };
        let mut challenge = inference::challenge(
            &extracted,
            filename,
            kind,
            &context,
            string(&args, "import_instructions"),
        )
        .map_err(|error| ApiError::bad(error.to_string()))?;
        let execution_id = Uuid::new_v4().simple().to_string();
        let challenge_id = Uuid::new_v4().simple().to_string();
        challenge["status"] = json!("needs_inference");
        challenge["execution_id"] = json!(execution_id);
        challenge["challenge_id"] = json!(challenge_id);
        let mut executions = self.executions.lock().await;
        executions.retain(|_, execution| execution.expires > Instant::now());
        executions.insert(
            execution_id,
            Pending {
                person: identity.person,
                athlete: identity.athlete,
                job: job.into(),
                challenge: challenge_id,
                body: challenge.clone(),
                args,
                file_hash: extracted.file_hash,
                rows: extracted.rows,
                glossary: exercises,
                expires: Instant::now() + Duration::from_secs(900),
            },
        );
        Ok(challenge)
    }

    async fn resume(
        &self,
        id: &str,
        body: Map<String, Value>,
        identity: Identity,
        job: &str,
    ) -> ApiResult<Value> {
        let args = Map::from_iter([("operation".into(), json!("import_parse_file"))]);
        contract::authorize(
            &self.http,
            &self.profile_url,
            "domain_resume",
            &args,
            &identity,
        )
        .await
        .map_err(|error| {
            if error == "access denied" {
                ApiError::forbidden(error)
            } else {
                ApiError::unavailable(error)
            }
        })?;
        let mut executions = self.executions.lock().await;
        let pending = executions.get(id).ok_or_else(|| {
            ApiError::uncertain("Domain execution unavailable; do not replay mutations")
        })?;
        if pending.person != identity.person || pending.athlete != identity.athlete {
            return Err(ApiError::forbidden("Execution belongs to another Person"));
        }
        if pending.job != job || pending.expires <= Instant::now() {
            return Err(ApiError::uncertain(
                "Domain execution unavailable; do not replay mutations",
            ));
        }
        let challenge_id = string(&body, "challenge_id");
        if challenge_id.is_empty() {
            return Ok(pending.body.clone());
        }
        if challenge_id != pending.challenge {
            return Err(ApiError::uncertain(
                "Challenge is stale or already answered",
            ));
        }
        let answer = body.get("content").cloned().unwrap_or(Value::Null);
        let mut answer: Value = match answer {
            Value::String(text) => serde_json::from_str(&text)
                .map_err(|_| ApiError::bad("Answer is not valid JSON"))?,
            answer => answer,
        };
        let schema = &pending.body["tools"][0]["function"]["parameters"];
        jsonschema::draft202012::validate(schema, &answer)
            .map_err(|error| ApiError::bad(error.to_string()))?;
        inference::validate_result(&answer).map_err(ApiError::bad)?;
        let pending = executions
            .remove(id)
            .ok_or_else(|| ApiError::uncertain("Execution unavailable"))?;
        drop(executions);
        let kind = string(&pending.args, "import_type");
        crate::resolve::reconcile(
            &mut answer,
            &pending.rows,
            &pending.glossary,
            kind == "template",
        );
        let automatic = pending.args.get("template_import") == Some(&Value::Bool(true));
        if automatic {
            let current = self
                .source
                .glossary(&identity.athlete)
                .await
                .map_err(|_| ApiError::unavailable("Glossary unavailable"))?;
            let plans = crate::missing::plan(&answer, &current, &identity.athlete)
                .map_err(ApiError::bad)?;
            let mut created: HashMap<String, String> = HashMap::new();
            for session in answer["sessions"].as_array().into_iter().flatten() {
                for exercise in session["exercises"].as_array().into_iter().flatten() {
                    if let Some(name) = exercise.get("name").and_then(Value::as_str) {
                        if let Some(id) = current
                            .iter()
                            .find(|entry| {
                                entry["name"]
                                    .as_str()
                                    .is_some_and(|candidate| candidate.eq_ignore_ascii_case(name))
                            })
                            .and_then(|entry| entry["id"].as_str())
                        {
                            created.insert(name.into(), id.into());
                        }
                    }
                }
            }
            for exercise in plans {
                let response = self
                    .domain
                    .call(
                        "glossary",
                        "exercise_upsert",
                        &json!({"pk":identity.athlete,"exercise":exercise}),
                        &identity,
                        Some(job),
                    )
                    .await
                    .map_err(|_| {
                        ApiError::uncertain(
                            "Glossary update outcome uncertain; check before retrying",
                        )
                    })?;
                let id = response
                    .get("id")
                    .and_then(Value::as_str)
                    .filter(|s| !s.is_empty())
                    .ok_or_else(|| {
                        ApiError::uncertain("Glossary update returned no ID; check before retrying")
                    })?;
                created.insert(
                    exercise["name"].as_str().unwrap_or("").to_owned(),
                    id.to_owned(),
                );
            }
            crate::missing::assign(&mut answer, &created);
        }
        let record = json!({"import_type":kind, "source_filename":string(&pending.args, "filename"), "source_file_hash":pending.file_hash, "ai_parse_result":answer});
        let import_id = self
            .store(&identity.athlete)
            .stage(record, Utc::now())
            .await
            .map_err(|_| {
                ApiError::uncertain(
                    "Unable to confirm staged import; do not replay without checking",
                )
            })?;
        let mut result = json!({"import_id":import_id,"classification":kind,"warnings":answer.get("warnings").cloned().unwrap_or_else(|| json!([])),"parse_notes":answer.get("parse_notes").cloned().unwrap_or_else(|| json!(""))});
        if automatic {
            let apply_args = Map::from_iter([
                ("import_id".into(), json!(import_id)),
                ("classification_override".into(), json!("template")),
                (
                    "author".into(),
                    pending
                        .args
                        .get("author")
                        .cloned()
                        .unwrap_or_else(|| json!(identity.person)),
                ),
            ]);
            let applied = self.apply(&apply_args, &identity, job).await?;
            result["template_sk"] = applied["target_sk"].clone();
        }
        self.registry.operations["import_parse_file"]
            .validate_result(&result)
            .map_err(|_| ApiError::unavailable("Operation produced an invalid result"))?;
        Ok(json!({"status":"succeeded", "result":result}))
    }
}

fn string<'a>(args: &'a Map<String, Value>, key: &str) -> &'a str {
    args.get(key).and_then(Value::as_str).unwrap_or("")
}
fn header<'a>(headers: &'a HeaderMap, name: &str) -> &'a str {
    headers
        .get(name)
        .and_then(|value| value.to_str().ok())
        .unwrap_or("")
}
fn caller(headers: &HeaderMap) -> Identity {
    Identity {
        person: header(headers, "x-person-pk").into(),
        athlete: header(headers, "x-athlete-pk").into(),
        source: header(headers, "x-pl-source-principal").into(),
    }
}
fn job(headers: &HeaderMap) -> &str {
    let turn = header(headers, "x-if-turn-id");
    if turn.is_empty() {
        header(headers, "x-if-job-id")
    } else {
        turn
    }
}

pub fn router(service: Arc<Service>) -> Router {
    Router::new()
        .route("/health", get(health))
        .route("/healthz", get(health))
        .route("/openapi.json", get(openapi))
        .route("/operations/{name}", post(operation))
        .route("/executions/{id}", post(resume))
        .route("/mcp", post(mcp))
        .layer(DefaultBodyLimit::max(32 * 1024 * 1024))
        .with_state(service)
}
async fn health() -> Json<Value> {
    Json(json!({"status":"ok","domain":"imports"}))
}
async fn openapi(State(service): State<Arc<Service>>) -> Json<Value> {
    let mut paths = Map::new();
    for operation in service.registry.operations.values() {
        let mut responses = json!({"200":{"description":"Domain result","content":{"application/json":{"schema":operation.result_schema}}}});
        if operation.ai {
            responses["202"] = json!({"description":"Queued execution","content":{"application/json":{"schema":{"type":"object","required":["job_id","status"],"properties":{"job_id":{"type":"string"},"status":{"type":"string"}}}}}});
        }
        paths.insert(format!("/operations/{}", operation.name), json!({"post":{"operationId":operation.name,"summary":operation.description,"requestBody":{"required":true,"content":{"application/json":{"schema":operation.input_schema}}},"responses":responses}}));
    }
    Json(
        json!({"openapi":"3.1.0","info":{"title":"Powerlifting imports","version":"1.0.0"},"paths":paths}),
    )
}
async fn operation(
    State(service): State<Arc<Service>>,
    Path(name): Path<String>,
    headers: HeaderMap,
    Json(args): Json<Map<String, Value>>,
) -> ApiResult<Response> {
    let result = service
        .call(
            &name,
            args,
            caller(&headers),
            job(&headers),
            header(&headers, "x-pl-nested-operation") == "true",
        )
        .await?;
    let status =
        if result.get("job_id").is_some() && result.get("cached") != Some(&Value::Bool(true)) {
            StatusCode::ACCEPTED
        } else {
            StatusCode::OK
        };
    Ok((status, Json(result)).into_response())
}
async fn resume(
    State(service): State<Arc<Service>>,
    Path(id): Path<String>,
    headers: HeaderMap,
    Json(body): Json<Map<String, Value>>,
) -> ApiResult<Json<Value>> {
    service
        .resume(&id, body, caller(&headers), job(&headers))
        .await
        .map(Json)
}
async fn mcp(
    State(service): State<Arc<Service>>,
    headers: HeaderMap,
    Json(body): Json<Value>,
) -> Response {
    let Some(id) = body.get("id").filter(|id| !id.is_null()) else {
        return (StatusCode::ACCEPTED, Json(json!({}))).into_response();
    };
    let method = body.get("method").and_then(Value::as_str).unwrap_or("");
    let params = body
        .get("params")
        .and_then(Value::as_object)
        .cloned()
        .unwrap_or_default();
    let name = string(&params, "name");
    let identity = match identity::resolve(header(&headers,"authorization"), caller(&headers), method, name, &service.public_key) {
        Ok(identity) => identity,
        Err(_) => return (StatusCode::UNAUTHORIZED, Json(json!({"jsonrpc":"2.0", "id":id, "error":{"code":-32001,"message":"Job token rejected"}}))).into_response(),
    };
    let result = match method {
        "initialize" => {
            json!({"protocolVersion":"2025-03-26", "capabilities":{"tools":{}}, "serverInfo":{"name":"powerlifting-imports","version":"1.0.0"}})
        }
        "ping" => json!({}),
        "tools/list" => {
            json!({"tools":service.registry.operations.values().map(|op| { let mut tool = json!({"name":op.name,"description":op.description,"inputSchema":op.input_schema}); if op.ai { tool["outputSchema"] = json!({"type":"object","properties":{"job_id":{"type":"string"},"status":{"type":"string"}},"required":["job_id","status"]}); } else if op.result_schema["type"] == "object" { tool["outputSchema"] = op.result_schema.clone(); } tool }).collect::<Vec<_>>()})
        }
        "tools/call" => {
            let arguments = match params.get("arguments") {
                None | Some(Value::Null) => Ok(Map::new()),
                Some(Value::Object(map)) => Ok(map.clone()),
                _ => Err(ApiError::bad("Arguments must be an object")),
            };
            let result = match arguments {
                Ok(args) => service.call(name, args, identity, "", false).await,
                Err(error) => Err(error),
            };
            match result {
                Ok(value) => {
                    let mut result = json!({"content":[{"type":"text","text":value.to_string()}],"isError":false});
                    if value.is_object() {
                        result["structuredContent"] = value;
                    }
                    result
                }
                Err(error) => {
                    json!({"content":[{"type":"text","text":json!({"error":{"code":error.1,"message":error.2},"status":error.0.as_u16()}).to_string()}],"isError":true})
                }
            }
        }
        _ => return Json(
            json!({"jsonrpc":"2.0", "id":id, "error":{"code":-32601,"message":"Method not found"}}),
        )
        .into_response(),
    };
    Json(json!({"jsonrpc":"2.0", "id":id, "result":result})).into_response()
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::routing::post;
    use base64::{Engine, engine::general_purpose::STANDARD};

    #[tokio::test]
    async fn http_and_mcp_reject_forged_identity() {
        let config = aws_config::defaults(aws_config::BehaviorVersion::latest())
            .region(aws_config::Region::new("ca-central-1"))
            .no_credentials()
            .load()
            .await;
        let service = Arc::new(
            Service::new(
                aws_sdk_dynamodb::Client::new(&config),
                "http://127.0.0.1:1".into(),
                "http://127.0.0.1:1".into(),
                "test".into(),
                "http://pl-{domain}:8000".into(),
                "".into(),
            )
            .unwrap(),
        );
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let task = tokio::spawn(async move {
            axum::serve(listener, router(service)).await.unwrap();
        });
        let client = reqwest::Client::new();
        let root = format!("http://{address}");
        let health: Value = client
            .get(format!("{root}/health"))
            .send()
            .await
            .unwrap()
            .json()
            .await
            .unwrap();
        assert_eq!(health["domain"], "imports");
        let forged = client
            .post(format!("{root}/operations/import_list"))
            .header("X-Person-Pk", "person")
            .header("X-Athlete-Pk", "athlete")
            .json(&json!({"_person_pk":"other"}))
            .send()
            .await
            .unwrap();
        assert_eq!(forged.status(), StatusCode::FORBIDDEN);
        let token = client.post(format!("{root}/mcp")).header("Authorization", "Bearer invalid").header("X-Person-Pk", "person").json(&json!({"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"import_list","arguments":{}}})).send().await.unwrap();
        assert_eq!(token.status(), StatusCode::UNAUTHORIZED);
        task.abort();
    }

    #[tokio::test]
    async fn parse_challenge_resumes_only_for_owner_and_stages_the_answer() {
        async fn fake(
            State(items): State<Arc<Mutex<Vec<Value>>>>,
            headers: HeaderMap,
            body: axum::body::Bytes,
        ) -> Json<Value> {
            let body: Value = serde_json::from_slice(&body).unwrap();
            match header(&headers, "x-amz-target") {
                "DynamoDB_20120810.Query" => Json(json!({"Items": *items.lock().await})),
                "DynamoDB_20120810.PutItem" => {
                    items.lock().await.push(body["Item"].clone());
                    Json(json!({}))
                }
                _ => Json(json!({})),
            }
        }
        async fn access() -> Json<Value> {
            Json(json!({}))
        }
        async fn glossary() -> Json<Value> {
            Json(json!({"exercises":[]}))
        }
        async fn program() -> Json<Value> {
            Json(json!({"sessions":[], "current_maxes":{}}))
        }
        let items = Arc::new(Mutex::new(Vec::new()));
        let fake_router = Router::new()
            .route("/", post(fake))
            .route("/operations/access_context", post(access))
            .route("/glossary/operations/exercise_get_glossary", post(glossary))
            .route("/program/operations/program_get", post(program))
            .with_state(items.clone());
        let fake_listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let fake_url = format!("http://{}", fake_listener.local_addr().unwrap());
        let fake_task = tokio::spawn(async move {
            axum::serve(fake_listener, fake_router).await.unwrap();
        });
        let config = aws_config::defaults(aws_config::BehaviorVersion::latest())
            .region(aws_config::Region::new("ca-central-1"))
            .endpoint_url(&fake_url)
            .credentials_provider(aws_sdk_dynamodb::config::Credentials::new(
                "test", "test", None, None, "test",
            ))
            .load()
            .await;
        let service = Arc::new(
            Service::new(
                aws_sdk_dynamodb::Client::new(&config),
                fake_url.clone(),
                fake_url.clone(),
                "test".into(),
                format!("{fake_url}/{{domain}}"),
                "".into(),
            )
            .unwrap(),
        );
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let root = format!("http://{}", listener.local_addr().unwrap());
        let task = tokio::spawn(async move {
            axum::serve(listener, router(service)).await.unwrap();
        });
        let client = reqwest::Client::new();
        let challenge: Value = client.post(format!("{root}/operations/import_parse_file")).header("X-Person-Pk", "person").header("X-Athlete-Pk", "athlete").header("X-If-Turn-Id", "job").json(&json!({"filename":"test.csv","import_type":"session_import","base64_content":STANDARD.encode("date,exercise,notes\n2026-01-01,Squat,Brace\n")})).send().await.unwrap().json().await.unwrap();
        assert_eq!(challenge["status"], "needs_inference");
        let target = format!(
            "{root}/executions/{}",
            challenge["execution_id"].as_str().unwrap()
        );
        let answer = json!({"challenge_id":challenge["challenge_id"],"content":{"program_name":null,"phases":[],"sessions":[{"date":"2026-01-01","exercises":[{"name":"Squat","notes":"invented"}]}],"warnings":[],"parse_notes":""}});
        let denied = client
            .post(&target)
            .header("X-Person-Pk", "other")
            .header("X-Athlete-Pk", "athlete")
            .header("X-If-Turn-Id", "job")
            .json(&answer)
            .send()
            .await
            .unwrap();
        assert_eq!(denied.status(), StatusCode::FORBIDDEN);
        let accepted = client
            .post(&target)
            .header("X-Person-Pk", "person")
            .header("X-Athlete-Pk", "athlete")
            .header("X-If-Turn-Id", "job")
            .json(&answer)
            .send()
            .await
            .unwrap();
        let status = accepted.status();
        let result: Value = accepted.json().await.unwrap();
        assert_eq!(status, StatusCode::OK, "{result}");
        assert_eq!(result["status"], "succeeded");
        let saved = items.lock().await;
        assert_eq!(saved.len(), 1);
        assert_eq!(saved[0]["pk"]["S"], "athlete");
        assert_eq!(
            saved[0]["ai_parse_result"]["M"]["sessions"]["L"][0]["M"]["exercises"]["L"][0]["M"]["notes"]
                ["S"],
            "Brace"
        );
        drop(saved);
        task.abort();
        fake_task.abort();
    }
}
