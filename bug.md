# Bugs noticed (not chased)

## competition (Go rewrite, found while capturing Python goldens)

- `calculate_attempts` (Python): `ProgramStore.get_program()` returns raw DynamoDB `Decimal` values. `attempt_1 + j1` becomes a `Decimal`, then `/ 2.5` (float) raises `TypeError`; `current_max * 0.7` fails the same way. The op only works when `operator_prefs.attempt_jumps` and `current_maxes` are absent or the program came from a fake store. The Go version treats stored numbers as plain numbers.
- `calculate_attempts` (Python): a missing program surfaces as an unhandled `ProgramNotFoundError` (HTTP 500). Go returns 404 `not_found`.
- Python `record_write` only bumps `pl:analysis-version:<athlete>` for the operation names `health_update_user_competition` / `health_complete_user_competition`. The same mutation sent through `health_list_competitions` with `op: update|complete` never invalidates the analysis version, so cached analysis can stay stale. Go keeps that behaviour for parity; widen `analysisInputWrites` in `competition-go/internal/service/service.go` if it should bump.
- Python `ProgramStore._load_program_sync` writes a recreated `program#current` pointer when it is missing. The Go reader does not write (read-only service); it only falls back to the newest published `program#v*` item.
- Rust `meet_projection` projects bench from exercises keyed exactly `bench` (normalised name), so sessions logged as "Bench Press" contribute no bench progression slope (bench slope is always 0 for them). Go replicates it for parity with the live Rust service.

## program-go rewrite findings (Python behaviour, noted while porting `services.program`)

- `health_setup_initialize` in template mode crashes with `TypeError: unsupported operand type(s) for *: 'float' and 'decimal.Decimal'` for any template exercise with `load_type: "percentage"` and a `load_value`. `template_apply.concretize` multiplies the float max by the stored `Decimal`. The Go service computes it correctly (`round(max * load / 2.5) * 2.5`).
- `ProgramNotFoundError` (no pointer, no published version, unpublished pointer target, archive of a missing sk) is not a `ValueError`, so the Python app answers 500. The Go service answers 404 `not_found`.
- `block_transition/handler.py` serialises with `json.dumps(..., default=str)`, so every `Decimal` in the returned `program` (meta, phases, goals, ...) is a JSON string (`"squat": "180"`) while session values are numbers. The Go service reproduces this shape for wire compatibility; the callers should stop relying on `result.program` numbers or the handler should use the shared Decimal encoder.
- `_sanitize_decimals` (session store, most program handlers) uses `obj % 1 > 0`, so negative fractional Decimals are truncated to ints (`-2.5` becomes `-2`). `program_get` uses `!= 0` and keeps the fraction. Reproduced in Go.
- `block_notes_update` ignores its documented `version` argument (always writes the current program); `block_notes_get` returns "Program version ... not found" if DynamoDB returns no Item for the nested projection.
- `export_program_markdown`: the analysis bundle always sets `correlation` and `program_evaluation` to `None`, so `_md_correlation`, `_md_program_evaluation` and the glossary fetch are dead code in the markdown path. Table cells render Dynamo `Decimal` values through `float()` (`220` becomes `220.0`) but session and weight-log values are already int/float, so the same quantity prints differently depending on its source. Reproduced in Go.

## profile rewrite findings (Python behaviour, noted while porting `services.profile`)

- `grant_list` with `athlete_mapped_pk` answers 500 `invalid_result` whenever the athlete has any `peer` grant: the result schema restricts `grant_type` to `coach|handler`, `normalize_grant` returns `peer`. Go reproduces it (the contract is unchanged).
- `profile_get` / `profile_get_current` raise `AttributeError` (HTTP 500) when a stored `tags` entry is a plain string and the athlete has a program: `profile_get/core.py::_public_profile` calls `.get("approved")` on every entry. `selected_tags` accepts strings everywhere else. Go tolerates both shapes.
- `master_copy_seed_user` imports `master_copy.MasterCopyService`, a module that exists nowhere in this repository, so the op always fails with `ImportError` (500). Nothing in the backend, coach or Rust code calls it. Go answers 501 `not_served`.
- `settings_create` is unreachable through the pipeline: `authorize` rejects `discord_id` (and the other identity selectors) for `ownership: person` operations, and `settings_create` requires `discord_id`. Its identity lookup is `scan(Limit=1, FilterExpression=...)`, which filters after limiting, so it inspects one row. Go keeps the operation with a full filtered scan; `identity_resolve` is the live path.
- `settings_update_*` resolve the row with `_sanitize_username(args.username)` instead of the person key. A person key with uppercase, fewer than 2 or more than 32 characters is looked up as a different key (or `user_<timestamp>`). Go reads by the authenticated person key (identical for every normal `person_<hex>` key).
- `settings_update_avatar` deletes the previous S3 object named by the path of any `http(s)` avatar URL (a Discord CDN URL becomes the key `avatars/<id>/<hash>.png` in the videos bucket). Go only deletes keys under `profiles/`.
- `handler_context` takes `phase` from the unfiltered program sessions and returns it with `program:read` even without `sessions:read`. Go keeps it for parity.
- Python `ProgramStore._load_program_sync` writes a recreated `program#current` pointer when it is missing, so `handler_context` can write from a read path. Go reads the newest published `program#v*` and never writes.
- Several Python profile reads use eventually consistent `get_item`/`query` (settings updates, `grant_check`, `grant_list`, favorites, notifications). Go uses consistent reads for the item reads that feed a following write and plain queries where Python paginated.
- `grant_list` by grantee only does a full-table `scan()` of `if-powerlifting-requests` (no GSI). Go keeps it; add a grantee index before this grows.
