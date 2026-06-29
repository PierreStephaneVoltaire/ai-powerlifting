# Fission Migration Plan — Replace AWS Lambda + API Gateway

Status: Phases 0-2 implemented (terraform fmt/validate green, per-tool deploy
archives built). Phases 3-7 forward work. Lives next to
`HEALTH_LAMBDA_MIGRATION_PLAN.md`. See `FISSION_DEPLOY.md` for the implemented
record and `FISSION_PHASE0_AUDIT.md` for the live-cluster audit.

> Architecture revision (operator-directed, 2026-06-28): the original
> "slim env + shared read-only HostPath layer mount" design was dropped. It
> forced a fat composite env image (pandas+numpy+scipy+all store modules+all
> prompts baked into ONE image every pod cold-starts) and a redundant per-tool
> zip script. The implemented design is the **Fission-native** path: the stock
> `ghcr.io/fission/python-env` runtime (shared, pulled once) + the stock
> `ghcr.io/fission/python-builder` that runs `pip install -r requirements.txt`
> at build time. Each tool's deploy archive carries ONLY the `.py` files it
> needs + a `requirements.txt` listing ONLY the pip deps that tool uses
> (boto3 for basic tools; +pandas/numpy for stats; +httpx/jinja2 for AI;
> +scipy for the 2 tools that need it). No tool drags deps it doesn't use.
> No custom Packer image. No HostPath layers. No per-pod bloat. Basic-math
> tool archives are ~12 KB; biggest archive is 88 KB; total 96 archives = 2 MB.
>
> Terraform topology (operator-directed, 2026-06-28): the generated Fission
> CRDs (`fission-functions.tf`) + per-tool deploy archives (`fission-build/`)
> live in the **root `terraform/`** (repo root), NOT in
> `utils/powerlifting-app/terraform/`. Per the multi-repo `.meta` config + the
> powerlifting `AGENTS.md`, the root stack is applied **locally** against the
> private k3s kubeconfig (GitHub Actions can't reach the private cluster);
> `powerlifting-app/terraform/` is AWS-only (ECR/S3/Lambda/SSM/DynamoDB) and
> owns NO k8s resources. The generator `lambda/fission-deploy.py` reads source
> from `utils/powerlifting-app/lambda/` (the powerlifting repo, source of truth)
> and writes its terraform output to the repo-root `terraform/`. Root vars
> `powerlifting_s3_bucket`, `pl_internal_token`, `fission_function_namespace`
> + the root `kubernetes_secret.pl_fission_secrets` + `INTERNAL_API_TOKEN` in
> `if_agent_api_secrets` are in the root stack.
>
> MCP exposure (operator-directed, 2026-06-28): each Function carries
> `spec.tool` (Fission's `ToolConfig` — `--expose-as-mcp`) with `name`,
> `description`, and `inputSchema` sourced from the tool's `resources.yaml`.
> Fission's router exposes an MCP server endpoint, so the IF agent consumes
> the tools directly via MCP — the `tools/health_lambda_mcp/` HTTP-discovery
> intermediary is no longer needed for the agent path. The portal backend
> still hits the Fission router HTTP (`POST /<tool>`) for UI calls via
> `invokeLambda` (unchanged code, just the env URL flips in Phase 3).

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
- **Avoid a fat env image.** Multiple concurrent functions must fit memory.
  Implemented via the Fission-native path: the stock `ghcr.io/fission/python-env`
  shared runtime (pulled once) + the Fission builder that pip-installs a
  per-tool `requirements.txt` at build time. No deps baked into any image;
  no tool carries deps it doesn't use.
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
  per-tool `requirements.txt` + vendored-store-module source (synthesized by
  `fission-deploy.py` from the layer→(modules, pip-requirements) map in
  `fission_layers.py`).
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

## Design — Fission-native (implemented)

### Three concerns, deliberately separate

1. **Env image (shared runtime, pulled once)** — the stock
   `ghcr.io/fission/python-env` image (Alpine + python + the Fission
   `server.py` dynamic loader). No app code, no app deps baked in. Every
   function pod cold-starts from this one shared image. Paired with
   `ghcr.io/fission/python-builder`, which runs the build phase.

2. **Per-tool deploy_archive (kilobytes)** — built per existing folder: the
   tool's own `.py` files (`handler.py`, `core.py`, `config.py`,
   `__init__.py`, and AI tools' `<name>_ai.py`) + the store modules its
   `resources.yaml layers:` list references, vendored at the archive root
   (so `from program_store import ...` resolves) + a `requirements.txt`
   listing ONLY the pip deps those layers bring + `fission_entry.py`
   (the shared Fission→Lambda adapter). The Fission builder runs
   `pip install -r requirements.txt -t <archive>` at build time, then
   copies the result as the deploy archive. **No deps baked into any
   image; no tool carries deps it doesn't use.**

3. **Per-tool `requirements.txt` (the dep carrier)** — derived from the
   tool's `resources.yaml layers:` list against the layer→pip-deps map in
   `fission_layers.py`:
   - `pl_boto3` → `boto3==1.42.83 botocore==1.42.83 s3transfer==0.16.0`
   - `pl_pandas` → `pandas==2.2.3 numpy==2.1.3`
   - `pl_ai` → `httpx jinja2`
   - `pl_program`/`pl_sessions`/`pl_glossary`/`pl_templates`/`pl_imports`/
     `pl_federation`/`pl_analysis_cache` → pure-python store modules,
     vendored into the archive (no pip dep)
   - `analyze_progression` and `analyze_rpe_drift` additionally pull
     `scipy` (explicit extra, not in any layer).

   Result: basic-math tools (calculate_attempts, days_until, estimate_1rm)
   ship a ~12 KB archive with a boto3-only requirements.txt. Stats tools
   add pandas/numpy. AI tools add httpx/jinja2 + vendored ai_config.py +
   prompts/loader.py + 22 `.j2` files. No per-pod bloat.

### The Fission entrypoint adapter

Fission's `server.py` loads the deploy archive at `/userfunc`, appends it
to `sys.path`, and routes HTTP requests to the module's `main` function
with the Flask request as the argument. The Lambda handlers expect
`(event, context)` where `event = {args: <body>, headers: {...}}` and
return `{statusCode: 200, body: "<json>"}` — the exact envelope the backend
`invokeLambda` consumes. `fission_entry.py` (~25 lines, vendored into every
archive) bridges the two: it imports the tool's `handler`, builds the
Lambda-style event from the Flask request, calls `handler(event, None)`,
and returns the Lambda envelope. Set as each Function's `functionName` via
the `IF_TOOL_NAME` env var.

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

### Phase 0 — Audit current state [COMPLETE]
- [x] Confirm Fission CRDs installed in cluster (`kubectl get crds | grep fission`) — done, see `FISSION_PHASE0_AUDIT.md`.
- [x] Confirm router Service is `ClusterIP` and resolvable from `if-portals` — `router.fission.svc.cluster.local`.
- [x] Confirm `var.fission_enabled` is on and router is reachable in-cluster.
- [x] Inventory current `lambda/*/resources.yaml` `layers:` fields — 10 layer keys
      (`pl_boto3 pl_pandas pl_program pl_sessions pl_glossary pl_templates
      pl_imports pl_federation pl_analysis_cache pl_ai`) mapped to their
      vendored python modules + pip requirements in `fission_layers.py`.
      Tool classes: 15 AI, 4 warm reads, 5 stats, 71 deterministic = 95
      deployable tools.
- [x] Disk + RAM headroom audit on the k3s node — confirmed ~14 GB headroom.

### Phase 1 — Fission env + layer contract [COMPLETE]
- [x] Layer→(python modules, pip requirements) contract in `fission_layers.py`
      (the single source of truth the generator reads). No HostPath layers,
      no composite image — the dropped design.
- [x] Fission `Environment` CR `pl-fission-tools` declared in
      `terraform/fission-functions.tf` using stock `ghcr.io/fission/python-env`
      runtime + `ghcr.io/fission/python-builder` builder, version 3,
      keeparchive false. No custom Packer image.
- [x] Providers (`versions.tf`, `providers.tf`): aws + kubernetes + kubectl
      (gavinbunney) + helm, gated by `var.fission_powerlifting_env_enabled`.
- [x] Variables (`variables.tf`): kubeconfig path/context, fission env name,
      router DNS, function namespace, `pl_internal_token`, `openrouter_api_key`.
- [x] `terraform fmt -check -recursive` + `terraform validate` → Success.

### Phase 2 — Convert per-folder handlers to Fission functions [COMPLETE]
- [x] `lambda/fission_entry.py` — shared Fission→Lambda adapter (~25 lines,
      vendored into every archive). Builds the Lambda event from the Flask
      request, imports the tool `handler`, calls `handler(event, None)`,
      returns the `{statusCode, body}` envelope the backend consumes.
- [x] `lambda/fission_layers.py` — layer→(modules, pip-requirements) contract
      + tool classification (ai/warm/stats/det) + `SCALE_PROFILE` per class.
- [x] `lambda/fission-deploy.py` — generator. `--dry-run` prints counts;
      default builds the 96 per-tool deploy archives under
      `terraform/fission-build/` + the pl_authorizer archive, then emits
      `terraform/fission-functions.tf` (HCL) declaring the Environment CR +
      96 Package + 96 Function + 95 HTTPTrigger `kubectl_manifest` blocks.
      Re-run after any handler or layer change to regenerate.
- [x] `terraform/fission-functions.tf` — generated. Environment +
      per-tool Package (literal source = the per-tool zip name, buildcmd
      `/usr/local/bin/build` so the Fission builder runs
      `pip install -r requirements.txt`) + Function (`newdeploy` executor,
      per-class scale profile, env vars, envFrom `pl-fission-secrets`,
      podspec with the stock `ghcr.io/fission/python-env` image) + HTTPTrigger.
- [x] `terraform/fission-secrets.tf` — `kubernetes_secret.pl_fission_secrets`
      (INTERNAL_API_TOKEN + OPENROUTER_API_KEY from existing vars).
- [x] `tool_registry` function — deploy archive bundles its `handler.py` +
      `resources.json`; `GET /openapi.json` HTTPTrigger, no prefn (unauthed).
- [x] `pl_authorizer` — deployed as its own Fission Function
      (`pl-authorizer`), wired as `spec.prefns` on every tool HTTPTrigger
      (constant-time `hmac.compare_digest` on `X-Internal-Token`).
- [x] `health_rag_search` — NOT migrated; stays in-process on the agent pod.
- [x] Archive size proof: basic-math tools ~12 KB (boto3-only reqs); stats
      tools ~12 KB (reqs add pandas/numpy, pip-installed by builder NOT in
      zip); AI tools ~36 KB (reqs add httpx/jinja2 + vendored ai_config +
      22 `.j2` prompts); scipy tools add scipy. Biggest archive 88 KB.
      Total 96 archives = 2.0 MB. No per-pod bloat.
- [x] `terraform fmt -check -recursive` + `terraform validate` → Success.
      `py_compile` on all new `.py` → OK. Zero comments in code files.
- [ ] Smoke-test one deterministic read, one deterministic write, one AI tool
      end-to-end against the Fission router (requires `terraform apply` +
      Phase 3 routing swap — forward work).
- [ ] Smoke-test one deterministic read (e.g. `health_get_program`), one
      deterministic write (e.g. `health_update_session`), one AI tool
      (e.g. `fatigue_profile_estimate`) end-to-end against the Fission router
      via the backend's `invokeLambda` with `POWERLIFTING_LAMBDA_BASE_URL`
      swapped to `http://router.fission.svc.cluster.local`.

### Phase 3 — Auth + routing swap (no Cloudflare changes) [DONE — env swap wired in root terraform]
- [x] Register `pl_authorizer/handler.py` as a Fission pre-function attached to
      every function trigger (constant-time check against `INTERNAL_API_TOKEN`
      from the k8s Secret). Keep `GET /openapi.json` unauthed. — DONE in Phase 2:
      `pl_authorizer` deployed as its own Function + `spec.prefns` on every tool
      HTTPTrigger; `pl_fission_secrets` Secret declared in `k8s-secrets.tf`.
- [x] Do NOT add tinyauth middleware to the Fission router path — it is
      ClusterIP-only and has no public exposure. Tinyauth stays scoped to the
      existing `cloudflared`-exposed portal UIs in `if-portals`. — confirmed by
      design (no public Service/Ingress/HTTPRoute for Fission); verify post-apply.
- [x] Update backend env: `POWERLIFTING_LAMBDA_BASE_URL`
      `= http://router.fission.svc.cluster.local` — DONE in root `terraform/`:
      added to `kubernetes_config_map.powerlifting_app_config`, gated by
      `var.fission_enabled` (empty when Fission off → AWS API Gateway path).
      `INTERNAL_API_TOKEN` wired via new `kubernetes_secret.powerlifting_app_secrets`
      + `has_secrets = true` on the powerlifting-app portal so the
      `dynamic "env_from"` block injects it into the backend pod.
- [x] Update agent API + agent MCP pod envs the same. — DONE in root
      `terraform/`: `POWERLIFTING_LAMBDA_BASE_URL` added to
      `kubernetes_config_map.if_agent_api_config` (gated by `var.fission_enabled`);
      `INTERNAL_API_TOKEN` already in `kubernetes_secret.if_agent_api_secrets`.
      The `health_lambda` MCP subprocess (`tools/health_lambda_mcp/server.py`)
      inherits the agent pod env, so it gets both. The agent's
      `OPENCODE_FISSION_URL` already pointed at the Fission router.
- [x] Update `app/src/config.py` default for `POWERLIFTING_LAMBDA_BASE_URL`
      — left at empty default (the env is the source of truth; the pod env sets
      it). No code change needed.
- [ ] Confirm NO new Cloudflare tunnel / HTTPRoute / public Service exists
      for Fission. — verify post-apply (read-only kubectl/grep).

### Phase 4 — Scale-to-zero tuning + HPA [implemented — see FISSION_PHASE4_HPA.md]
- [x] Per-function `newdeploy` executor spec per tool class:
      - AI tools (15 deployed): `minReplicas=0`, `maxReplicas=1`, `targetCPU=70`,
        `SpecializationTimeout=120`, timeout 900s.
      - Stats tools (5): `minReplicas=0`, `maxReplicas=2`, `targetCPU=80`,
        `SpecializationTimeout=120`, timeout 900s.
      - High-traffic deterministic reads (10): `minReplicas=1`,
        `maxReplicas=2`, `targetCPU=70`, `SpecializationTimeout=60`.
      - Remaining deterministic (65): `minReplicas=0`, `maxReplicas=3`,
        `targetCPU=70`, `SpecializationTimeout=90`, timeout 900s.
- [x] HPA `--horizontal-pod-autoscaler-downscale-stabilization=120s` flag on the
      kube-controller-manager. k3s config is node-level (not Terraform-managed);
      runbook command in `FISSION_PHASE4_HPA.md` for the operator to run.
- [x] Fission owns the per-function HPA (newdeploy executor auto-creates one per
      Function; `TargetCPUPercent` in `ExecutionStrategy` is what Fission passes
      to its HPA). No separate `kubernetes_horizontal_pod_autoscaler` resources
      declared. Confirmed in `FISSION_PHASE4_HPA.md`.
- [x] WARM_READS expanded from 4 effective to 10 verified read-only tools
      (`fission_layers.py::WARM_READS`); `fission-functions.tf` regenerated.
- [ ] Soak test: invoke 3 tool types, idle 5 min, confirm pods scale to 0
      within 2 min and cold starts rehydrate in < 5s for deterministic / < 10s
      for AI (OpenRouter stream latency dominates the latter). Checklist in
      `FISSION_PHASE4_HPA.md` — operator-run.
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

## Resolved decisions (from implementation)

- [x] ~~(A) HostPath layer mount vs (B) composite image emptyDir mount~~ —
      RESOLVED: neither. Implemented design uses the Fission-native stock env
      image + per-tool `requirements.txt` pip-installed by the Fission builder.
      No HostPath, no composite image, no per-pod bloat. (Operator-directed
      revision 2026-06-28: the original HostPath/composite design forced a fat
      shared image that every pod would cold-start.)
- [x] ~~tinyauth middleware on Fission router vs Fission `pl_authorizer` pre-function
      hook~~ — DECIDED: Fission pre-function (`pl_authorizer` deployed as its
      own Function + `spec.prefns` on every tool HTTPTrigger). Tinyauth stays
      scoped to public Cloudflare-exposed portals only.
- [x] `OPENROUTER_API_KEY` + `INTERNAL_API_TOKEN` source — DECIDED: a k8s Secret
      `pl-fission-secrets` in `if-portals` carrying both (from the existing
      `var.pl_internal_token` + `var.openrouter_api_key`). Functions read them
      via `envFrom.secretRef`. SSM remains as the source for the AWS Lambda path
      until Phase 5 teardown; the k8s Secret is the Fission path's source.

## Open decisions to confirm before Phase 4 (HPA tuning)

- [ ] `minReplicas` for the warm pool on high-traffic deterministic reads — 1
      or 0? 1 = snappy UI but always-on ~80MB resident pod. Default: 1 for the
      ~10 highest-traffic reads. (Phase 2 set the 4 known warm reads to
      minReplicas=1; confirm the full warm list.)
- [ ] Max concurrent AI calls budget on node — 1, 2, or 3? Affects
      `maxReplicas` and HPA target for the 19 AI tools. (Phase 2 set AI
      maxReplicas=1; revisit if you want 2.)

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
