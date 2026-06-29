# Fission Substrate Migration — Implementation

Status: COMPLETE (Phases 0-2). terraform fmt/validate green in BOTH roots.
Per-tool lean deploy archives built (96 zips, 2.0 MB total). Phases 3-7 forward.

## Architecture (corrected, Fission-native)

No custom Packer image. No hostPath layers. No bloated per-pod image. The
Fission-native path:

- **Env**: stock `ghcr.io/fission/python-env` (runtime, shared by all functions,
  pulled once) + `ghcr.io/fission/python-builder` (runs
  `pip install -r requirements.txt` at build time). Declared in
  `terraform/fission-functions.tf` as a single `Environment` CR
  (`pl-fission-tools`, version 3, keeparchive false).
- **Per-tool deploy archive**: each tool's `.py` files + the store modules its
  `resources.yaml layers:` references (vendored at archive root so
  `from program_store import ...` resolves) + a `requirements.txt` listing ONLY
  the pip deps those layers bring + `fission_entry.py` (the shared adapter).
  The Fission builder pip-installs the requirements into the archive at build
  time and produces the deploy archive. Basic-math tools carry only boto3;
  stats tools add pandas/numpy; AI tools add httpx/jinja2; the 2 scipy tools add
  scipy. No tool carries deps it doesn't use.
- **MCP exposure**: each Function carries `spec.tool` (Fission `ToolConfig`,
  the `--expose-as-mcp` flag) with `name`, `description`, and `inputSchema`
  sourced from the tool's `resources.yaml`. Fission's router exposes an MCP
  server endpoint, so the IF agent consumes the tools directly via MCP — no
  `tools/health_lambda_mcp/` HTTP-discovery intermediary needed for the agent
  path. The portal backend still hits the Fission router HTTP (`POST /<tool>`)
  for UI calls.
- **`fission_entry.py`** (~25 lines): the shared Fission entrypoint. Fission's
  `server.py` loads the deploy archive at `/userfunc` and calls the module's
  `main` with the Flask request. The adapter builds the Lambda-style event
  `{args: <body>, headers: {...}}`, imports the tool's `handler`, calls
  `handler(event, None)`, returns the `{statusCode, body}` envelope.

## Terraform topology (multi-repo)

Per the `.meta` config + the powerlifting `AGENTS.md`:
- **Root `terraform/`** (repo root, applied locally against the private k3s
  kubeconfig — GitHub Actions can't reach the private cluster): owns all k8s
  resources including the generated Fission CRDs. Contains:
  - `terraform/fission-functions.tf` — generated Environment + 96 Package +
    96 Function (with `spec.tool` MCP exposure) + 95 HTTPTrigger + pl_authorizer.
  - `terraform/fission-build/*.zip` — 96 per-tool deploy archives.
  - `terraform/k8s-secrets.tf` — `kubernetes_secret.pl_fission_secrets` (gated
    by `var.fission_enabled`) + `INTERNAL_API_TOKEN` added to
    `if_agent_api_secrets`.
  - `terraform/variables.tf` — `powerlifting_s3_bucket`, `pl_internal_token`.
- **`utils/powerlifting-app/terraform/`** (AWS-only, GitHub Actions): owns ECR,
  S3, Lambda, API Gateway, SSM, DynamoDB. NO k8s resources. Clean of all
  Fission references (the wrongly-placed files were moved out).
- **`utils/powerlifting-app/lambda/`** (the powerlifting repo, source of truth):
  the tool handlers, layers, `fission_entry.py`, `fission_layers.py`,
  `fission-deploy.py` (the generator that reads from here and writes to the
  repo-root `terraform/`).

## Archive sizes (proof of leanness)

- `calculate_attempts` (basic math): 12 KB — requirements.txt = boto3 only.
- `analyze_powerlifting_stats` (stats): 12 KB — requirements.txt = boto3 +
  pandas + numpy (wheels pip-installed by builder, NOT in the zip).
- `fatigue_profile_estimate` (AI): 36 KB — requirements.txt = httpx + jinja2 +
  boto3; ai_config.py + 22 .j2 prompts + loader.py vendored.
- `analyze_progression`/`analyze_rpe_drift` (scipy): requirements.txt adds scipy.
- Biggest archive: `export_program_history` = 88 KB. Total `fission-build/` =
  2.0 MB across 96 zips.

## Generated counts

- 96 Package (95 tools + pl_authorizer)
- 96 Function (95 tools with `spec.tool` MCP exposure + pl_authorizer)
- 95 HTTPTrigger (94 tool POST routes gated by pl-authorizer prefn +
  1 `tool_registry` GET `/openapi.json` unauthed)
- 1 Environment + 1 kubernetes_secret (pl_fission_secrets) +
  INTERNAL_API_TOKEN in if_agent_api_secrets
- Tool classes: 15 AI (minReplicas 0), 4 warm reads (minReplicas 1), 5 stats
  (minReplicas 0), 71 deterministic (minReplicas 0)

## Auth wiring

`pl_authorizer` is its own Fission Function with `INTERNAL_API_TOKEN` from the
`pl-fission-secrets` Secret via `valueFrom.secretKeyRef`. Every tool HTTPTrigger
carries `spec.prefns: [{name: pl-authorizer, namespace: if-portals}]` so the
`hmac.compare_digest` token check runs before the main function.
`GET /openapi.json` (tool_registry) has no prefn — stays unauthed.

## Files

- `lambda/fission_entry.py` — shared Fission entrypoint adapter.
- `lambda/fission_layers.py` — layer→(modules, pip-requirements) contract +
  tool classification + scale profiles.
- `lambda/fission-deploy.py` — generator. `--dry-run` prints counts; default
  builds the 96 zips under `terraform/fission-build/` and emits
  `terraform/fission-functions.tf`. Reads source from `utils/powerlifting-app/lambda/`
  and writes terraform to repo-root `terraform/` (per multi-repo topology).
- `terraform/fission-functions.tf` — generated (repo root).
- `terraform/k8s-secrets.tf` — `pl_fission_secrets` + `INTERNAL_API_TOKEN` in
  `if_agent_api_secrets`.
- `terraform/variables.tf` — `pl_internal_token`, `powerlifting_s3_bucket`.

## Verification

- `terraform fmt -check -recursive` → Success (both roots)
- `terraform validate` → Success (both roots)
- `python3 -m py_compile fission_entry.py fission_layers.py fission-deploy.py` → OK
- `python3 fission-deploy.py --dry-run` → 95 deployable tools
- 96 zips built, 2.0 MB total, biggest 88 KB (deps NOT baked in)
- 95 Functions carry `spec.tool` (MCP exposure)
- No comments in code files; no `AWS_REGION` env name (uses `IF_AWS_REGION`)
- App terraform clean of all Fission references (AWS-only stack)

## Regenerate

After any handler or layer change:
`cd utils/powerlifting-app/lambda && python3 fission-deploy.py`
Rebuilds the zips under `terraform/fission-build/` and regenerates
`terraform/fission-functions.tf` (in the repo root, per the multi-repo topology).

## Deploy

`cd terraform && terraform apply` (root stack, applied locally against the
private k3s kubeconfig — gated, with your explicit nod). The Environment +
secret apply first, then Fission builds each package (builder pip-installs
requirements.txt), then functions specialize on demand. Phase 3 flips
`POWERLIFTING_LAMBDA_BASE_URL` for the backend HTTP path + wires the agent to
the Fission MCP endpoint.
