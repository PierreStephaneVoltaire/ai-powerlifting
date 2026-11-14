# Bugs noticed (not chased)

## competition (Go rewrite, found while capturing Python goldens)

- `calculate_attempts` (Python): `ProgramStore.get_program()` returns raw DynamoDB `Decimal` values. `attempt_1 + j1` becomes a `Decimal`, then `/ 2.5` (float) raises `TypeError`; `current_max * 0.7` fails the same way. The op only works when `operator_prefs.attempt_jumps` and `current_maxes` are absent or the program came from a fake store. The Go version treats stored numbers as plain numbers.
- `calculate_attempts` (Python): a missing program surfaces as an unhandled `ProgramNotFoundError` (HTTP 500). Go returns 404 `not_found`.
- Python `record_write` only bumps `pl:analysis-version:<athlete>` for the operation names `health_update_user_competition` / `health_complete_user_competition`. The same mutation sent through `health_list_competitions` with `op: update|complete` never invalidates the analysis version, so cached analysis can stay stale. Go keeps that behaviour for parity; widen `analysisInputWrites` in `competition-go/internal/service/service.go` if it should bump.
- Python `ProgramStore._load_program_sync` writes a recreated `program#current` pointer when it is missing. The Go reader does not write (read-only service); it only falls back to the newest published `program#v*` item.
- Rust `meet_projection` projects bench from exercises keyed exactly `bench` (normalised name), so sessions logged as "Bench Press" contribute no bench progression slope (bench slope is always 0 for them). Go replicates it for parity with the live Rust service.
