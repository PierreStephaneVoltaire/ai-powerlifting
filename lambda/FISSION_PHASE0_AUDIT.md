# Phase 0 Audit — Fission Substrate Migration

Status: COMPLETE (read-only). Confirms `FISSION_MIGRATION_PLAN.md` Phase 0 preconditions.

## Scope

This audit is the orchestrator-owned Phase 0 deliverable (read-only cluster + filesystem check). It produces the layer-bucket inventory that Phase 1 (foundation) and Phase 2 (per-folder Fission functions) consume. No application state was mutated. No `terraform plan/apply/destroy` was run.

## Cluster state — confirmed live via read-only kubectl

- Fission CRDs installed: `canaryconfigs.fission.io`, `environments.fission.io`, `functions.fission.io`, `httptriggers.fission.io`, `kuberneteswatchtriggers.fission.io`, `messagequeuetriggers.fission.io`, `packages.fission.io`, `timetriggers.fission.io`.
- Fission services in `fission` namespace are all `ClusterIP` (no public ingress): `router` (`10.43.228.243:80`), `executor`, `storagesvc`, `webhook-service`.
- Existing Fission `Environment`: `opencode-runner` (18d). No powerlifting env exists yet — Phase 1 must add one.
- Namespaces `fission` (18d) and `if-portals` (99d) both `Active`.
- Node `sirsimpalot-g5-5000`: CPU `1773m` / 11%, MEM `17969Mi` / 56% (~14 GB free). Fits the planned warm pool (~600-900 MB) plus 1-2 cold AI invocations (~500-1000 MB transient). Single k3s node — no horizontal scale-out.
- DNS: from `if-portals`, `router.fission.svc.cluster.local` resolves via cross-namespace cluster DNS. This is the Phase 3 `POWERLIFTING_LAMBDA_BASE_URL` value.
- Bot-root `terraform/k8s-fission.tf` already declares the Fission helm release + the `kubectl_manifest`/`kubernetes_*`/`kubectl_manifest` patterns for an Environment. The powerlifting surface should add a dedicated `Environment` (e.g. `pl-fission-tools`) so the newdeploy executor and scale config are isolated from `opencode-runner`.

## Tool inventory — 93 tool folders

Sourced from a parse of every `utils/powerlifting-app/lambda/<tool>/resources.yaml`. Non-tool folders carrying a `resources.yaml`: `pl_authorizer`, `tool_registry`, `analysis_section`, `master-sync` (these are wired specially in Phases 2-3; not all become per-tool Fission functions).

- AI tools (`pl_ai` layer): 19
  `block_correlation_analysis block_program_evaluation budget_advisor budget_priority_timeline correlation_analysis fatigue_profile_estimate glossary_estimate_e1rm glossary_estimate_fatigue glossary_estimate_muscles glossary_generate_text import_parse_file lift_profile_estimate_stimulus lift_profile_review lift_profile_rewrite lift_profile_rewrite_and_estimate multi_block_comparison_analysis muscle_group_estimate program_evaluation template_evaluate`
- Stats / pandas tools (`pl_pandas` layer): 4
  `analyze_powerlifting_stats analyze_rpe_drift powerlifting_filter_categories powerlifting_ranking_percentile`
- Deterministic tools (no `pl_ai`, no `pl_pandas`): 70 — DynamoDB CRUD, math/units, templates, imports, analysis reads.

## Layer usage (bridge to the 4 Fission layer-mount buckets)

`pl_boto3:86, pl_program:65, pl_templates:15, pl_sessions:13, pl_ai:19, pl_glossary:8, pl_analysis_cache:4, pl_pandas:4, pl_imports:3, pl_federation:2` — collapses to:

| Fission bucket | Contents | Source layers |
|---|---|---|
| `pl_base` | httpx, jinja2, boto3, botocore, s3transfer | `pl_boto3` + the httpx/jinja2 portion of `pl_ai` |
| `pl_health_data` | program/sessions/templates/glossary/imports/federation/analysis-cache stores + `core.py`, `health_types.py`, `comparison.py`, `powerlifting_stats.py`, `program_store.py` etc. | `pl_program`, `pl_sessions`, `pl_templates`, `pl_glossary`, `pl_imports`, `pl_federation`, `pl_analysis_cache` |
| `pl_prompts` | `prompts/loader.py` + the 24 `.j2` files | the prompt-file portion of `pl_ai` |
| `pl_stats` | pandas, numpy, scipy | `pl_pandas` |

The per-tool `PYTHONPATH` is derived from its `resources.yaml` `layers:` list via the translation table in `fission_layers.py` (the shared Phase 0 contract artifact). Read-only layer mounts are page-cached once on disk; concurrent pods share RAM pages.

## Files this audit lands

- `utils/powerlifting-app/lambda/FISSION_PHASE0_AUDIT.md` (this file — orchestrator-owned).
- `utils/powerlifting-app/lambda/fission_layers.py` (orchestrator-owned machine-readable layer-bucket contract consumed by Phase 1 builds and Phase 2 `fission-deploy.py`).

## Open items deferred to the relevant phase

- Env image ECR repo + `kubectl_manifest` providers must be added to `utils/powerlifting-app/terraform/` (`versions.tf` is currently aws-only). Owned by `pl-fission-env` in Phase 1.
- `/opt/pl-layers` populate mechanism: prefer HostPath readOnly mount (plan option A) via an init DaemonSet; falls back to composite image emptyDir (option B) only if node-image constraints forbid.
- `health_rag_search` stays in-process on the agent pod (ChromaDB) — NOT migrated.
- `resources.json` (94 entries) and the per-folder `resources.yaml` survive the substrate swap unchanged; `tool_registry` just gains a Fission HTTP trigger at `GET /openapi.json`.

## Next

Phase 1 (foundation, serial) — `pl-fission-env` subagent builds the 4 layer-mount archives, the slim `pl-fission-env` Docker image, the Fission `Environment` CR + hostPath terraform, and adds the required kubectl/kubernetes providers. Verified by `terraform fmt/validate` + `py_compile` + the per-bucket `import` smoke.
