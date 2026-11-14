# Prompt cache in Go

## Why

Domain AI calls must not reprompt when an earlier answer still holds. The cache
was meant to check exact match first, then a semantic match that a small model
judges against input, output and context. The semantic layer was removed from
operation AI calls in `f11cbee6`, and the Go rewrite (`acad1a5d`) only has an
exact Valkey key. Today every non-identical prompt reprompts.

## Design

One Go service owns the prompt cache. Every domain AI call (Python runtime and
Go analytics-ai) asks it before inference and tells it after inference.

    lookup(athlete, operation, request, context) -> hit {response, layer} | miss
    store(athlete, operation, request, response, context)

`context` is what can make the same ask need a different answer:
- `date`: today's date (ISO).
- `analysis_version`: `pl:analysis-version:{athlete}` from Valkey.

Lookup order:

1. Exact. Valkey key `pl:ai-cache:exact:{athlete}:{operation}:{analysis_version}:{request_hash}`.
   A hit returns the stored response. Layer `exact`.
2. Semantic candidates. Search the Qdrant collection for this athlete and
   operation (one collection per athlete and operation, as today) through
   `pl-prompt-cache-mcp` (`qdrant-find`, embeddings stay inside
   mcp-server-qdrant). Take the top 3 candidates. Each candidate's Qdrant
   metadata holds its entry id; the entry (request, response, context) lives in
   Valkey at `pl:ai-cache:entry:{entry_id}`.
3. Decision. One call to the OpenAI Decisions API (`POST DECISIONS_URL`,
   default `https://api.openai.com/v1/decisions`, `Authorization: Bearer
   OPENAI_API_KEY`, API key only, model `DECISION_MODEL` default `gpt-6-luna`).
   Request:

       {"model": "gpt-6-luna",
        "input": [{"role": "user", "content": [{"type": "input_json", "json":
          {"new": {"request": <request>, "context": {date, analysis_version}},
           "candidates": [{"entry_id", "request", "response", "context"}, ...]}}]}],
        "questions": [one "choice" question per candidate, name
          "candidate_<entry_id>", instructions "Can the stored response be reused
          unchanged for the new request? same = answers it as is; contextual =
          the ask or its data differs so the answer would change; temporal = the
          answer depends on the date and the date moved; none = unrelated.",
          choices same / contextual / temporal / none, each with a short description],
        "prompt_cache_key": "<athlete>:<operation>"}

   Response: `answers[]` of `{type: "choice", name, choice, probabilities, confidence}`
   or `{type: "refusal"}`.
   - `same`: the candidate answers the new ask as is.
   - `contextual`: the ask or its data differs in a way that changes the answer.
   - `temporal`: the answer depends on the date (days to a competition, current
     week, recency) and the date moved.
   - `none`: no candidate fits.
   Hit rule: the first candidate in search order whose answer is `same` with
   `confidence >= DECISION_MIN_CONFIDENCE` (default 0.8). Layer `semantic`.
   Otherwise a miss; the first `contextual` or `temporal` answer is reported as
   the reason in the lookup result and the log line. A refusal, HTTP error,
   timeout (`DECISION_TIMEOUT_MS`, default 3000) or a missing key is a miss.
   The decision sits behind a `Decider` interface; without `OPENAI_API_KEY` the
   service wires a decider that always misses.
4. Miss. The caller runs inference, then calls `store`.

Store writes the exact key, the entry, and `qdrant-store` with the searchable
text of the request and metadata `{entry_id, date, analysis_version}`.

Read-only callers (visitors) may look up but never start inference; that rule
stays in the callers.

## Service

- Code: `src/services/prompt-cache/` (Go module, same layout and idioms as
  `src/services/analytics-ai`: `internal/...`, `main.go`/cmd as that module does,
  slog, go-redis). No language suffix in names.
- HTTP API (JSON):
  - `POST /lookup` `{athlete, operation, request, context}` -> `{hit: bool, layer?, response?, entry_id?, decision?}`
  - `POST /store` `{athlete, operation, request, response, context}` -> `{entry_id}`
  - `GET /health`
- Config env: `VALKEY_URL`, `PROMPT_CACHE_MCP_URL`, `OPENAI_API_KEY` (optional),
  `DECISIONS_URL`, `DECISION_MODEL` (default `gpt-6-luna`), `DECISION_TIMEOUT_MS`
  (default 3000), `DECISION_MIN_CONFIDENCE` (default 0.8), `ENTRY_TTL_SECONDS`
  (default 30 days, same as today).
- `request` is `{messages, tools, response_format}` (what `cache_request`
  builds today). Searchable text = the user/system message text, as the old
  `searchable_text` did in `669f8774:src/services/lib/prompt_cache.py`.
- Log one structured line per lookup: athlete, operation, layer, decision
  reason, latency. No prompt bodies in logs.

## Callers

- Python `src/services/runtime/prompt_cache.py`: replace the Valkey logic with
  an HTTP client for `/lookup` and `/store` (`PROMPT_CACHE_URL`, default
  `http://pl-prompt-cache-api.powerlifting.svc.cluster.local:8000`). Keep
  `cache_request` and `request_hash`. `runtime/ai.py` `completion` passes
  context (today, `analysis_version.current(athlete)`) and logs `cache_layer`
  from the result (`exact`, `semantic`, or `none`). A cache service error is a
  miss, never a failed operation.
- Go `src/services/analytics-ai/internal/cache`: `Prompts.Exact`/`Remember`
  become a client of the same API with the same context. Keep
  `AnalysisVersion`.
- `src/services/coach/chat_cache.py` (chat replies) is out of scope.

## Deploy

- Kubernetes Deployment and Service `pl-prompt-cache-api` in a new
  `terraform/k8s/app/prompt_cache_api.tf` (do not stuff it into
  `prompt_cache.tf`). Match `analytics_ai.tf` for image, probes, resources,
  mesh labels and service account pattern. `OPENAI_API_KEY` comes from SSM
  `/powerlifting/litellm/provider_keys/openai` (the existing provider key path
  read in `litellm.tf`), mounted from a `pl-prompt-cache-api` secret; an absent
  parameter gives an empty key and the service starts with an always-miss decider.
- Add `PROMPT_CACHE_URL` to the services that run domain AI (the shared config
  map used by pl-* services and analytics-ai).
- CI: add the image to the build matrix in `.github/workflows/build-images.yml`
  and `pl-prompt-cache-api` to the rollout list there.
- Pipeline deploys it. No manual apply.

## Tests

No new test suites. Run existing tests that cover changed files:
`src/services/analytics-ai` `go test ./internal/cache/...`, and the Python
test files that import `prompt_cache` or `runtime.ai`. The new module needs
`go build ./...` and `go vet ./...` to pass.

## Later phases (separate plans)

2. Reports: after the calculations, save AI reports to S3 with a Valkey
   pointer; remove the DynamoDB generation store (`analytics-ai/internal/generation/dynamo.go`,
   `if-powerlifting-analysis-cache`).
3. Invalidation: remove hardcoded cache version constants from keys; analytics
   deletes its own outdated keys on build change; `record_write` resolves
   `mapped_pk` before bumping the athlete version.
