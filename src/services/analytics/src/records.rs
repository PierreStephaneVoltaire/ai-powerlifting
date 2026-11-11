use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::cache::Cache;
use crate::windows::{self, WindowKey};

pub const SECTION_KEYS: [&str; 7] = [
    "overview",
    "fatigue_readiness",
    "peaking",
    "workload",
    "alerts",
    "ai_correlation",
    "program_evaluation",
];
pub const STALE_AFTER_SECONDS: i64 = 900;

#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum Status {
    Complete,
    Error,
    Missing,
    Running,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct SectionStatus {
    #[serde(rename = "sectionKey")]
    pub section_key: String,
    pub status: Status,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub generation_id: Option<String>,
    #[serde(rename = "generatedAt", skip_serializing_if = "Option::is_none")]
    pub generated_at: Option<String>,
    #[serde(rename = "updatedAt", skip_serializing_if = "Option::is_none")]
    pub updated_at: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
    #[serde(rename = "sourceFingerprint", skip_serializing_if = "Option::is_none")]
    pub source_fingerprint: Option<String>,
    #[serde(default)]
    pub cached: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub payload: Option<Value>,
}

impl SectionStatus {
    pub fn missing(section: &str, fingerprint: &str) -> Self {
        Self {
            section_key: section.to_owned(),
            status: Status::Missing,
            generation_id: None,
            generated_at: None,
            updated_at: None,
            error: None,
            source_fingerprint: Some(fingerprint.to_owned()),
            cached: false,
            payload: None,
        }
    }

    pub fn running(section: &str, fingerprint: &str) -> Self {
        Self {
            status: Status::Running,
            updated_at: Some(timestamp()),
            ..Self::missing(section, fingerprint)
        }
    }

    pub fn complete(section: &str, fingerprint: &str, payload: Value) -> Self {
        let now = timestamp();
        Self {
            status: Status::Complete,
            generated_at: Some(now.clone()),
            updated_at: Some(now),
            payload: Some(payload),
            ..Self::missing(section, fingerprint)
        }
    }

    pub fn failed(section: &str, message: String) -> Self {
        Self {
            section_key: section.to_owned(),
            status: Status::Error,
            generation_id: None,
            generated_at: None,
            updated_at: None,
            error: Some(message),
            source_fingerprint: None,
            cached: false,
            payload: None,
        }
    }

    pub fn without_payload(mut self) -> Self {
        self.payload = None;
        self
    }
}

pub fn timestamp() -> String {
    Utc::now().format("%Y-%m-%dT%H:%M:%S%.3fZ").to_string()
}

fn stale(updated_at: Option<&str>) -> bool {
    updated_at
        .and_then(|text| DateTime::parse_from_rfc3339(text).ok())
        .is_some_and(|updated| {
            (Utc::now() - updated.with_timezone(&Utc)).num_seconds() > STALE_AFTER_SECONDS
        })
}

#[derive(Clone, Debug)]
pub struct AnalysisKey {
    pub athlete: String,
    pub as_of: String,
    pub window_key: WindowKey,
    pub start: Option<String>,
    pub end: Option<String>,
    pub fingerprint: String,
}

impl AnalysisKey {
    pub async fn resolve(
        cache: &Cache,
        athlete: &str,
        as_of: String,
        window_key: WindowKey,
        start: Option<String>,
        end: Option<String>,
    ) -> Self {
        let version = cache.version(athlete).await;
        let fingerprint = windows::source_key(&version, start.as_deref(), end.as_deref());
        Self {
            athlete: athlete.to_owned(),
            as_of,
            window_key,
            start,
            end,
            fingerprint,
        }
    }

    pub fn section_record(&self, section: &str) -> String {
        format!(
            "native_section#{}#{}#{section}#{}",
            self.as_of,
            self.window_key.as_str(),
            self.fingerprint
        )
    }

    pub fn windows_record(&self) -> String {
        format!("native_windows#{}#{}", self.as_of, self.fingerprint)
    }

    pub fn bundle_record(&self) -> String {
        format!("native_bundle#{}#{}", self.as_of, self.fingerprint)
    }
}

pub async fn section_status(cache: &Cache, key: &AnalysisKey, section: &str) -> SectionStatus {
    let Some(record) = cache
        .read::<SectionStatus>(&key.athlete, &key.section_record(section))
        .await
    else {
        return SectionStatus::missing(section, &key.fingerprint);
    };
    if record.status == Status::Running && stale(record.updated_at.as_deref()) {
        return SectionStatus {
            status: Status::Error,
            error: Some("Generation interrupted; explicitly retry.".to_owned()),
            ..record
        };
    }
    SectionStatus {
        cached: record.status == Status::Complete,
        ..record
    }
}

pub fn normalize_sections(requested: Option<&[String]>, fallback: &[&str]) -> Vec<String> {
    let filtered: Vec<String> = requested
        .unwrap_or_default()
        .iter()
        .filter(|section| SECTION_KEYS.contains(&section.as_str()))
        .cloned()
        .collect();
    if filtered.is_empty() {
        fallback
            .iter()
            .map(|section| (*section).to_owned())
            .collect()
    } else {
        filtered
    }
}

#[derive(Clone, Copy, PartialEq, Eq)]
pub enum QueueMode {
    Missing,
    Regenerate,
}

pub async fn queue(
    cache: &Cache,
    key: &AnalysisKey,
    sections: &[String],
    mode: QueueMode,
) -> Vec<String> {
    let mut accepted = Vec::new();
    for section in sections {
        let status = section_status(cache, key, section).await;
        if status.status == Status::Running
            || (status.status == Status::Complete && mode == QueueMode::Missing)
        {
            continue;
        }
        let record = SectionStatus::running(section, &key.fingerprint);
        let created = status.status == Status::Missing;
        if cache
            .write(&key.athlete, &key.section_record(section), &record, created)
            .await
        {
            accepted.push(section.clone());
        }
    }
    accepted
}

#[cfg(test)]
mod tests {
    use super::*;

    fn key() -> AnalysisKey {
        AnalysisKey {
            athlete: "operator".to_owned(),
            as_of: "2026-11-11".to_owned(),
            window_key: WindowKey::Previous4,
            start: None,
            end: None,
            fingerprint: windows::source_key("54", None, None),
        }
    }

    #[test]
    fn fingerprints_match_the_node_format() {
        assert_eq!(windows::source_key("54", None, None), "s4-v54--");
        assert_eq!(
            windows::source_key("3", Some("2026-01-01"), Some("2026-02-01")),
            "s4-v3-2026-01-01-2026-02-01"
        );
    }

    #[test]
    fn record_keys_match_the_node_format() {
        let key = key();
        assert_eq!(
            key.section_record("overview"),
            "native_section#2026-11-11#previous_4#overview#s4-v54--"
        );
        assert_eq!(key.windows_record(), "native_windows#2026-11-11#s4-v54--");
    }

    #[test]
    fn running_records_go_stale_after_fifteen_minutes() {
        let old = (Utc::now() - chrono::Duration::minutes(16))
            .format("%Y-%m-%dT%H:%M:%S%.3fZ")
            .to_string();
        let fresh = timestamp();
        assert!(stale(Some(&old)));
        assert!(!stale(Some(&fresh)));
        assert!(!stale(None));
        assert!(!stale(Some("not a date")));
    }

    #[test]
    fn section_names_are_filtered_and_defaulted() {
        let requested = vec!["overview".to_owned(), "bogus".to_owned()];
        assert_eq!(
            normalize_sections(Some(&requested), &SECTION_KEYS),
            vec!["overview".to_owned()]
        );
        assert_eq!(
            normalize_sections(None, &["alerts"]),
            vec!["alerts".to_owned()]
        );
        assert_eq!(
            normalize_sections(Some(&["bogus".to_owned()]), &["alerts"]),
            vec!["alerts".to_owned()]
        );
    }

    #[test]
    fn status_json_uses_the_documented_casing() {
        let value = serde_json::to_value(SectionStatus::missing("overview", "s4-v1--"))
            .expect("serializes");
        assert_eq!(
            value,
            serde_json::json!({
                "sectionKey": "overview",
                "status": "missing",
                "sourceFingerprint": "s4-v1--",
                "cached": false
            })
        );
    }
}
