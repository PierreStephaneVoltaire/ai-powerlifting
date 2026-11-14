# Sessions, Program, Competition: Go rewrite

Subagents read this file as their spec. Model: the analytics rewrite
(`2026-11-11-analytics-rankings-rewrite.md`) — same rules, same Go stack.

## Execution rules

- Sonnet subagents do all the work; Opus only orchestrates.
- **Fresh rewrite, not a transliteration.** Read the Python to learn the
  behaviour and the wire contract, then design idiomatic Go: typed request/result
  structs, a small store layer, pure functions for calculation. Do not port
  Python helper-by-helper, do not reproduce dead branches or legacy shims that no
  caller exercises (check callers before keeping a compat path).
- Go builds/tests are serialized and memory-capped:
  `flock /tmp/claude-1000/go-build.lock systemd-run --user --scope -p MemoryMax=6G -p MemorySwapMax=0 --quiet -- env GOFLAGS=-p=3 <go cmd>`.
- No git writes. Only the pipeline applies changes. `terraform fmt/validate` only.
- Tests are offline and scoped to the module you changed (`go test ./...` inside
  that one Go module is fine; never the whole repo, never `*_live*`). Nothing is
  ever written to a live table. No AWS credentials in tests.
- No code comments (project rule 6). Unrelated bugs → `bug.md`; stuck >4 cycles →
  `HANDOFF.md` and move on.

## 1. Services

| Service (unchanged k8s name) | Go module dir | Ops (from `operations/<x>.json`) |
|---|---|---|
| `pl-sessions` (2 replicas) | `src/services/sessions-go/` | `operations/sessions.json` (10 ops) |
| `pl-program` | `src/services/program-go/` | `operations/program.json` (18 ops, incl. `export_program_markdown`, `health_setup_initialize`) |
| `pl-competition` | `src/services/competition-go/` | `operations/competition.json` (5 ops) |

Service names, ports (HTTP :8000, route `POST /operations/<op>`, `POST /mcp`) and
the `operations/*.json` contracts are unchanged, so the backend, coach, Discord
and other services need no caller changes. All ops are `deterministic`,
`ownership: athlete` — no AI, no Codex, no Person gate (same lesson as analytics:
Python only requires a Person for `ownership: person`).

No gRPC unless a caller actually needs it (none do today) — HTTP + MCP only.

## 2. Wire and data compatibility (the hard requirement)

These services share DynamoDB items and Valkey keys with code that is **not**
being rewritten: Python `runtime/program_store.py`, `runtime/session_store.py`,
`runtime/competition_entries.py` (used by templates, performance, export,
lift_profiles, profile_views, handler_context), the Node backend, the coach, and
Rust `pl-analytics`. Therefore:

- Dynamo item shapes (pk/sk formats, attribute names, version/`current` pointer
  semantics, session ids/ordinals, list ordering) must be byte-for-byte what the
  Python stores read and write. Numbers go to Dynamo as numbers (no floats lost;
  use `attributevalue` with care for ints vs decimals). Read
  `runtime/program_store.py` and `runtime/session_store.py` fully before writing
  the store layer.
- Valkey program cache: every write must invalidate/refresh exactly the keys the
  Python store does (same key strings, same TTL behaviour), so Python and Rust
  readers never see stale data. Find keys in `runtime/program_store.py`,
  `runtime/valkey.py`, and `health_invalidate_program_cache`.
- JSON results must match Python's output shape for every op (field names,
  null vs absent, number formatting — see `analytics-ai/internal/pyjson` for the
  Decimal/float rendering helper; reuse the approach).
- Golden parity: before writing Go, capture Python outputs for each op against an
  in-memory/moto-style fake or fixtures (offline), store them in the session
  scratchpad (not the repo), and assert the Go output matches them in tests that
  use checked-in fixtures under `<module>/testdata/`.

## 3. Auth and communication

Identical to `analytics-export` / `analytics-ai` (mesh model, `app.py:call`
check order): `X-Person-Pk`, `X-Athlete-Pk`, `X-PL-Source-Principal`; generation
without job → 403; unknown op → 404; reserved args → 403; `internal_only`
requires the backend source account; scope arguments; validate input with the
op's `input_schema`; run; validate output against `result_schema`. Copy and
adapt `analytics-export/internal/{auth,contract,apperr,serve}` — each module owns
its own copy (that is the existing convention; no shared Go module).
`operations.json` and `permissions.json` are embedded via `go:generate` copies
from `operations/<x>.json` and `runtime/permissions.json`, as analytics does.

## 4. Go stack

`huma/v2` on `chi` (Swagger at `/docs`, plus a test that every op is
documented), `santhosh-tekuri/jsonschema/v6`, `aws-sdk-go-v2`, `go-redis/v9`,
`slog`. Health `/healthz`. Distroless non-root, `GOMEMLIMIT` under the pod limit.
Match `analytics-export/main.go` structure and env/config names.

Program-specific: `export_program_markdown` renders markdown with
`text/template`; `FORMULA_REFERENCE` (used by Python
`templates/template_evaluate`) must stay available to Python — see Phase D.
`health_setup_initialize` applies a template: implement the needed template
read/apply logic natively in program-go (read-only on template items; the
Python templates domain keeps its own code).

## Phases

- [ ] **A. Build (parallel, one agent per module).** Goldens, Go module,
  handlers, store, tests green offline, `go vet`, `gofmt`. Each agent touches
  only its own `<domain>-go/` dir (and `bug.md`/`HANDOFF.md`).
- [ ] **B. Deploy artifacts (single agent, after A).**
  - Packer: `powerlifting-sessions.pkr.hcl`, `powerlifting-program.pkr.hcl`,
    `powerlifting-competition.pkr.hcl` modelled on
    `powerlifting-analytics-export.pkr.hcl`; the services image excludes the
    new Go dirs.
  - ECR repos / `var.repositories`, `.github/workflows` build matrix,
    `.github/image-filters.yml`, rollout list.
  - Terraform: remove `pl-sessions`, `pl-program`, `pl-competition` from the
    Python `services.tf` map; new `sessions.tf`, `program.tf`,
    `competition.tf` (one file per service, 128Mi, pl-sessions 2 replicas),
    keeping Service names, ports, service accounts, mesh callers and
    `cache_callers` (Valkey) equivalent to today. `fmt` + `validate` only.
- [ ] **D. Delete legacy Python (single agent, after B).**
  - Carve-out first: move `FORMULA_REFERENCE` into
    `templates/template_evaluate/` (or `runtime/`), and give
    `export/export_program_history` its own read of the program (via
    `runtime/program_store.py`, not the deleted `services.program`).
  - Delete `src/services/{sessions,program,competition}/` Python packages and
    their tests; `contract.py` handler optional for these domains;
    `test_handler_imports` skips them. Keep `runtime/*_store.py` (still used).
  - Grep: no imports of the deleted packages remain. Run only the scoped tests of
    the files touched.
- [ ] **E. Verify (operator / after pipeline).** Pods Running within limits, no
  403s, UI: log a session, edit program meta/phases, block notes, diet notes,
  supplements, competitions list, attempt calculator, export program markdown,
  new block / setup.
