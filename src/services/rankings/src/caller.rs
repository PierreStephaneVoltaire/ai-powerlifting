use axum::http::HeaderMap;

const BACKEND_ACCOUNT: &str = "/sa/powerlifting-app-backend";

#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct Generation {
    pub id: String,
    pub attempt: i64,
}

#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct Caller {
    pub person: String,
    pub athlete: String,
    pub source: String,
    pub job_id: String,
    pub turn_id: String,
    pub nested: bool,
    pub generation: Option<Generation>,
}

fn header<'a>(headers: &'a HeaderMap, name: &str) -> &'a str {
    headers
        .get(name)
        .and_then(|value| value.to_str().ok())
        .unwrap_or_default()
}

impl Caller {
    pub fn identity(headers: &HeaderMap) -> Self {
        Self {
            person: header(headers, "x-person-pk").to_owned(),
            athlete: header(headers, "x-athlete-pk").to_owned(),
            source: header(headers, "x-pl-source-principal").to_owned(),
            ..Self::default()
        }
    }

    pub fn from_headers(headers: &HeaderMap) -> Self {
        let generation_id = header(headers, "x-if-generation-id");
        Self {
            job_id: header(headers, "x-if-job-id").to_owned(),
            turn_id: header(headers, "x-if-turn-id").to_owned(),
            nested: header(headers, "x-pl-nested-operation") == "true",
            generation: (!generation_id.is_empty()).then(|| Generation {
                id: generation_id.to_owned(),
                attempt: header(headers, "x-if-generation-attempt")
                    .parse()
                    .unwrap_or_default(),
            }),
            ..Self::identity(headers)
        }
    }

    pub fn active_job(&self) -> &str {
        if self.turn_id.is_empty() {
            &self.job_id
        } else {
            &self.turn_id
        }
    }

    pub fn is_backend(&self) -> bool {
        self.source
            .strip_prefix("spiffe://")
            .unwrap_or(&self.source)
            .ends_with(BACKEND_ACCOUNT)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn headers(pairs: &[(&'static str, &str)]) -> HeaderMap {
        let mut map = HeaderMap::new();
        for (name, value) in pairs {
            map.insert(*name, value.parse().unwrap());
        }
        map
    }

    #[test]
    fn reads_every_header() {
        let caller = Caller::from_headers(&headers(&[
            ("x-person-pk", "person_1"),
            ("x-athlete-pk", "athlete_1"),
            (
                "x-pl-source-principal",
                "cluster.local/ns/pl/sa/pl-analytics-ai",
            ),
            ("x-if-job-id", "job_1"),
            ("x-if-turn-id", "turn_1"),
            ("x-pl-nested-operation", "true"),
            ("x-if-generation-id", "gen_1"),
            ("x-if-generation-attempt", "3"),
        ]));
        assert_eq!(caller.person, "person_1");
        assert_eq!(caller.athlete, "athlete_1");
        assert_eq!(caller.source, "cluster.local/ns/pl/sa/pl-analytics-ai");
        assert_eq!(caller.job_id, "job_1");
        assert_eq!(caller.turn_id, "turn_1");
        assert!(caller.nested);
        assert_eq!(
            caller.generation,
            Some(Generation {
                id: "gen_1".to_owned(),
                attempt: 3
            })
        );
        assert_eq!(caller.active_job(), "turn_1");
    }

    #[test]
    fn absent_headers_are_empty() {
        let caller = Caller::from_headers(&HeaderMap::new());
        assert_eq!(caller, Caller::default());
        assert_eq!(caller.active_job(), "");
    }

    #[test]
    fn job_id_is_used_without_a_turn() {
        let caller = Caller::from_headers(&headers(&[("x-if-job-id", "job_1")]));
        assert_eq!(caller.active_job(), "job_1");
    }

    #[test]
    fn identity_ignores_execution_headers() {
        let caller = Caller::identity(&headers(&[
            ("x-person-pk", "p"),
            ("x-if-job-id", "job_1"),
            ("x-pl-nested-operation", "true"),
        ]));
        assert_eq!(caller.person, "p");
        assert_eq!(caller.job_id, "");
        assert!(!caller.nested);
    }

    #[test]
    fn backend_is_recognised_by_service_account() {
        let backend = |source: &str| {
            Caller {
                source: source.to_owned(),
                ..Caller::default()
            }
            .is_backend()
        };
        assert!(backend(
            "spiffe://cluster.local/ns/pl/sa/powerlifting-app-backend"
        ));
        assert!(backend("cluster.local/ns/pl/sa/powerlifting-app-backend"));
        assert!(!backend("cluster.local/ns/pl/sa/pl-analytics-ai"));
        assert!(!backend(
            "cluster.local/ns/pl/sa/x-powerlifting-app-backend2"
        ));
        assert!(!backend(""));
    }
}
