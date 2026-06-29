# Fission Substrate Migration — Implementation

Status: COMPLETE. terraform fmt/validate green. Per-tool lean deploy archives built (96 zips, 2.0 MB total — deps pip-installed by Fission builder, NOT baked in).

## Architecture (corrected)

No custom Packer image. No hostPath layers. No bloated per-pod 2GB image. The Fission-native path:

- **Env**: stock `ghcr.io/fission/python-env` (runtime, shared by all functions, pulled once) + `ghcr.io/fission/python-builder` (runs `pip install -r requirements.txt` at build time). Declared in `fission-functions.tf` as a single `Environment` CR (`pl-fission-tools`, version 3, keeparchive false).
- **Per-tool deploy archive**: each tool's `.py` files + the store modules its `resources.yaml layers:` references (vendored at archive root so `from program_store import ...` resolves) + a `requirements.txt` listing ONLY the pip deps those layers bring + `fission_entry.py` (the shared adapter). The Fission builder pip-installs the requirements into the archive and produces the deploy archive. **Basic-math tools carry only boto3; stats tools add pandas/numpy; AI tools add httpx/jinja2; the 2 scipy tools add scipy. No tool carries deps it doesn't use.**
- **`fission_entry.py`** (~25 lines): the shared Fission entrypoint. Fission's `server.py` loads the deploy archive at `/userfunc` and calls the module's `main` with the Flask request. The adapter builds the Lambda-style event `{args: <body>, headers: {...}}`, imports the tool's `handler`, calls `handler(event, None)`, returns the `{statusCode, body}` envelope the backend expects.

## Archive sizes (proof of leanness)

- `calculate_attempts` (basic math): 12 KB — contents = handler/core/config + program_store.py + fission_entry.py + requirements.txt(boto3 only). No pandas, no httpx.
- `analyze_powerlifting_stats` (stats): 12 KB — requirements.txt = boto3 + pandas + numpy. Wheels pip-installed by builder, NOT in the zip.
- `fatigue_profile_estimate` (AI): 36 KB — requirements.txt = httpx + jinja2 + boto3; ai_config.py + 22 .j2 prompts + loader.py vendored.
- `analyze_progression`/`analyze_rpe_drift` (scipy): requirements.txt adds scipy.
- Biggest archive: `export_program_history` = 88 KB. Total `fission-build/` = 2.0 MB across 96 zips.

## Generated counts

- 96 Package (95 tools + pl_authorizer)
- 96 Function (95 tools + pl_authorizer)
- 95 HTTPTrigger (94 tool POST routes gated by pl-authorizer prefn + 1 `tool_registry` GET `/openapi.json` unauthed)
- 1 Environment + 1 kubernetes_secret
- Tool classes: 15 AI (minReplicas 0), 4 warm reads (minReplicas 1), 5 stats (minReplicas 0), 71 deterministic (minReplicas 0)

## Auth wiring

`pl_authorizer` is its own Fission Function with `INTERNAL_API_TOKEN` from the `pl-fission-secrets` Secret via `valueFrom.secretKeyRef`. Every tool HTTPTrigger carries `spec.prefns: [{name: pl-authorizer, namespace: if-portals}]` so the `hmac.compare_digest` token check runs before the main function. `GET /openapi.json` (tool_registry) has no prefn — stays unauthed.

## Files

- `lambda/fission_entry.py` — shared Fission entrypoint adapter.
- `lambda/fission_layers.py` — layer→(modules, pip-requirements) contract + tool classification + scale profiles.
- `lambda/fission-deploy.py` — generator. `--dry-run` prints counts; default builds the 96 zips under `terraform/fission-build/` and emits `terraform/fission-functions.tf`.
- `terraform/fission-functions.tf` — generated. Environment CR + 96 Package/Function/HTTPTrigger `kubectl_manifest` blocks.
- `terraform/fission-secrets.tf` — `kubernetes_secret.pl_fission_secrets` (INTERNAL_API_TOKEN + OPENROUTER_API_KEY).
- `terraform/versions.tf` + `providers.tf` + `variables.tf` + `outputs.tf` — kubectl/kubernetes/helm providers, kubeconfig vars, fission env/router outputs.

## Verification

- `terraform fmt -check -recursive` → Success
- `terraform validate` → Success
- `python3 -m py_compile fission_entry.py fission_layers.py fission-deploy.py` → OK
- `python3 fission-deploy.py --dry-run` → 95 deployable tools (15 AI / 4 warm / 5 stats / 71 det)
- 96 zips built, 2.0 MB total, biggest 88 KB (deps NOT baked in — in requirements.txt for the builder)
- No comments in code files; no `AWS_REGION` env name (uses `IF_AWS_REGION`)

## Deploy

`cd utils/powerlifting-app/terraform && terraform apply` (gated, with your explicit nod). The Environment + secret apply first, then Fission builds each package (builder pip-installs requirements.txt), then functions specialize on demand. Backend `POWERLIFTING_LAMBDA_BASE_URL=http://router.fission.svc.cluster.local` (Phase 3 routing swap).

## Regenerate

After any handler or layer change: `cd utils/powerlifting-app/lambda && python3 fission-deploy.py` rebuilds the zips and regenerates `fission-functions.tf`.
