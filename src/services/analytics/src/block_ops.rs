use std::collections::{BTreeMap, BTreeSet};

use serde_json::{Map, Value, json};

use crate::args::{self, BlockArgs, CompareArgs, LifetimeArgs, PkArgs};
use crate::assemble::{Loaded, Scope};
use crate::blocks::goals::normalize_all;
use crate::blocks::scope::scoped_entry;
use crate::blocks::types::{BlockEntry, Bundle};
use crate::blocks::{self, Workspace, bundle, index};
use crate::calc::Env;
use crate::compare;
use crate::engine::{Engine, to_value};
use crate::error::Error;
use crate::lifetime;
use crate::records::timestamp;
use crate::source::Window;
use crate::windows::CACHE_SCHEMA_VERSION;

const BLOCK_INDEX_SCHEMA_VERSION: i64 = 2;

pub fn workspace(loaded: &Loaded, today: chrono::NaiveDate) -> Workspace<'_> {
    Workspace {
        program: &loaded.program,
        weight_log: &loaded.weight_log,
        goals: normalize_all(&loaded.goals),
        today,
    }
}

fn index_key(version: &str) -> String {
    format!("native_block_index#{CACHE_SCHEMA_VERSION}#{BLOCK_INDEX_SCHEMA_VERSION}#{version}")
}

fn view_key(block_key: &str, version: &str) -> String {
    format!("native_block_view#{CACHE_SCHEMA_VERSION}#{block_key}#{version}")
}

fn bundle_key(block_key: &str, tail: &str) -> String {
    format!("native_block#{CACHE_SCHEMA_VERSION}#{block_key}#{tail}")
}

fn lifetime_key(version: &str) -> String {
    format!("native_lifetime#{version}")
}

fn mark_cached(mut saved: Value) -> Value {
    if let Some(map) = saved.as_object_mut() {
        map.insert("cached".to_owned(), Value::Bool(true));
    }
    saved
}

impl Engine {
    async fn everything(&self, athlete: &str) -> Result<Loaded, Error> {
        self.load(athlete, &Window::default(), Scope::Everything)
            .await
    }

    pub async fn bundle_for(
        &self,
        workspace: &Workspace<'_>,
        env: Env<'_>,
        athlete: &str,
        raw: &BlockEntry,
        refresh: bool,
        cache_only: bool,
    ) -> Result<Option<Bundle>, Error> {
        let entry = scoped_entry(workspace, raw);
        let cache_key = bundle_key(&raw.block_key, &entry.source_fingerprint);
        let latest_key = bundle_key(&raw.block_key, "latest");
        if !(refresh && !cache_only) {
            let mut saved = self.cache.read::<Bundle>(athlete, &cache_key).await;
            if saved.is_none() && cache_only {
                saved = self.cache.read::<Bundle>(athlete, &latest_key).await;
            }
            if let Some(mut saved) = saved {
                saved.block.label = entry.label.clone();
                saved.block.is_current = entry.is_current;
                saved.cached = true;
                return Ok(Some(saved));
            }
        }
        if cache_only {
            return Ok(None);
        }
        let computed = tokio::task::block_in_place(|| bundle::compute(workspace, env, raw))?;
        self.cache.write(athlete, &cache_key, &computed, false).await;
        self.cache.write(athlete, &latest_key, &computed, false).await;
        Ok(Some(computed))
    }

    pub async fn blocks_list(&self, arguments: Map<String, Value>) -> Result<Value, Error> {
        let args: PkArgs = args::parse(arguments)?;
        let version = self.cache.version(&args.pk).await;
        let key = index_key(&version);
        if let Some(saved) = self.cache.read::<Value>(&args.pk, &key).await {
            return Ok(saved);
        }
        let loaded = match self.everything(&args.pk).await {
            Ok(loaded) => loaded,
            Err(Error::NotFound(_)) => return Ok(json!([])),
            Err(error) => return Err(error),
        };
        let entries = index::build(&workspace(&loaded, self.clock.today()));
        let value = to_value(&entries)?;
        self.cache.write(&args.pk, &key, &value, false).await;
        Ok(value)
    }

    pub async fn blocks_get(&self, arguments: Map<String, Value>) -> Result<Value, Error> {
        let args: BlockArgs = args::parse(arguments)?;
        let refresh = args.refresh.unwrap_or(false);
        let cache_only = args.cache_only.unwrap_or(false);
        let version = self.cache.version(&args.pk).await;
        let view = view_key(&args.block_key, &version);
        if !(refresh && !cache_only)
            && let Some(saved) = self.cache.read::<Value>(&args.pk, &view).await
        {
            return Ok(mark_cached(saved));
        }
        let loaded = self.everything(&args.pk).await?;
        let workspace = workspace(&loaded, self.clock.today());
        let entries = index::build(&workspace);
        let raw = entries
            .iter()
            .find(|entry| entry.block_key == args.block_key)
            .ok_or_else(|| Error::CacheMiss(format!("Block {} not found", args.block_key)))?;
        let env = self.env(&loaded);
        let bundle = self
            .bundle_for(&workspace, env, &args.pk, raw, refresh, cache_only)
            .await?
            .ok_or_else(|| Error::CacheMiss(format!("Block {} not cached", args.block_key)))?;
        let value = to_value(&bundle)?;
        self.cache.write(&args.pk, &view, &value, false).await;
        Ok(value)
    }

    pub async fn blocks_regenerate(
        &self,
        arguments: Map<String, Value>,
        person: &str,
    ) -> Result<Value, Error> {
        let args: BlockArgs = args::parse(arguments)?;
        let loaded = self.everything(&args.pk).await?;
        let workspace = workspace(&loaded, self.clock.today());
        let entries = index::build(&workspace);
        let raw = entries
            .iter()
            .find(|entry| entry.block_key == args.block_key)
            .ok_or_else(|| Error::NotFound(format!("Block {} not found", args.block_key)))?;
        let env = self.env(&loaded);
        let bundle = self
            .bundle_for(&workspace, env, &args.pk, raw, true, false)
            .await?
            .ok_or_else(|| Error::NotFound(format!("Block {} not found", args.block_key)))?;
        let version = self.cache.version(&args.pk).await;
        let view = to_value(&bundle)?;
        self.cache
            .write(&args.pk, &view_key(&args.block_key, &version), &view, false)
            .await;
        let regenerated = self.ai.regenerate(&args.pk, person, &args.block_key).await;
        Ok(json!({
            "success": true,
            "blockKey": args.block_key,
            "generatedAt": timestamp(),
            "correlationRegenerated": regenerated.as_ref().is_some_and(|result| result.correlation_regenerated),
            "evaluationRegenerated": regenerated.as_ref().is_some_and(|result| result.evaluation_regenerated),
        }))
    }

    pub async fn compare_blocks(&self, arguments: Map<String, Value>) -> Result<Value, Error> {
        let args: CompareArgs = args::parse(arguments)?;
        let loaded = self.everything(&args.pk).await?;
        let workspace = workspace(&loaded, self.clock.today());
        let entries = index::build(&workspace);
        let requested = args.block_keys.unwrap_or_default();
        let mut selected: BTreeSet<String> = if requested.is_empty() {
            entries
                .iter()
                .filter(|entry| !entry.is_current)
                .map(|entry| entry.block_key.clone())
                .collect()
        } else {
            requested.into_iter().collect()
        };
        if let Some(current) = entries.iter().find(|entry| entry.is_current) {
            selected.insert(current.block_key.clone());
        }
        let env = self.env(&loaded);
        let mut bundles = Vec::new();
        let mut contexts = BTreeMap::new();
        for raw in entries.iter().filter(|entry| selected.contains(&entry.block_key)) {
            let scoped = scoped_entry(&workspace, raw);
            contexts.insert(
                scoped.block_key.clone(),
                compare::context::build(&workspace, raw),
            );
            if let Some(bundle) = self
                .bundle_for(&workspace, env, &args.pk, raw, scoped.is_current, false)
                .await?
            {
                bundles.push(bundle);
            }
        }
        let comparison = compare::build(&bundles, Vec::new(), &contexts);
        to_value(&comparison)
    }

    pub async fn lifetime_report(&self, arguments: Map<String, Value>) -> Result<Value, Error> {
        let args: LifetimeArgs = args::parse(arguments)?;
        let refresh = args.refresh.unwrap_or(false);
        let version = self.cache.version(&args.pk).await;
        let key = lifetime_key(&version);
        if !refresh && let Some(saved) = self.cache.read::<Value>(&args.pk, &key).await {
            return Ok(saved);
        }
        if args.cache_only.unwrap_or(false) {
            return Err(Error::CacheMiss("Lifetime report is not cached".to_owned()));
        }
        let report = self.compute_lifetime(&args.pk).await?;
        let value = to_value(&report)?;
        self.cache.write(&args.pk, &key, &value, false).await;
        Ok(value)
    }

    pub async fn compute_lifetime(&self, athlete: &str) -> Result<lifetime::types::Lifetime, Error> {
        let loaded = self.everything(athlete).await?;
        let workspace = workspace(&loaded, self.clock.today());
        let entries = index::build(&workspace);
        let env = self.env(&loaded);
        let mut bundles = Vec::new();
        for raw in &entries {
            if let Some(bundle) = self
                .bundle_for(&workspace, env, athlete, raw, raw.is_current, false)
                .await?
            {
                bundles.push(bundle);
            }
        }
        Ok(tokio::task::block_in_place(|| {
            let mut records = Vec::new();
            let mut contexts = BTreeMap::new();
            for bundle in &bundles {
                let (record, context) = lifetime::record_for(&workspace, env, bundle);
                contexts.insert(bundle.block.block_key.clone(), context);
                records.push(record);
            }
            lifetime::assemble(records, &bundles, &contexts)
        }))
    }

    pub async fn list_blocks_typed(&self, athlete: &str) -> Result<Vec<BlockEntry>, Error> {
        let loaded = self.everything(athlete).await?;
        Ok(blocks::index::build(&workspace(&loaded, self.clock.today())))
    }
}
