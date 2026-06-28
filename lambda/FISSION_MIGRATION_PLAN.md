# Fission Migration Plan — Replace AWS Lambda + API Gateway

Status: DRAFT — planned, not yet implemented. Lives next to `HEALTH_LAMBDA_MIGRATION_PLAN.md`.

## Goal

Replace the deployed AWS Lambda + HTTP API Gateway + authorizer stack for the
powerlifting health tool surfaces with **Fission** running inside the existing
k3s cluster. Keep the per-folder `resources.yaml` data model, the OpenAPI
registry, the agent `health_lambda` MCP server, the backend `invokeLambda` + LRU
cache, and the agent-side OpenAPI-discovery pattern. Net change is the **backend
runtime substrate** only.

Motivation: avoid variable AWS billing per-request, avoid duplicated RAM of
fat images on a single-node cluster, reclaim resources faster than Lambda's
5-15 min keep-warm. Cluster-side substrate is already paid for 24/7.

## Constraints (from operator discussion)

- Single k3s node — no horizontal scale-out.
- **Avoid a 3GB env image.** Multiple concurrent functions must fit memory.
- Slim shared base: `python:3.12-slim` env + read-only layer mounts.
- **Fission router stays in-cluster only** — no Cloudflare exposure required
  for Fission itself. All callers (portal backend, IF agent API pod, agent MCP
  pod) already live in the same cluster and can hit `router.fission:80` (the
  `ClusterIP` service already declared in `terraform/k8s-fission.tf`) directly.
  Only `cloudflared`-exposed portals (frontend UIs in `if-portals`) require
  any external traffic.
- Backend, IF agent API, and the new `health_lambda` MCP pod are the only
  callers allowed to reach the router (token-gated).
- Scale-to-zero for low-traffic / AI tools; small warm pool for the 8-10
  high-traffic deterministic read tools (portal UI responsiveness).
- The 19 AI tools continue to call OpenRouter themselves; the layer that
  bundles `httpx` + `jinja2` + `prompts/loader.py` + 24 `.j2` files stays.
- `health_rag_search` keeps running in-process on the agent pod (ChromaDB).

## What stays unchanged from the Lambda migration

- Every `lambda/<tool>/` folder + `handler.py` + `resources.yaml` — same
  per-folder data model. The `layers:` field in `resources.yaml` becomes the
  per-function `PYTHONPATH` synthesis source.
- `lambda/tool_registry/` + its `resources.json` (89... 94 entries) and the
  generated OpenAPI doc semantics — Fission function reads the bundled
  `resources.json` and returns OpenAPI from `GET /openapi.json`.
- `tools/health_lambda_mcp/server.py` — the agent's HTTP-discovering MCP
  server. Only the `POWERLIFTING_LAMBDA_BASE_URL` env points at the in-cluster
  Fission router DNS instead of `execute-api.ca-central-1.amazonaws.com`.
  Discovery code, header injection, response parsing — unchanged.
- `app/src/mcp_runtime/manager.py` category wiring + `app/src/config.py`
  `MCP_SERVER_CATEGORIES` / `POWERLIFTING_LAMBDA_BASE_URL` — unchanged.
- `utils/powerlifting-app/backend/src/utils/lambda.ts` `invokeLambda` —
  unchanged signature and body. Only the env value flips.
- `lambdaCache.ts` (LRU + write invalidation) — unchanged.
- 19 AI lambda folders, `pl_authorizer` folder (becomes a tiny Fission
  pre-function auth or tinyauth middleware — see Phase 3).

## Design — slim env + shared read-only layer mount

### Three concerns, deliberately separate

1. **Env image (warm pool base, ONE image pulled)** — `python:3.12-slim`
   (~80-120 MB on disk). Contains only: python runtime, pip, Fission's
   `python-env` stub. No app code, no app deps. This is the only image a
   function pod cold-starts.

2. **Per-function deploy_archive (kilobytes)** — built per existing folder:
   `handler.py` + (AI tools only) the copied `_ai.py`. No deps in the zip.
   Mounted/injected by Fission onto a warm env pod.

3. **Shared layer mounts (single on-disk copy, page-cached)** — the existing
   10 LayerVersion-equivalent concerns collapse to 3-4 thin read-only dirs
   bind-mounted into every function pod:
   - `pl_base`     = httpx + jinja2 + boto3 (+ core libs every tool needs)
   - `pl_health_data` = program_store/session_store/glossary_store/template_store/
                     import_store/federation_store/analysis_cache/comparison/
                     powerlifting_stats + health_types + core
   - `pl_prompts`  = prompts/loader.py + the 24 `.j2` files (read-only, tiny)
   - `pl_stats`   = pandas + numpy + scipy (mounted only when `resources.yaml`
                    `layers:` lists `pl_pandas`)

   Each function pod gets `PYTHONPATH=/opt/layers/<subset>` derived from its
   `resources.yaml` `layers:` list atHTTP trigger evaluation time. The same
   pages live on disk once; Linux page cache means concurrent pods share RAM
   pages for the read-only layers — no duplication.

### Layer mount mechanism

Two options, Fission env spec supports both via pod patch / volume mounts:

- **(A) HostPath / preferred for single-node k3s** — populate
  `/opt/pl-layers/{pl_base,pl_health_data,pl_prompts,pl_stats}` once on the
  node (from a one-shot `kubectl apply` of an init DaemonSet or via the
  existing Packer AMI build). Mount that host path `readOnly: true` into every
  function pod at `/opt/layers`. Zero duplication. Disk cost: 200-300 MB total
  on the node. Page cache = shared across pods.

- **(B) Composite Docker image for layers** — pull a `pl-layers:vN` image
  (~300-400 MB on disk, ~80-150 MB resident in page cache), run a 1-second
  initContainer that rsyncs it onto an `emptyDir` shared with main. Avoids
  HostPath but duplicates per-pod emptyDir RAM; only choose if HostPath is
  disallowed.

Default: (A) — HostPath is fine on a single self-managed k3s node and gives
the smallest resident footprint. The Cordon-Node + Replicated-PV pattern
isn't needed because the cluster is single-node.

### Routing — all in-cluster

- Fission router ships as `ClusterIP` per existing `terraform/k8s-fission.tf`
  (`serviceType=ClusterIP`, `routerServiceType=ClusterIP`). No public Service,
  no Ingress, no HTTPRoute, no Cloudflare record for the router.
- Every function gets a Fission HTTP trigger at `POST /<tool>` — same path as
  today. The trigger is the API gateway; Fission IS the API gateway here.
- Callers reach it via in-cluster DNS:
  - If backend / agent / MCP pods are in `if-portals`: the FQDN is
    `router.fission.svc.cluster.local` (or the helm-installed router DNS).
  - If in another namespace but same cluster: same DNS resolves.
- `cloudflared` continues to expose ONLY the existing public UIs in
  `if-portals` — portals that talk to the backend over the existing tunnel.
  Fission itself never appears on any public URL.

### Authz — token gate stays, dropped from the public-ingress path

The Fission router is `ClusterIP`-only, never exposed via Cloudflare. The
only callers are *already inside the same cluster* (backend pod, IF agent API
pod, agent MCP pod). Tinyauth exists to gate **public ingress** behind OAuth —
putting it in front of a private in-cluster Service is overkill.

Mechanism: **Fission pre-function auth** — reuse the existing
`lambda/pl_authorizer/handler.py` (constant-time `X-Internal-Token` check)
attached as a Fission `pre-hook` so every function invocation is gated once,
centrally, before the main function runs. Zero middleware sidecar wiring,
no new Service, no new Ingress.

Why the static token is still worth keeping on a private cluster:
- Stops a misconfigured pod in another namespace from accidentally hitting
  tool endpoints.
- Stops a debug container left lying around from spamming the AI lambdas
  (the original cost concern).
- Lets you rotate access if a pod's env leaks.

Discarded option: tinyauth middleware on the Fission router path — valid but
adds an unnecessary sidecar for a path that has no public exposure. Tinyauth
stays in the cluster for what it is actually for: the public Cloudflare-exposed
portal UIs in `if-portals`.

`GET /openapi.json` stays unauthed (public schema doc, no user data), same
as the Lambda version.

### Scale-to-zero + HPA

- 19 AI tools → `newdeploy`, `minReplicas=0`, `maxReplicas=1` (or 2 if node RAM
  permits) — they cost 512MB-1GB resident; OpenRouter calls last 30-60s.
  Termination grace bumped to 120s so OpenRouter streams don't get SIGTERM'd
  mid-call (kills OpenRouter TCP connections → partial responses).
- OpenPowerlifting stats tools (3) → `newdeploy`, `minReplicas=0` — heavy
  pandas/scipy cold start; warm only when needed.
- 8-10 high-traffic deterministic reads (health_get_program,
  health_get_session, health_get_sessions_range, template_list, get_*_markdown,
  weekly_analysis, analysis_section) → `newdeploy`, `minReplicas=1` so portal
  UI从不 takes a cold start on first hit after node idle.
- Remaining ~60 deterministic tools → `newdeploy`, `minReplicas=0`. Whoever
  hits them pays a ~1-3s cold start; acceptable for low-traffic admin paths.
- HPA target: CPU + concurrency, with `--horizontal-pod-autoscaler-
  downscale-stabilization=120s` so pods aren't yanked mid-stream. Resource
  reclamation: 30s-2 min after last request — faster than Lambda's 5-15 min.

### Resource budget (single-node)

Resident RAM ceiling for the tool surface at steady-state with the warm pool:
- 1 warm poolmgr container (~80MB, shared) + ~10 read-tool pods (~50-80MB
  each) = ~600-900MB total warm.
- Cold AI invocations add 1 × ~500-1000MB transient until completion, then
  released. Max 1-2 concurrent AI calls fit a 2-3 GB node-side budget for the
  tool surface, with headroom for the rest of the cluster (bot API, portals,
  Loki/Prometheus/Grafana).

Disk: env image pulled once (~120MB on disk) + read-only layer dir
(~300MB on disk, page-cached) + Fission router + controller (~200MB). Total
~600MB disk for the substrate, shared.

## Phases

### Phase 0 — Audit current state [not started]
- [ ] Confirm Fission CRDs installed in cluster (`kubectl get crds | grep fission`).
- [ ] Confirm router Service is `ClusterIP` and resolvable from `if-portals`.
- [ ] Confirm `var.fission_enabled` is on and router is reachable in-cluster.
- [ ] Inventory current `lambda/*/resources.yaml` `layers:` fields: produce the
      3-4 thin layer buckets (pl_base, pl_health_data, pl_prompts, pl_stats).
- [ ] Disk + RAM headroom audit on the k3s node (free -h, df -h).

### Phase 1 — Build the slim env + layer mounts [not started]
- [ ] Build `pl-layers-base` package/archive (httpx, jinja2, boto3) — from
      existing `lambda/layers/pl-ai` build with the AI bits split out.
- [ ] Build `pl-layers-health-data` — scraped from current `pl_program`,
      `pl_sessions`, `pl_glossary`, `pl_templates`, `pl_imports`,
      `pl_federation`, `pl_analysis_cache` contents.
- [ ] Build `pl-layers-prompts` — `prompts/loader.py` + 24 `.j2`.
- [ ] Build `pl-layers-stats` — pandas/numpy/scipy (carried over from
      `pl-pandas`).
- [ ] Publish to cluster node under `/opt/pl-layers/` via:
      - (A) One-shot DaemonSet init cp tarball from a `kubectl cp`, or
      - (B) Packer AMI bake step adds `/opt/pl-layers/` to the node image.
- [ ] Build `pl-fission-env` Docker image — `python:3.12-slim` base, Fission
      env stub, ENV `PYTHONPATH=/opt/layers/pl_base:/opt/layers/pl_prompts`
      as the default. Push to ECR.
- [ ] Define Fission `Environment` CR with the slim env image + a pod spec
      patch declaring the HostPath `/opt/pl-layers` readOnly mount so every
      function pod gets the layers without per-function wiring.
- [ ] Validate: pod from this env can `import httpx`, `import jinja2`,
      `from prompts.loader import load_system_prompt` — without the host path
      mount not present (to prove nothing is baked into the env image).

### Phase 2 — Convert per-folder handlers to Fission functions [not started]
- [ ] Script: `tools/fission-deploy.py` — walks `lambda/<tool>/` folders (skipping
      `layers/`, `master-sync/`, `video-thumbnail/`, `tool_registry/`,
      `pl_authorizer/`). For each folder:
      - Reads `resources.yaml` → derives `PYTHONPATH` from `layers:` list
      - Builds a `deploy_archive.zip` of just the folder's .py files
      - Emits a Terraform fragment declaring `fission_package` +
        `fission_function` + `fission_http_trigger` for that tool
- [ ] Terraform file `fission-functions.tf` `for_each` over the 94 (current
      deterministic fingerprint minus `health_rag_search` / `pl_authorizer`)
      folders' `resources.yaml`, declaring the package + function + trigger.
- [ ] `tool_registry` function — same handler.py (it serves `resources.json`
      as OpenAPI); gets a Fission HTTP trigger at `GET /openapi.json`.
- [ ] Resolve `health_rag_search` — NOT migrated, stays in-process on agent pod.
- [ ] Smoke-test one deterministic read (e.g. `health_get_program`), one
      deterministic write (e.g. `health_update_session`), one AI tool
      (e.g. `fatigue_profile_estimate`) end-to-end against the Fission router
      via the backend's `invokeLambda` with `POWERLIFTING_LAMBDA_BASE_URL`
      swapped to `http://router.fission.svc.cluster.local`.

### Phase 3 — Auth + routing swap (no Cloudflare changes) [not started]
- [ ] Register `pl_authorizer/handler.py` as a Fission pre-function attached to
      every function trigger (constant-time check against `INTERNAL_API_TOKEN`
      from the k8s Secret). Keep `GET /openapi.json` unauthed.
- [ ] Do NOT add tinyauth middleware to the Fission router path — it is
      ClusterIP-only and has no public exposure. Tinyauth stays scoped to the
      existing `cloudflared`-exposed portal UIs in `if-portals`.
- [ ] Update backend env: `POWERLIFTING_LAMBDA_BASE_URL`
      `= http://router.fission.svc.cluster.local` (no more execute-api URL).
- [ ] Update agent API + agent MCP pod envs the same.
- [ ] Update `app/src/config.py` default for `POWERLIFTING_LAMBDA_BASE_URL`
      if desired (or leave blank — same as today).
- [ ] Confirm NO new Cloudflare tunnel / HTTPRoute / public Service exists
      for Fission.

### Phase 4 — Scale-to-zero tuning + HPA [not started]
- [ ] Per-function `newdeploy` executor spec per tool class:
      - AI tools (19): `minReplicas=0`, `maxReplicas=1-2`, `targetCPU=70`,
        `terminationGracePeriodSeconds=120`, timeout 900s.
      - Stats tools (3): `minReplicas=0`, `maxReplicas=1`, timeout 600s.
      - High-traffic deterministic reads (8-10): `minReplicas=1`,
        `maxReplicas=2`, `targetCPU=70`.
      - Remaining deterministic (~60): `minReplicas=0`, `maxReplicas=2`,
        `targetCPU=70`, timeout 60s.
- [ ] HPA `--horizontal-pod-autoscaler-downscale-stabilization=120s` on the
      controller-manager config to bound churn.
- [ ] Soak test: invoke 3 tool types, idle 5 min, confirm pods scale to 0
      within 2 min and cold starts rehydrate in < 5s for deterministic / < 10s
      for AI (OpenRouter stream latency dominates the latter).
- [ ] Document concurrent-AI-call cap (estimate 2 concurrent on node budget).

### Phase 5 — Cluster replacement of AWS sources [not started]
- [ ] Move `OPENROUTER_API_KEY` + `INTERNAL_API_TOKEN` sources from
      `aws_ssm_parameter` (plain String, no KMS) to a k8s `Secret` in
      `if-portals` namespace (or keep SSM as source-of-truth and k8s Secret
      as a mirror pulled by an External Secrets Operator — pick later).
- [ ] Tear down (with explicit approval per the no-mutating rule):
      - `terraform destroy -target=aws_lambda_function.health_tool` (all 94)
      - `terraform destroy -target=aws_lambda_layer_version.*` (the 10 layer
        versions)
      - `terraform destroy -target=aws_apigatewayv2_api.health_api` +
        integration/route/permission/authorizer resources
      - `terraform destroy -target=aws_ssm_parameter.pl_openrouter_key` and
        `pl_internal_token` IF moving them fully to k8s Secrets
- [ ] Remove Lambda/API Gateway TF files: `lambda.tf`, `layers.tf`,
      `apigateway.tf`, `authorizer.tf`, `ssm.tf`, `iam.tf` lambda exec role (if
      nothing else uses it).
- [ ] Keep `tools/health_lambda_mcp/`, the per-folder `resources.yaml`, the
      `tool_registry` folder + `resources.json`, the agent MCP `health_lambda`
      category wiring — all stay.

### Phase 6 — Observability (free: already wired) [not started]
- [ ] Fission pods emit stdout JSON; existing `promtail` DaemonSet (in
      `monitoring` namespace per `terraform/k8s-observability.tf`) already
      ships pod logs to existing Loki. Zero new plumbing for logs.
- [ ] Lambda-style CloudWatch → Vector/Loki path from the deferred Lambda
      migration Phase 4 is NO LONGER NEEDED — no CloudWatch tail to maintain.
- [ ] Add Grafana dashboard panel for `fission_function_invocations_total`,
      `fission_function_errors_total`, `fission_function_cold_starts_total` —
      exposed via Fission's built-in metrics endpoint; scrape the existing
      Prometheus config map (`grafana_dashboards` ConfigMap).
- [ ] Add a dashboard for per-tool pod count + 'scale-to-zero' events.

### Phase 7 — Docs + cutover [not started]
- [ ] Update `AGENTS.md` — add "Powerlifting tools runtime substrate" note:
      Lambda+API Gateway replaced by Fission in-cluster `router.fission`
      ClusterIP; agent MCP discovery path unchanged; `tools/health]))
- [ ] Update `HEALTH_LAMBDA_MIGRATION_PLAN.md` — mark its Phase 1-3 DONE,
      add redirect note pointing here for the Fission follow-on.
- [ ] Update `tools/health_lambda_mcp/README.md` — `POWERLIFTING_LAMBDA_BASE_URL`
      now resolves to the in-cluster Fission router; no Cloudflare route.
- [ ] Deploy via `scripts/build-test-images.sh` to `if-portals-test` + a
      Fission-enabled test namespace; smoke test the portal flow end-to-end.
- [ ] Final cutover: replace env values live, run drain, monitor dashboard.

## Open decisions to confirm before Phase 1 starts

- [ ] (A) HostPath layer mount vs (B) composite image emptyDir mount — HostPath
      preferred unless node-image constraints forbid.
- [ ] ~~tinyauth middleware on Fission router vs Fission `pl_authorizer` pre-function
      hook~~ — DECIDED: Fission pre-function. Tinyauth stays scoped to public
      Cloudflare-exposed portals only.
- [ ] `OPENROUTER_API_KEY` + `INTERNAL_API_TOKEN` source: keep SSM-String +
      mirror to k8s Secret via External Secrets Operator, or move exclusively
      to k8s Secret? (Either works; SSM keeps single source-of-truth if
      other AWS services still use it.)
- [ ] `minReplicas` for the warm pool on high-traffic deterministic reads — 1
      or 0? 1 = snappy UI but always-on ~80MB resident pod. Default: 1 for the
      ~10 highest-traffic reads.
- [ ] Max concurrent AI calls budget on node — 1, 2, or 3? Affects
      `maxReplicas` and HPA target for the 19 AI tools.

## What is explicitly NOT in scope

- Re-implementing any of the AI tool logic, OpenRouter call code, prompt
  templates, store modules, schemas, OpenAPI registry, agent MCP server, or
  backend LRU cache. Those survive the substrate swap unchanged.
- Changing the `health_rag_search` in-process path on the agent.
- Any public Cloudflare route for Fission itself. Only existing
  `cloudflared`-exposed portal UIs in `if-portals` keep external traffic.
- Multi-node elastic scale-out (cluster stays single-node).

## What this plan does NOT back out

- The original Lambda migration is live and untouched. This plan is a
  follow-on; switching to Fission is opt-in by replacing
  `POWERLIFTING_LAMBDA_BASE_URL` and executing Phase 5's teardown.
