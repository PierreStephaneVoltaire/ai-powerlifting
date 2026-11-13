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

fn lifetime_key(version: &str, block_keys: &[String]) -> String {
    if block_keys.is_empty() {
        return format!("native_lifetime#{version}");
    }
    format!(
        "native_lifetime#{version}#{}",
        crate::js::sha1_prefix(&block_keys.join(","), 14)
    )
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

    async fn stored_bundle(&self, athlete: &str, block_key: &str) -> Option<Bundle> {
        let snapshots = self.snapshots.as_ref()?;
        match snapshots.read(athlete, block_key).await {
            Ok(body) => serde_json::from_value(body?).ok(),
            Err(error) => {
                tracing::warn!(%error, block_key, "block snapshot read failed");
                None
            }
        }
    }

    async fn store_bundle(&self, athlete: &str, bundle: &Bundle) {
        let Some(snapshots) = self.snapshots.as_ref() else {
            return;
        };
        let Ok(body) = to_value(bundle) else {
            return;
        };
        if let Err(error) = snapshots
            .write(athlete, &bundle.block.block_key, body)
            .await
        {
            tracing::warn!(%error, block_key = bundle.block.block_key, "block snapshot write failed");
        }
    }

    async fn is_stored(&self, athlete: &str, block_key: &str) -> bool {
        let Some(snapshots) = self.snapshots.as_ref() else {
            return true;
        };
        if block_key == blocks::DEFAULT_BLOCK {
            return true;
        }
        snapshots
            .list(athlete)
            .await
            .is_ok_and(|stored| stored.iter().any(|item| item.block_key == block_key))
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
        let past = !entry.is_current && self.snapshots.is_some();
        let cache_key = bundle_key(&raw.block_key, &entry.source_fingerprint);
        let latest_key = bundle_key(&raw.block_key, "latest");
        if !refresh || cache_only {
            let stored = if past {
                self.stored_bundle(athlete, &raw.block_key).await
            } else {
                None
            };
            let was_stored = stored.is_some();
            let mut saved = stored;
            if saved.is_none() {
                saved = self.cache.read::<Bundle>(athlete, &cache_key).await;
            }
            if saved.is_none() && cache_only {
                saved = self.cache.read::<Bundle>(athlete, &latest_key).await;
            }
            if let Some(mut saved) = saved {
                saved.block.label = entry.label.clone();
                saved.block.is_current = entry.is_current;
                saved.cached = true;
                if past && !was_stored {
                    self.store_bundle(athlete, &saved).await;
                }
                return Ok(Some(saved));
            }
        }
        if cache_only {
            return Ok(None);
        }
        let computed = tokio::task::block_in_place(|| bundle::compute(workspace, env, raw))?;
        self.cache
            .write(athlete, &cache_key, &computed, false)
            .await;
        self.cache
            .write(athlete, &latest_key, &computed, false)
            .await;
        if past {
            self.store_bundle(athlete, &computed).await;
        }
        Ok(Some(computed))
    }

    async fn annotate_stored(&self, athlete: &str, mut index: Value) -> Value {
        let Some(snapshots) = self.snapshots.as_ref() else {
            return index;
        };
        let stored = match snapshots.list(athlete).await {
            Ok(stored) => stored,
            Err(error) => {
                tracing::warn!(%error, "block snapshot listing failed");
                return index;
            }
        };
        for entry in index.as_array_mut().into_iter().flatten() {
            let Some(map) = entry.as_object_mut() else {
                continue;
            };
            let current = map.get("isCurrent").and_then(Value::as_bool) == Some(true);
            let found = map
                .get("blockKey")
                .and_then(Value::as_str)
                .and_then(|key| stored.iter().find(|item| item.block_key == key))
                .filter(|_| !current);
            map.insert("stored".to_owned(), Value::Bool(found.is_some()));
            map.insert(
                "storedAt".to_owned(),
                found.map_or(Value::Null, |item| Value::String(item.stored_at.clone())),
            );
        }
        index
    }

    pub async fn blocks_list(&self, arguments: Map<String, Value>) -> Result<Value, Error> {
        let args: PkArgs = args::parse(arguments)?;
        let version = self.cache.version(&args.pk).await;
        let key = index_key(&version);
        if let Some(saved) = self.cache.read::<Value>(&args.pk, &key).await {
            return Ok(self.annotate_stored(&args.pk, saved).await);
        }
        let loaded = match self.everything(&args.pk).await {
            Ok(loaded) => loaded,
            Err(Error::NotFound(_)) => return Ok(json!([])),
            Err(error) => return Err(error),
        };
        let entries = index::build(&workspace(&loaded, self.clock.today()));
        let value = to_value(&entries)?;
        self.cache.write(&args.pk, &key, &value, false).await;
        Ok(self.annotate_stored(&args.pk, value).await)
    }

    pub async fn blocks_get(&self, arguments: Map<String, Value>) -> Result<Value, Error> {
        let args: BlockArgs = args::parse(arguments)?;
        let refresh = args.refresh.unwrap_or(false);
        let cache_only = args.cache_only.unwrap_or(false);
        let version = self.cache.version(&args.pk).await;
        let view = view_key(&args.block_key, &version);
        if (!refresh || cache_only)
            && let Some(saved) = self.cache.read::<Value>(&args.pk, &view).await
            && self.is_stored(&args.pk, &args.block_key).await
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
        for raw in entries
            .iter()
            .filter(|entry| selected.contains(&entry.block_key))
        {
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
        let mut block_keys = args.block_keys.clone().unwrap_or_default();
        block_keys.sort();
        block_keys.dedup();
        let key = lifetime_key(&version, &block_keys);
        if !refresh && let Some(saved) = self.cache.read::<Value>(&args.pk, &key).await {
            return Ok(saved);
        }
        if args.cache_only.unwrap_or(false) {
            return Err(Error::CacheMiss("Lifetime report is not cached".to_owned()));
        }
        let report = self.compute_lifetime(&args.pk, &block_keys).await?;
        let value = to_value(&report)?;
        self.cache.write(&args.pk, &key, &value, false).await;
        Ok(value)
    }

    pub async fn compute_lifetime(
        &self,
        athlete: &str,
        block_keys: &[String],
    ) -> Result<lifetime::types::Lifetime, Error> {
        let loaded = self.everything(athlete).await?;
        let workspace = workspace(&loaded, self.clock.today());
        let entries = index::build(&workspace);
        let env = self.env(&loaded);
        let selecting = !block_keys.is_empty();
        let mut bundles = Vec::new();
        let mut current = None;
        for raw in &entries {
            let wanted = if selecting {
                !raw.is_current && block_keys.contains(&raw.block_key)
            } else {
                true
            };
            if selecting && raw.is_current {
                current = self
                    .bundle_for(&workspace, env, athlete, raw, true, false)
                    .await?;
            }
            if !wanted {
                continue;
            }
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
            let report = lifetime::assemble(records, &bundles, &contexts);
            match current {
                Some(bundle) => {
                    let (record, _) = lifetime::record_for(&workspace, env, &bundle);
                    lifetime::with_current(report, record)
                }
                None => report,
            }
        }))
    }

    pub async fn list_blocks_typed(&self, athlete: &str) -> Result<Vec<BlockEntry>, Error> {
        let loaded = self.everything(athlete).await?;
        Ok(blocks::index::build(&workspace(
            &loaded,
            self.clock.today(),
        )))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn lifetime_cache_key_is_versioned() {
        assert_eq!(lifetime_key("0", &[]), "native_lifetime#0");
        assert_eq!(lifetime_key("42", &[]), "native_lifetime#42");
    }

    #[test]
    fn block_cache_keys_keep_the_python_layout() {
        assert_eq!(index_key("7"), "native_block_index#5#2#7");
        assert_eq!(view_key("current", "7"), "native_block_view#5#current#7");
        assert_eq!(
            bundle_key("current", "latest"),
            "native_block#5#current#latest"
        );
    }
}
