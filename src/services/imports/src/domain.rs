use std::time::Duration;

use serde_json::Value;

use crate::identity::Identity;

pub struct DomainClient {
    client: reqwest::Client,
    url_template: String,
}

impl DomainClient {
    pub fn new(client: reqwest::Client, url_template: String) -> Result<Self, String> {
        if !url_template.contains("{domain}") {
            return Err("service URL template must contain {domain}".into());
        }
        Ok(Self {
            client,
            url_template,
        })
    }

    pub async fn call(
        &self,
        domain: &str,
        operation: &str,
        arguments: &Value,
        identity: &Identity,
        job_id: Option<&str>,
    ) -> Result<Value, String> {
        if !matches!(
            (domain, operation),
            ("glossary", "exercise_get_glossary" | "exercise_upsert")
                | ("program", "program_apply_session_import")
                | ("templates", "template_create_from_import")
        ) {
            return Err("unsupported domain operation".into());
        }
        if identity.person.is_empty() || identity.athlete.is_empty() {
            return Err("Person and Athlete required".into());
        }
        let url = format!(
            "{}/operations/{operation}",
            self.url_template
                .replace("{domain}", domain)
                .trim_end_matches('/')
        );
        let mut request = self
            .client
            .post(url)
            .timeout(Duration::from_secs(60))
            .header("X-Person-Pk", &identity.person)
            .header("X-Athlete-Pk", &identity.athlete)
            .json(arguments);
        if let Some(job_id) = job_id.filter(|id| !id.is_empty()) {
            request = request
                .header("X-If-Turn-Id", job_id)
                .header("X-Pl-Nested-Operation", "true");
        }
        let response = request
            .send()
            .await
            .map_err(|error| format!("domain request failed: {error}"))?;
        let status = response.status();
        if !status.is_success() {
            return Err(format!("domain request failed: HTTP {status}"));
        }
        response
            .json()
            .await
            .map_err(|error| format!("invalid domain response: {error}"))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn requires_domain_placeholder() {
        assert!(DomainClient::new(reqwest::Client::new(), "http://pl-service".into()).is_err());
        assert!(DomainClient::new(reqwest::Client::new(), "http://pl-{domain}".into()).is_ok());
    }
}
