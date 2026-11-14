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
