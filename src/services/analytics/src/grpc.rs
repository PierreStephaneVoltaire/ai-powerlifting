use std::net::SocketAddr;
use std::sync::Arc;

use serde_json::Value;
use tonic::service::Interceptor;
use tonic::service::interceptor::InterceptedService;
use tonic::transport::Server as Transport;
use tonic::transport::server::TcpIncoming;
use tonic::{Request, Response, Status};

use crate::assemble::Scope;
use crate::block_ops::workspace;
use crate::blocks::index;
use crate::blocks::scope::{analysis_end, program_for_block, scoped_entry};
use crate::calc::e1rm;
use crate::correlation;
use crate::drivers;
use crate::engine::{Engine, to_value};
use crate::error::Error;
use crate::model::{Competition, Session};
use crate::proto::analytics::analytics_data_server::{AnalyticsData, AnalyticsDataServer};
use crate::proto::analytics::{
    AthleteRef, BlockKeys, BlockList, BlockRef, CorrelationInputsReply, DESCRIPTOR, ExerciseVolume,
    LifetimeRef, Report, Snapshot, WeeklyAccessoryVolume, WeeklyE1rm,
};
use crate::source::Window;
use crate::structs::{to_struct, to_structs};

const MAX_MESSAGE_BYTES: usize = 128 * 1024 * 1024;

#[derive(Clone, Debug)]
pub struct Principal {
    pub athlete: String,
    pub person: String,
}

#[derive(Clone)]
pub struct Guard {
    allowed: Arc<[String]>,
}

impl Guard {
    pub fn new(allowed: &[String]) -> Self {
        Self {
            allowed: allowed.into(),
        }
    }
}

fn metadata<'a>(request: &'a Request<()>, name: &str) -> &'a str {
    request
        .metadata()
        .get(name)
        .and_then(|value| value.to_str().ok())
        .unwrap_or_default()
}

fn service_account(source: &str) -> Option<&str> {
    source
        .rsplit_once("/sa/")
        .map(|(_, account)| account)
        .filter(|account| !account.is_empty())
}

impl Interceptor for Guard {
    fn call(&mut self, mut request: Request<()>) -> Result<Request<()>, Status> {
        let athlete = metadata(&request, "x-athlete-pk").to_owned();
        let person = metadata(&request, "x-person-pk").to_owned();
        if athlete.is_empty() || person.is_empty() {
            return Err(Status::unauthenticated(
                "x-athlete-pk and x-person-pk metadata are required",
            ));
        }
        let source = metadata(&request, "x-pl-source-principal");
        let Some(account) = service_account(source) else {
            return Err(Status::unauthenticated(
                "x-pl-source-principal metadata is required",
            ));
        };
        if !self.allowed.iter().any(|allowed| allowed == account) {
            return Err(Status::permission_denied("Calling service is not allowed"));
        }
        request
            .extensions_mut()
            .insert(Principal { athlete, person });
        Ok(request)
    }
}

fn status_of(error: Error) -> Status {
    match error {
        Error::NotFound(message) | Error::CacheMiss(message) => Status::not_found(message),
        Error::Validation(message) => Status::invalid_argument(message),
        other => Status::internal(other.to_string()),
    }
}

fn authorize<T>(request: &Request<T>, athlete: &str) -> Result<(), Status> {
    let principal = request
        .extensions()
        .get::<Principal>()
        .ok_or_else(|| Status::unauthenticated("Missing principal"))?;
    if athlete.is_empty() || principal.athlete != athlete {
        return Err(Status::permission_denied(
            "athlete_pk does not match x-athlete-pk",
        ));
    }
    Ok(())
}

pub struct Service {
    engine: Engine,
}

impl Service {
    pub fn new(engine: Engine) -> Self {
        Self { engine }
    }

    async fn report(&self, value: Result<Value, Error>) -> Result<Response<Report>, Status> {
        let body = value.map_err(status_of)?;
        Ok(Response::new(Report {
            body: Some(to_struct(body)),
        }))
    }
}

#[tonic::async_trait]
impl AnalyticsData for Service {
    async fn get_snapshot(
        &self,
        request: Request<AthleteRef>,
    ) -> Result<Response<Snapshot>, Status> {
        let athlete = request.get_ref().athlete_pk.clone();
        authorize(&request, &athlete)?;
        let loaded = self
            .engine
            .load(&athlete, &Window::default(), Scope::Everything)
            .await
            .map_err(status_of)?;
        let mut root = loaded.program.root.clone();
        let competitions = match root.remove("competitions") {
            Some(Value::Array(items)) => items,
            _ => Vec::new(),
        };
        Ok(Response::new(Snapshot {
            program: Some(to_struct(Value::Object(root))),
            sessions: to_structs(
                loaded
                    .program
                    .sessions
                    .iter()
                    .map(|session| session.raw.clone())
                    .collect(),
            ),
            weight_log: to_structs(loaded.weight_log.clone()),
            goals: to_structs(loaded.goals.clone()),
            competitions: to_structs(competitions),
        }))
    }

    async fn get_block_bundle(
        &self,
        request: Request<BlockRef>,
    ) -> Result<Response<Report>, Status> {
        let reference = request.get_ref().clone();
        authorize(&request, &reference.athlete_pk)?;
        let arguments = serde_json::json!({
            "pk": reference.athlete_pk,
            "blockKey": reference.block_key,
            "refresh": reference.refresh,
        });
        let Value::Object(arguments) = arguments else {
            return Err(Status::internal("invalid arguments"));
        };
        self.report(self.engine.blocks_get(arguments).await).await
    }

    async fn list_blocks(
        &self,
        request: Request<AthleteRef>,
    ) -> Result<Response<BlockList>, Status> {
        let athlete = request.get_ref().athlete_pk.clone();
        authorize(&request, &athlete)?;
        let entries = self
            .engine
            .list_blocks_typed(&athlete)
            .await
            .map_err(status_of)?;
        let values = entries
            .iter()
            .map(to_value)
            .collect::<Result<Vec<_>, _>>()
            .map_err(status_of)?;
        Ok(Response::new(BlockList {
            blocks: to_structs(values),
        }))
    }

    async fn compare(&self, request: Request<BlockKeys>) -> Result<Response<Report>, Status> {
        let keys = request.get_ref().clone();
        authorize(&request, &keys.athlete_pk)?;
        let Value::Object(arguments) = serde_json::json!({
            "pk": keys.athlete_pk,
            "blockKeys": keys.block_keys,
        }) else {
            return Err(Status::internal("invalid arguments"));
        };
        self.report(self.engine.compare_blocks(arguments).await)
            .await
    }

    async fn lifetime(&self, request: Request<AthleteRef>) -> Result<Response<Report>, Status> {
        let reference = request.get_ref().clone();
        authorize(&request, &reference.athlete_pk)?;
        let Value::Object(arguments) = serde_json::json!({
            "pk": reference.athlete_pk,
            "refresh": reference.refresh,
        }) else {
            return Err(Status::internal("invalid arguments"));
        };
        self.report(self.engine.lifetime_report(arguments).await)
            .await
    }

    async fn selected_lifetime(
        &self,
        request: Request<LifetimeRef>,
    ) -> Result<Response<Report>, Status> {
        let reference = request.get_ref().clone();
        authorize(&request, &reference.athlete_pk)?;
        let Value::Object(arguments) = serde_json::json!({
            "pk": reference.athlete_pk,
            "refresh": reference.refresh,
            "blockKeys": reference.block_keys,
        }) else {
            return Err(Status::internal("invalid arguments"));
        };
        self.report(self.engine.lifetime_report(arguments).await)
            .await
    }

    async fn correlation_inputs(
        &self,
        request: Request<BlockRef>,
    ) -> Result<Response<CorrelationInputsReply>, Status> {
        let reference = request.get_ref().clone();
        authorize(&request, &reference.athlete_pk)?;
        let loaded = self
            .engine
            .load(&reference.athlete_pk, &Window::default(), Scope::Everything)
            .await
            .map_err(status_of)?;
        let workspace = workspace(&loaded, self.engine.clock.today());
        let entries = index::build(&workspace);
        let raw = entries
            .iter()
            .find(|entry| entry.block_key == reference.block_key)
            .ok_or_else(|| Status::not_found(format!("Block {} not found", reference.block_key)))?;
        let entry = scoped_entry(&workspace, raw);
        let (program, _) = program_for_block(&workspace, &entry);
        let inputs = correlation::build(&program.sessions, &entry.start_date);
        let env = self.engine.env(&loaded);
        let completed: Vec<&Session> = program
            .sessions
            .iter()
            .filter(|session| session.completed)
            .collect();
        let end = analysis_end(&entry);
        let reference = crate::util::parse_date(end).unwrap_or(env.today);
        let competitions: Vec<&Competition> = program.competitions.iter().collect();
        let from_competitions = e1rm::from_competitions(&competitions, reference);
        let maxes = if from_competitions.is_empty() {
            e1rm::from_sessions_default(&completed, reference)
        } else {
            from_competitions
        };
        let drivers = drivers::build(drivers::Input {
            env,
            sessions: &program.sessions,
            cutoff: &entry.start_date,
            program_start: &entry.start_date,
            maxes,
            weekly_e1rm: &inputs.weekly_e1rm,
        });
        let measurement = |key: &str| program.meta.get(key).cloned().unwrap_or(Value::Null);
        let measurements: serde_json::Map<String, Value> = [
            "height_cm",
            "arm_wingspan_cm",
            "leg_length_cm",
            "weight_class_kg",
            "current_body_weight_kg",
        ]
        .iter()
        .map(|key| ((*key).to_owned(), measurement(key)))
        .collect();
        Ok(Response::new(CorrelationInputsReply {
            block_key: entry.block_key.clone(),
            window_start: entry.start_date.clone(),
            weeks: i32::try_from(entry.week_count).unwrap_or(i32::MAX),
            weekly_e1rm: inputs
                .weekly_e1rm
                .iter()
                .map(|(week, lifts)| WeeklyE1rm {
                    week_number: i32::try_from(*week).unwrap_or(i32::MAX),
                    squat_kg: lifts[0],
                    bench_kg: lifts[1],
                    deadlift_kg: lifts[2],
                })
                .collect(),
            weekly_accessory: inputs
                .weekly_accessory
                .iter()
                .map(|(week, exercises)| WeeklyAccessoryVolume {
                    week_number: i32::try_from(*week).unwrap_or(i32::MAX),
                    exercises: exercises
                        .iter()
                        .map(|(name, volume)| ExerciseVolume {
                            name: name.clone(),
                            volume_kg: *volume,
                        })
                        .collect(),
                })
                .collect(),
            lift_profiles: to_structs(
                program
                    .root
                    .get("lift_profiles")
                    .and_then(Value::as_array)
                    .cloned()
                    .unwrap_or_default(),
            ),
            athlete_measurements: Some(to_struct(Value::Object(measurements))),
            exercise_weeks: drivers.exercise_weeks,
            exercises: drivers.exercises,
            muscle_weeks: drivers.muscle_weeks,
            muscle_landmarks: drivers.muscle_landmarks,
            fatigue_weeks: drivers.fatigue_weeks,
            lift_sessions: drivers.lift_sessions,
            driver_stats: drivers.driver_stats,
        }))
    }
}

pub async fn serve(
    engine: Engine,
    allowed: &[String],
    address: SocketAddr,
    shutdown: impl std::future::Future<Output = ()>,
) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    serve_on(engine, allowed, TcpIncoming::bind(address)?, shutdown).await
}

pub async fn serve_on(
    engine: Engine,
    allowed: &[String],
    incoming: TcpIncoming,
    shutdown: impl std::future::Future<Output = ()>,
) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    let (reporter, health) = tonic_health::server::health_reporter();
    reporter.set_serving::<AnalyticsDataServer<Service>>().await;
    let reflection = tonic_reflection::server::Builder::configure()
        .register_encoded_file_descriptor_set(DESCRIPTOR)
        .build_v1()?;
    let data = AnalyticsDataServer::new(Service::new(engine))
        .max_decoding_message_size(MAX_MESSAGE_BYTES)
        .max_encoding_message_size(MAX_MESSAGE_BYTES);
    let service = InterceptedService::new(data, Guard::new(allowed));
    Transport::builder()
        .add_service(health)
        .add_service(reflection)
        .add_service(service)
        .serve_with_incoming_shutdown(incoming, shutdown)
        .await?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use tonic::Code;
    use tonic::metadata::MetadataValue;

    fn guard() -> Guard {
        Guard::new(&[
            "pl-analytics-ai".to_owned(),
            "pl-analytics-export".to_owned(),
        ])
    }

    fn request(pairs: &[(&'static str, &str)]) -> Request<()> {
        let mut request = Request::new(());
        for (name, value) in pairs {
            request
                .metadata_mut()
                .insert(*name, MetadataValue::try_from(*value).unwrap());
        }
        request
    }

    const AI: &str = "spiffe://cluster.local/ns/pl/sa/pl-analytics-ai";

    #[test]
    fn allowed_service_account_passes_with_principal() {
        let allowed = guard()
            .call(request(&[
                ("x-person-pk", "p"),
                ("x-athlete-pk", "a"),
                ("x-pl-source-principal", AI),
            ]))
            .unwrap();
        let principal = allowed.extensions().get::<Principal>().unwrap();
        assert_eq!(
            (principal.person.as_str(), principal.athlete.as_str()),
            ("p", "a")
        );
    }

    #[test]
    fn export_account_is_allowed() {
        let source = "cluster.local/ns/pl/sa/pl-analytics-export";
        assert!(
            guard()
                .call(request(&[
                    ("x-person-pk", "p"),
                    ("x-athlete-pk", "a"),
                    ("x-pl-source-principal", source),
                ]))
                .is_ok()
        );
    }

    #[test]
    fn unlisted_service_account_is_denied() {
        let denied = guard()
            .call(request(&[
                ("x-person-pk", "p"),
                ("x-athlete-pk", "a"),
                (
                    "x-pl-source-principal",
                    "cluster.local/ns/pl/sa/pl-rankings",
                ),
            ]))
            .unwrap_err();
        assert_eq!(denied.code(), Code::PermissionDenied);
    }

    #[test]
    fn missing_source_is_unauthenticated() {
        for source in [None, Some("pl-analytics-ai"), Some("x/sa/")] {
            let mut pairs = vec![("x-person-pk", "p"), ("x-athlete-pk", "a")];
            if let Some(source) = source {
                pairs.push(("x-pl-source-principal", source));
            }
            let denied = guard().call(request(&pairs)).unwrap_err();
            assert_eq!(denied.code(), Code::Unauthenticated, "{source:?}");
        }
    }

    #[test]
    fn missing_person_or_athlete_is_unauthenticated() {
        for pairs in [
            vec![("x-athlete-pk", "a"), ("x-pl-source-principal", AI)],
            vec![("x-person-pk", "p"), ("x-pl-source-principal", AI)],
        ] {
            let denied = guard().call(request(&pairs)).unwrap_err();
            assert_eq!(denied.code(), Code::Unauthenticated);
        }
    }

    #[test]
    fn athlete_must_match_the_request() {
        let mut allowed = guard()
            .call(request(&[
                ("x-person-pk", "p"),
                ("x-athlete-pk", "a"),
                ("x-pl-source-principal", AI),
            ]))
            .unwrap();
        assert!(authorize(&allowed, "a").is_ok());
        assert_eq!(
            authorize(&allowed, "b").unwrap_err().code(),
            Code::PermissionDenied
        );
        allowed.extensions_mut().remove::<Principal>();
        assert_eq!(
            authorize(&allowed, "a").unwrap_err().code(),
            Code::Unauthenticated
        );
    }
}
