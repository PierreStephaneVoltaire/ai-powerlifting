use serde_json::{Map, Value, json};

use crate::args::{self, WeeklyArgs, WindowArgs};
use crate::assemble::{Loaded, Scope};
use crate::calc::Env;
use crate::engine::{Engine, to_value};
use crate::error::Error;
use crate::records::{
    AnalysisKey, QueueMode, SECTION_KEYS, SectionStatus, normalize_sections, queue, section_status,
    timestamp,
};
use crate::sections::{self, DETERMINISTIC, Params};
use crate::source::Window;
use crate::util::parse_date;
use crate::windows::{
    self, ALL_WINDOWS, CACHE_SCHEMA_VERSION, MANIFEST_SCHEMA_VERSION, WindowKey, Windows,
};

const AI_PENDING: &str = "AI sections are served by pl-analytics-ai";

fn is_iso(text: &str) -> bool {
    let bytes = text.as_bytes();
    bytes.len() == 10
        && bytes.iter().enumerate().all(|(index, byte)| {
            if index == 4 || index == 7 {
                *byte == b'-'
            } else {
                byte.is_ascii_digit()
            }
        })
}

impl Engine {
    fn as_of(&self, requested: Option<&str>) -> String {
        requested
            .filter(|text| is_iso(text))
            .map_or_else(|| self.clock.today().to_string(), str::to_owned)
    }

    async fn key(&self, args: &WindowArgs) -> AnalysisKey {
        AnalysisKey::resolve(
            &self.cache,
            &args.pk,
            self.as_of(args.as_of_date.as_deref()),
            WindowKey::parse(args.window.as_deref().unwrap_or_default()),
            None,
            None,
        )
        .await
    }

    async fn current_program(&self, key: &AnalysisKey) -> Result<Loaded, Error> {
        let window = Window {
            start: key.start.clone(),
            end: key.end.clone(),
        };
        self.load(&key.athlete, &window, Scope::Block("current"))
            .await
    }

    async fn windows_for(&self, key: &AnalysisKey) -> Result<Windows, Error> {
        if let Some(saved) = self
            .cache
            .read::<Windows>(&key.athlete, &key.windows_record())
            .await
        {
            return Ok(saved);
        }
        let loaded = self.current_program(key).await?;
        let built = windows::build(
            &loaded.program,
            parse_date(&key.as_of).unwrap_or_else(|| self.clock.today()),
        )?;
        self.cache
            .write(&key.athlete, &key.windows_record(), &built, false)
            .await;
        Ok(built)
    }

    pub async fn manifest(&self, arguments: Map<String, Value>) -> Result<Value, Error> {
        let args: WindowArgs = args::parse(arguments)?;
        let key = self.key(&args).await;
        let mut sections = Map::new();
        for section in SECTION_KEYS {
            let status = section_status(&self.cache, &key, section)
                .await
                .without_payload();
            sections.insert(section.to_owned(), to_value(&status)?);
        }
        Ok(json!({
            "schemaVersion": MANIFEST_SCHEMA_VERSION,
            "asOfDate": key.as_of,
            "windowKey": key.window_key.as_str(),
            "windows": to_value(&self.windows_for(&key).await?)?,
            "sourceFingerprint": key.fingerprint,
            "sections": sections,
        }))
    }

    pub async fn sections_get(&self, arguments: Map<String, Value>) -> Result<Value, Error> {
        let args: WindowArgs = args::parse(arguments)?;
        let section = args.section_key.clone().unwrap_or_default();
        if !SECTION_KEYS.contains(&section.as_str()) {
            return Err(Error::Validation(format!(
                "Unknown analysis section: {section}"
            )));
        }
        let key = self.key(&args).await;
        let status = section_status(&self.cache, &key, &section).await;
        let fingerprint = status
            .source_fingerprint
            .clone()
            .unwrap_or_else(|| key.fingerprint.clone());
        let mut body = to_value(&status)?;
        if let Value::Object(map) = &mut body {
            map.insert("asOfDate".to_owned(), json!(key.as_of));
            map.insert("windowKey".to_owned(), json!(key.window_key.as_str()));
            map.insert("sourceFingerprint".to_owned(), json!(fingerprint));
        }
        Ok(body)
    }

    pub async fn sections_queue(&self, arguments: Map<String, Value>) -> Result<Value, Error> {
        let args: WindowArgs = args::parse(arguments)?;
        let key = self.key(&args).await;
        let requested = normalize_sections(args.sections.as_deref(), &SECTION_KEYS);
        let queued = queue(&self.cache, &key, &requested, QueueMode::Missing).await;
        self.spawn_sections(key.clone(), queued.clone());
        Ok(json!({
            "accepted": true,
            "asOfDate": key.as_of,
            "windowKey": key.window_key.as_str(),
            "queued": queued,
            "sourceFingerprint": key.fingerprint,
        }))
    }

    pub async fn sections_invalidate(&self, arguments: Map<String, Value>) -> Result<Value, Error> {
        let args: WindowArgs = args::parse(arguments)?;
        let key = self.key(&args).await;
        let requested = normalize_sections(args.sections.as_deref(), &SECTION_KEYS);
        let queued = queue(&self.cache, &key, &requested, QueueMode::Regenerate).await;
        self.spawn_sections(key.clone(), queued.clone());
        Ok(json!({
            "accepted": true,
            "invalidated": requested,
            "queued": queued,
            "asOfDate": key.as_of,
            "windowKey": key.window_key.as_str(),
            "sourceFingerprint": key.fingerprint,
        }))
    }

    pub async fn regenerate(&self, arguments: Map<String, Value>) -> Result<Value, Error> {
        let mut args: WindowArgs = args::parse(arguments)?;
        if args.window.is_none() {
            args.window = args
                .windows
                .as_ref()
                .and_then(|windows| windows.first().cloned());
        }
        let key = self.key(&args).await;
        let requested = normalize_sections(args.sections.as_deref(), &SECTION_KEYS);
        let queued = queue(&self.cache, &key, &requested, QueueMode::Regenerate).await;
        self.spawn_sections(key.clone(), queued.clone());
        Ok(json!({
            "success": true,
            "accepted": true,
            "asOfDate": key.as_of,
            "windowKey": key.window_key.as_str(),
            "queued": queued,
            "generatedAt": timestamp(),
            "windowsRegenerated": 1,
        }))
    }

    pub async fn bundle(&self, arguments: Map<String, Value>) -> Result<Value, Error> {
        let args: WindowArgs = args::parse(arguments)?;
        let key = self.key(&args).await;
        let refresh = args.refresh.unwrap_or(false);
        if !refresh
            && let Some(Value::Object(mut saved)) = self
                .cache
                .read::<Value>(&key.athlete, &key.bundle_record())
                .await
        {
            saved.insert("cached".to_owned(), json!(true));
            return Ok(Value::Object(saved));
        }
        let loaded = self
            .load(&key.athlete, &Window::default(), Scope::Block("current"))
            .await?;
        let as_of = parse_date(&key.as_of).unwrap_or_else(|| self.clock.today());
        let windows = windows::build(&loaded.program, as_of)?;
        let env = self.env(&loaded);
        let mut results = Map::new();
        for window_key in ALL_WINDOWS {
            let window = &windows[&window_key];
            let params = window_params(window, &key.as_of);
            results.insert(
                window_key.as_str().to_owned(),
                Value::Object(sections::compute_all(env, &loaded.program, &params)?),
            );
        }
        let bundle = json!({
            "schemaVersion": CACHE_SCHEMA_VERSION,
            "asOfDate": key.as_of,
            "generatedAt": timestamp(),
            "cached": false,
            "windows": to_value(&windows)?,
            "results": results,
        });
        self.cache
            .write(&key.athlete, &key.bundle_record(), &bundle, false)
            .await;
        Ok(bundle)
    }

    pub async fn weekly(&self, arguments: Map<String, Value>) -> Result<Value, Error> {
        let args: WeeklyArgs = args::parse(arguments)?;
        let loaded = self
            .load(&args.pk, &Window::default(), Scope::Everything)
            .await?;
        let params = Params {
            weeks: args.weeks.max(1),
            block: Some(args.block.clone()),
            window_start: args.window_start.filter(|text| !text.is_empty()),
            window_end: args.window_end.filter(|text| !text.is_empty()),
            ref_date: args.ref_date.filter(|text| !text.is_empty()),
            week_start: args.week_start.filter(|week| *week > 0),
            week_end: args.week_end.filter(|week| *week > 0),
        };
        sections::compute_all(self.env(&loaded), &loaded.program, &params).map(Value::Object)
    }

    fn spawn_sections(&self, key: AnalysisKey, sections: Vec<String>) {
        if sections.is_empty() {
            return;
        }
        let engine = self.clone();
        tokio::spawn(async move {
            if let Err(error) = engine.run_sections(&key, &sections).await {
                tracing::error!(%error, "analysis section run failed");
                for section in &sections {
                    let failed = SectionStatus::failed(section, error.to_string());
                    engine
                        .cache
                        .write(&key.athlete, &key.section_record(section), &failed, false)
                        .await;
                }
            }
        });
    }

    async fn run_sections(&self, key: &AnalysisKey, requested: &[String]) -> Result<(), Error> {
        let loaded = self.current_program(key).await?;
        let as_of = parse_date(&key.as_of).unwrap_or_else(|| self.clock.today());
        let windows = windows::build(&loaded.program, as_of)?;
        let today = self.clock.today();
        let work_key = key.clone();
        let work_sections = requested.to_vec();
        let statuses = tokio::task::spawn_blocking(move || {
            let env = Env {
                today,
                glossary: &loaded.glossary,
            };
            work_sections
                .iter()
                .map(|section| compute_status(env, &loaded, &windows, &work_key, section))
                .collect::<Vec<_>>()
        })
        .await
        .map_err(|error| Error::Internal(error.to_string()))?;
        for status in statuses {
            self.cache
                .write(
                    &key.athlete,
                    &key.section_record(&status.section_key),
                    &status,
                    false,
                )
                .await;
        }
        Ok(())
    }
}

fn window_params(window: &windows::Window, as_of: &str) -> Params {
    Params {
        weeks: window.weeks,
        block: Some("current".to_owned()),
        window_start: Some(window.start.clone()),
        window_end: Some(window.end.clone()),
        ref_date: Some(as_of.to_owned()),
        week_start: Some(window.week_start),
        week_end: Some(window.week_end),
    }
}

fn compute_status(
    env: Env<'_>,
    loaded: &Loaded,
    windows: &Windows,
    key: &AnalysisKey,
    section: &str,
) -> SectionStatus {
    let window = &windows[&key.window_key];
    let outcome: Result<Value, Error> = if DETERMINISTIC.contains(&section) {
        sections::compute(
            env,
            &loaded.program,
            section,
            &window_params(window, &key.as_of),
        )
    } else if section == "ai_correlation" && window.weeks < 4 {
        Ok(json!({
            "insufficient_data": true,
            "insufficient_data_reason": "Correlation analysis requires at least 4 weeks of data.",
            "cache_miss": false,
        }))
    } else if section == "program_evaluation" && key.window_key != WindowKey::Block {
        Ok(json!({
            "insufficient_data": true,
            "insufficient_data_reason": "Program evaluation is only available for the full block.",
            "cache_miss": false,
        }))
    } else {
        Err(Error::NotImplemented(AI_PENDING))
    };
    match outcome {
        Ok(payload) => SectionStatus::complete(section, &key.fingerprint, payload),
        Err(error) => SectionStatus::failed(section, error.to_string()),
    }
}
