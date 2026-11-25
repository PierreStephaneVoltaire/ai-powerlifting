# Remove program versioning from Dynamo

The operator wants no code that writes or reads program "versions" in DynamoDB.
Existing prod items keep their shape and keys; code simply stops reading or writing the
version-related attributes. No migration, no deletes, no prod writes from this work.

## Prod facts (read-only scan of `if-health`, 2026-11-24)

- 4 athletes, each with a `program#current` pointer. Pointer `ref_sk` values look like
  `program#v023-<hex>`. Those SKs stay as opaque identifiers.
- `max_history#current` x3, `weight_log#current` x1 (operator, live), plus a stale
  `weight_log#v001` (operator, 1 entry, 2026-03). `#current` is canonical; v001 is ignored.
- Session SKs embed the program SK: `session#{program_sk}#{date}#{ord:03d}#{id}`. Because
  the program SK never changes again, existing sessions stay attached.

## Target model

| Concept | Before | After |
|---|---|---|
| Locate the program | pointer `ref_sk`, else rebuild from max `program#vNNN`, else `program#v001` | pointer `program#current.ref_sk` only. No pointer means program not found (setup creates one). No prefix scans, no `v001` fallbacks. |
| Pointer attributes | `version, ref_sk, updated_at, current_block_id` | write/read `ref_sk, updated_at, current_block_id` only. Never read or write `version`. |
| New program (setup) | `program#v001-<hex>`, `published=true`, pointer `version=1` | `program#<hex>`, no `published`, pointer without `version` |
| Transition / import apply / template apply | new `program#vNNN+1` item + copy all sessions + publish swap | **in-place** save to `loaded.SK` (see below) |
| `published` flag | draft flag during publish | gone: not written, not read, not filtered |
| `meta.version_label` | incremented on new version, displayed in export/markdown, whitelisted in public view, user-patchable | never written or displayed. Remove from allowed-meta, public whitelist, markdown/workbook output. Existing values pass through `meta` untouched. |
| Session `program_version`, `program_version_number` | written on every session item | not written. **Keep** these two names in the internal-field strip lists so old items don't leak them (the only accepted remaining reference). |
| `weight_log#{version}`, `max_history#{version}` + item `version` field | from arg/pointer, `v%03d` in export | fixed `weight_log#current` / `max_history#current`, no `version` attribute written |
| `version` / `program_sk` selector args on operations | select an old program item | removed. Operations always act on the current program. |
| `health_new_version` permission/op | exists | removed everywhere (permissions.json copies, access checks, analysis-version op lists) |
| Results `new_version`, `program_version` | returned | removed from code and result schemas |
| Export "Version" / "Version Label" rows, `vNNN` labels | shown | removed |

Out of scope, do not touch: the Valkey `pl:analysis-version:{athlete}` counter
(`runtime/analysis_version.py` except removing the `health_new_version` op name,
`*/store/versions.go`, `Cache.Version`), template `published` (template library),
`derived_from_program_sk` lineage, crate/package/API versions, the
`fixtures/operator/**` prod snapshot data, `scripts/migrate_supplements.py` (one-off).
Never add or bump any cache/schema version constant.

## In-place save (replaces `WriteNewVersion` / `PublishVersion`)

Go `store.Programs.Save(ctx, athlete, program, loaded) (*Written, error)`:

1. Validate session identities (as today).
2. Build the program item from `program` minus `sessions`; persist supplements
   against `loaded.SK` exactly as `Commit` does (supplements table split); set
   `meta.updated_at`, `pk`, `sk = loaded.SK`.
3. One `TransactWriteItems` (new DB method replacing `PublishVersion`, e.g. `SaveProgram`):
   - Put the program item.
   - Update the pointer: `SET current_block_id = :block, updated_at = :now`,
     condition `ref_sk = :expected` (`loaded.SK`) — keeps the optimistic guard.
   - If `loaded.ImportID != ""`: the existing import-claim `ConditionCheck`.
4. Sync sessions for `loaded.SK`: build items with the existing `buildItem`, `BatchPut`
   them, then query existing `session#{loaded.SK}#` keys and `BatchDelete` the keys not in
   the new set. Put before delete.
5. Return `Written{Program, SK: loaded.SK}`.

Memory DB fake gets the same method. Delete `NextVersionLabel`, `ListVersions`,
`rebuildPointer`, `VersionSK` (callers use the pointer `ref_sk`), `Loaded.Version`,
`published()`, `WriteNewVersion`, `PublishVersion`.

Python `ProgramStore` mirrors this: `_write_new_version*` becomes an in-place save to
the pointer's `ref_sk` (conditional pointer update of `current_block_id`/`updated_at`,
`replace_program_sessions_sync(ref_sk, ...)` must delete stale sessions); remove
`new_version()` and its patch validator if nothing but itself uses them (check coach
tools); remove the prefix-scan pointer rebuild and `_cache_version`.

## Work split (parallel, disjoint files)

- **A: program service (Go)** — `src/services/program/**`, `src/services/operations/program.json`.
  Store rewrite above; ops `transition.go`, `import_apply.go` (drop `new_version` result),
  `template_apply.go`, `setup.go` (`WriteInitial` SK `program#<hex>`, remove dead
  `"sk":"program#v001"`), `export.go` (no `vNNN`, `weight_log#current`, `max_history#current`),
  `reads.go`, `mutate.go` (no `program_sk` selector), `markdown/build.go` (no Version line),
  `analysis/analysis.go` (`health_new_version`), contract json (`new_version`, selectors,
  `version` args, `health_new_version` in permissions.json).
- **B: Go readers** — `src/services/{sessions,templates,competition,lift_profiles,profile,glossary}/**`
  and their `src/services/operations/*.json`. Pointer-only lookups, drop `published`,
  prefix scans, `v001` fallbacks, `program_version*` writes, `version`/`program_sk`
  selector args, `competition_snapshot` `version` arg, templates `program_version` result,
  `health_new_version` in their permissions.json and `profile/internal/access/check.go`.
- **C: Go export/performance/weight_log** — `src/services/{export,performance,weight_log}/**`
  and `src/services/operations/{export,performance,weight-log,rankings}.json` (rankings: just
  the `version` arg if it maps to a Dynamo key; check `src/services/rankings` first). Fixed
  `#current` keys, no `version` attr, hydration pointer-only, no `published`, no Version rows,
  `version_label` out of public view whitelist, `health_new_version` out of their permissions.json.
- **D: Python + Rust + types** — `src/services/runtime/**`, `src/services/videos/**`,
  `src/services/coach*/**` (only if they call removed APIs), `src/lambda/video-thumbnail`,
  `src/services/operations/{videos,imports}.json`, `src/services/imports/**` (Rust: pointer-only,
  no `published`, drop `new_version` result validation), `src/dependencies/types/index.ts`
  (`version_label`, `ProgramListItem`), all remaining `*/internal/contract/permissions.json`
  `health_new_version` entries not covered by A–C.

## Verification

- Per changed Go package: `go build ./...` and `go test ./internal/<changed pkg>/...` in that
  service only. Python: only the touched test files, offline, no AWS creds. Rust imports:
  `cargo check -j2` then `cargo test -j2` in `src/services/imports`; `cargo clean` afterwards
  (node disk is shared). Frontend/types: `tsc --noEmit` in the affected package.
- Tests: delete tests of removed behaviour (`NextVersionLabel`, publish swap, unpublished
  filtering, newest-version fallbacks); minimally fix the rest. No new tests.
- Final grep for `version_label|program_version|ListVersions|NextVersionLabel|PublishVersion|program#v|published|new_version|health_new_version`
  across `src/services` (excluding template `published`, strip lists, fixtures, out-of-scope
  items) must be empty.
