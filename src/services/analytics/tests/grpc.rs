mod common;

use std::sync::Arc;

use common::fixtures;
use pl_analytics::grpc;
use pl_analytics::proto::analytics::AthleteRef;
use pl_analytics::proto::analytics::analytics_data_client::AnalyticsDataClient;
use tonic::metadata::MetadataValue;
use tonic::transport::Channel;
use tonic::transport::server::TcpIncoming;
use tonic::{Code, Request};

const ALLOWED: &str = "spiffe://cluster.local/ns/pl/sa/pl-analytics-ai";
const DENIED: &str = "spiffe://cluster.local/ns/pl/sa/pl-rankings";

struct Running {
    client: AnalyticsDataClient<Channel>,
    athlete: String,
    stop: tokio::sync::oneshot::Sender<()>,
}

async fn start() -> Option<Running> {
    let fixtures = fixtures()?;
    let incoming = TcpIncoming::bind("127.0.0.1:0".parse().expect("address")).expect("bind");
    let address = incoming.local_addr().expect("local address");
    let (stop, stopped) = tokio::sync::oneshot::channel::<()>();
    let engine = fixtures.engine();
    let allowed = Arc::new(vec!["pl-analytics-ai".to_owned()]);
    tokio::spawn(async move {
        grpc::serve_on(engine, &allowed, incoming, async {
            let _ = stopped.await;
        })
        .await
    });
    let channel = Channel::from_shared(format!("http://{address}"))
        .expect("uri")
        .connect_lazy();
    Some(Running {
        client: AnalyticsDataClient::new(channel),
        athlete: fixtures.athlete.clone(),
        stop,
    })
}

fn request(athlete: &str, source: &str) -> Request<AthleteRef> {
    let mut request = Request::new(AthleteRef {
        athlete_pk: athlete.to_owned(),
        refresh: false,
    });
    let metadata = request.metadata_mut();
    metadata.insert(
        "x-athlete-pk",
        MetadataValue::try_from(athlete).expect("ascii"),
    );
    metadata.insert(
        "x-person-pk",
        MetadataValue::try_from("person").expect("ascii"),
    );
    metadata.insert(
        "x-pl-source-principal",
        MetadataValue::try_from(source).expect("ascii"),
    );
    request
}

#[tokio::test(flavor = "multi_thread")]
async fn allowed_caller_lists_blocks_and_reads_lifetime() {
    let Some(mut running) = start().await else {
        return;
    };
    let fixtures = fixtures().expect("fixtures");
    let blocks = running
        .client
        .list_blocks(request(&running.athlete, ALLOWED))
        .await
        .expect("list blocks")
        .into_inner();
    assert_eq!(
        blocks.blocks.len(),
        fixtures.manifest["blockKeys"]
            .as_array()
            .map_or(0, Vec::len)
    );
    let report = running
        .client
        .lifetime(request(&running.athlete, ALLOWED))
        .await
        .expect("lifetime")
        .into_inner();
    let body = report.body.expect("report body");
    assert!(body.fields.contains_key("blocks"));
    assert!(body.fields.contains_key("correlations"));
    assert!(body.fields.contains_key("did_not_work"));
    let _ = running.stop.send(());
}

#[tokio::test(flavor = "multi_thread")]
async fn unlisted_caller_is_denied() {
    let Some(mut running) = start().await else {
        return;
    };
    let denied = running
        .client
        .list_blocks(request(&running.athlete, DENIED))
        .await
        .expect_err("denied");
    assert_eq!(denied.code(), Code::PermissionDenied);
    let denied = running
        .client
        .lifetime(request(&running.athlete, DENIED))
        .await
        .expect_err("denied");
    assert_eq!(denied.code(), Code::PermissionDenied);
    let _ = running.stop.send(());
}

#[tokio::test(flavor = "multi_thread")]
async fn missing_metadata_is_unauthenticated_and_athlete_must_match() {
    let Some(mut running) = start().await else {
        return;
    };
    let bare = Request::new(AthleteRef {
        athlete_pk: running.athlete.clone(),
        refresh: false,
    });
    let denied = running
        .client
        .list_blocks(bare)
        .await
        .expect_err("unauthenticated");
    assert_eq!(denied.code(), Code::Unauthenticated);
    let mut mismatched = request(&running.athlete, ALLOWED);
    mismatched.get_mut().athlete_pk = "someone-else".to_owned();
    let denied = running
        .client
        .list_blocks(mismatched)
        .await
        .expect_err("mismatch");
    assert_eq!(denied.code(), Code::PermissionDenied);
    let _ = running.stop.send(());
}
