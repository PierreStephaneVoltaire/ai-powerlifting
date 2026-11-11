use std::time::Duration;

use tonic::Request;
use tonic::metadata::MetadataValue;
use tonic::transport::{Channel, Endpoint};

use crate::proto::reports::reports_client::ReportsClient;
use crate::proto::reports::{BlockRef, RegenerateResult};

const REGENERATE_TIMEOUT: Duration = Duration::from_secs(900);

#[derive(Clone, Default)]
pub struct Ai {
    client: Option<ReportsClient<Channel>>,
    token: String,
}

impl Ai {
    pub fn disabled() -> Self {
        Self::default()
    }

    pub fn connect_lazy(url: &str, token: &str) -> Self {
        let client = Endpoint::from_shared(url.to_owned())
            .ok()
            .map(|endpoint| endpoint.timeout(REGENERATE_TIMEOUT).connect_lazy())
            .map(ReportsClient::new);
        Self {
            client,
            token: token.to_owned(),
        }
    }

    pub async fn regenerate(
        &self,
        athlete: &str,
        person: &str,
        block_key: &str,
    ) -> Option<RegenerateResult> {
        let mut client = self.client.clone()?;
        let mut request = Request::new(BlockRef {
            athlete_pk: athlete.to_owned(),
            block_key: block_key.to_owned(),
        });
        for (name, value) in [
            ("x-internal-token", self.token.as_str()),
            ("x-athlete-pk", athlete),
            ("x-person-pk", person),
        ] {
            if let Ok(value) = MetadataValue::try_from(value) {
                request.metadata_mut().insert(name, value);
            }
        }
        client
            .regenerate(request)
            .await
            .inspect_err(|error| tracing::warn!(%error, block_key, "AI regeneration failed"))
            .ok()
            .map(tonic::Response::into_inner)
    }
}
