# Cache invalidation without version constants

## Why

Caches invalidate outdated entries; they are never busted by bumping a
hardcoded version in the key. Data changes already invalidate: input writes
bump `pl:analysis-version:{athlete}` in Valkey (`runtime/analysis_version.py`,
`record_write` from `dispatch`) and analysis keys include that version. Two
problems remain:

1. Rust analytics keys and the S3 snapshot path embed hardcoded constants
   (`CACHE_SCHEMA_VERSION`, `SECTION_CACHE_SCHEMA_VERSION`,
   `BLOCK_INDEX_SCHEMA_VERSION`, and any similar constant used in a cache key
   or object path), which were bumped by hand when computation changed.
2. `record_write(operation_name, arguments.get("pk"))` bumps the version for
   whatever `pk` the operation received. For person-scoped writes (settings)
   that is the person (`sir_simpalot`), not the mapped athlete (`operator`),
   so the athlete's analysis is not invalidated.

## Design

### Code changes invalidate by build

- analytics reads its build id from env `BUILD_ID` (set by Terraform from the
  deployed image tag/digest; find how analytics.tf passes the image).
- On startup, analytics reads `pl:analysis-build` from Valkey. If it differs
  from `BUILD_ID`, it deletes its own keys (`SCAN` + `UNLINK` on
  `pl:analysis:*`, batched) and then sets `pl:analysis-build`. Only one
  replica should do the sweep: guard with `SET pl:analysis-build-sweep NX EX 300`.
  Missing `BUILD_ID` (local/tests) = no sweep.
- Remove the version constants from every cache key and from the snapshot S3
  path in `snapshots.rs`. Snapshots carry the build id in their JSON body; a
  read whose build id differs from the current one is treated as missing and
  recomputed.
- API response fields named `schemaVersion` are read by the frontend
  (`src/frontend/src/api/analytics.ts`). Keep those fields in responses; they
  are not cache keys. If a constant is only used for that field, it may stay as
  a response value but must not appear in any key or path.

### Data changes invalidate the mapped athlete

- `dispatch` already knows the resolved athlete for the call (the
  `X-Athlete-Pk` / storage scope the operation runs under). `record_write`
  bumps that athlete, not `arguments["pk"]`. Do not add a user lookup or scan.
- Keep the `ANALYSIS_INPUT_WRITES` allowlist.

## Tests

No new tests. Update existing assertions that hardcode versioned keys
(`block_ops.rs`, `cache.rs`, `windows.rs`, snapshot tests) minimally. The
parity goldens `fixtures/operator/golden/analytics.blocks_get__*.json` are
stale since `0ae41570`; regenerate them offline only (local moto + read-only
snapshot, never live services or prod writes) if the repo has a regeneration
script; otherwise leave them and report. Run `cargo test -j2 --lib`,
`cargo test -j2 --test parity`, `cargo test -j2 --test grpc`, then
`cargo clean`. Python: existing tests covering `dispatch.py` /
`analysis_version.py`, offline.
