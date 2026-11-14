# AI reports in S3, not DynamoDB

## Why

Caches and stored results belong in S3 or Valkey, never DynamoDB. analytics-ai
stores AI report generations (correlation / ROI, program evaluation, block
comparison, any other generation) in the DynamoDB table
`if-powerlifting-analysis-cache` through `internal/generation/dynamo.go`.
The design: after the calculations, the finished report is saved to S3, and
Valkey holds the fast pointer and the in-flight state.

## Design

- Finished report: S3 object in the existing powerlifting bucket
  (`POWERLIFTING_S3_BUCKET`, already used by the analytics snapshot store),
  key `analysis-reports/{athlete}/{generation_id}.json`. Body: the full record
  the Dynamo item holds today (status, operation, result, requirements,
  owner, timestamps).
- Valkey:
  - `pl:report:{athlete}:{generation_id}` -> small JSON pointer
    `{status, s3_key, operation, requirements, updated_at}`. Terminal records
    point at S3; in-flight records carry status only.
  - Reservation (today's conditional put in `Reserve`): `SET NX` on the
    pointer key with a TTL equal to today's in-flight timeout; retry semantics
    unchanged.
  - Pointer TTL: none for terminal records (LRU eviction like other analysis
    keys). If the pointer is missing, read S3 directly at the known key; if S3
    has it, restore the pointer.
- `generation_id` and its identity stay as computed today in
  `internal/generation/identity.go`, which keys on the athlete
  `analysis_version`, so a data write already invalidates. Do not add any
  hardcoded version constant.
- Requirements check on read (persisted source domains vs current
  permissions) stays exactly as today, reading requirements from the pointer
  or the S3 body.
- Read-only cache misses never start inference (unchanged).

## Code

- `src/services/analytics-ai/internal/generation`: replace `dynamo.go` with an
  S3 + Valkey store implementing the same store interface (`Get`, `Reserve`,
  and the rest of what `store.go` / `backend.go` use). Keep `memory.go` for
  tests. Reuse the S3 client pattern from analytics-export or analytics if one
  exists in Go; otherwise aws-sdk-go-v2 s3.
- `internal/config/config.go`: drop `ANALYSIS_CACHE_TABLE_NAME`; add the bucket
  (`POWERLIFTING_S3_BUCKET`) and prefix.
- Anything else in the repo reading `if-powerlifting-analysis-cache`
  (grep for the table name and `ANALYSIS_CACHE_TABLE_NAME`): move to the new
  store or remove the reference.

## Terraform

- Remove `ANALYSIS_CACHE_TABLE_NAME` env from analytics-ai (and anywhere else),
  add the bucket env, and give analytics-ai's AWS credentials S3 read/write on
  the `analysis-reports/` prefix (follow how analytics gets snapshot bucket
  access).
- Do NOT remove the `aws_dynamodb_table.if_powerlifting_analysis_cache`
  resource: removing it would make the pipeline destroy the table. The
  operator deletes it after cutover.

## Cutover

Existing Dynamo records are not migrated. Reports regenerate on next request
(the owner triggers; visitors only read cached).

## Tests

No new test suites. Run existing `go test ./internal/generation/...` and any
package you change in analytics-ai; update existing tests minimally. `go vet`.
`terraform fmt` + `terraform validate` in the stacks you change.
