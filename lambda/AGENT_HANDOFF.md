# Agent handoff — health tool runtime substrate migration

**Read these four files in this order, then act on what's open.**

1. `utils/powerlifting-app/lambda/HEALTH_LAMBDA_MIGRATION_PLAN.md` — the current
   state. Phases 1-3 are DONE. The 75 deterministic tools + 19 AI tools (94 total)
   + `pl_authorizer` + `tool_registry` are deployed as AWS Lambdas behind an
   HTTP API Gateway. Phase 4 (observability) is PENDING.
2. `utils/powerlifting-app/lambda/FISSION_MIGRATION_PLAN.md` — the planned
   follow-on. All phases NOT-STARTED. Replaces the AWS Lambda + API Gateway
   substrate with in-cluster Fission router (cluster-private, no Cloudflare),
   keeping the per-folder `resources.yaml` model, the OpenAPI registry, the
   agent `health_lambda` MCP server, the backend `invokeLambda` + LRU cache.
3. `utils/powerlifting-app/POWERLIFTING_FEATURES_BACKLOG.md` — user-story
   backlog for the next set of portal features (session-detail UX bugs, lift
   profile videos + failure nodes, onboarding, multi-role RBAC, athlete/coach/
   handler flows, search + temporary-`mapped_pk`-or-`pk` navigation state,
   relationship requests, profile tags). Implement AFTER the substrate
   migration is settled. The first decision the operator must make for the
   features is the identity/RBAC mechanism (Keycloak vs Ory vs Cognito) — ask
   before any feature epic starts.
4. This file — `AGENT_HANDOFF.md` — operating context, file map, team-subagent
   fire pattern, hard constraints.

The operator's standing instruction is:

> Read these 4 files and use the team-subagent to do the actual work, and favour
> parallel invocation of those teams when there are no overlap of files.

That is the directive you are executing.

## Background you need to know (don't skip)

Read `AGENTS.md` at repo root FIRST. It is the constitution — it covers tech
stack, the Tanzoperation repo layout, the DynamoDB-Decimal rule (always convert
floats to `Decimal(str(x))` before any boto3 write), the paid-test-namespace
rule (`if-portals-test`, `pk=test`, never `operator` except in production),
the portal verification sequence (build-test-images.sh → port-forward → pod
logs, NOT local Vite), the no-mutating-terraform rule, the no-git-writes rule,
the no-AWS-deletes rule. You must internalize all of this before writing any
code or running any command.

### The substrate migration at a high level

The `powerlifting_coach` workflow in the Discord bot historically called ~94
`tools/health/` Python functions **in-process** — meaning the agent pod had to
bundle `httpx`, `jinja2`, `chromadb`, `pandas`, `numpy`, `scipy`, all the health
store modules, and 24 LLM system-prompt `.j2` files. That bloated the agent
image to 3GB and made every agent pod start slow. The migration moves these 94
functions out of the agent pod into separately-deployable compute units so the
agent image shrinks and only `health_rag_search` (which needs local ChromaDB)
stays in-process on the agent.

### Why two plan files

The first migration (LAMBDA) moved the 94 tools onto AWS Lambda + HTTP API
Gateway with a `pl_authorizer` request-authorizer gate and a backend in-process
LRU cache with write invalidation. Work is functionally complete — code,
Terraform, and `resources.json` exist and validate green. However, the operator
needs the observability and Phase 4 polish, AND/OR is pursuing an in-cluster
Fission replacement of the whole AWS layer for cost-and-resource reasons. The
Fission plan picks up from wherever the Lambda plan leaves off and swaps the
runtime substrate out without re-doing the per-tool logic, the OpenAPI registry,
or any of the agent-side discovery.

## Current state on disk (snapshot as of when this was written)

### Working & verified green
- All 94 Lambda function folders exist under
  `utils/powerlifting-app/lambda/<tool>/` — each has `handler.py`, `config.py`,
  `__init__.py` (empty), `requirements.txt` (empty BY DESIGN — deps come from
  Lambda Layers via `/opt/python` on `PYTHONPATH`, not from a pip-install step;
  read the foundation section of the LAMBDA plan if this surprises you),
  `resources.yaml`.
- 10 Lambda layer dirs under `utils/powerlifting-app/lambda/layers/`: `pl-ai`,
  `pl-boto3`, `pl-program`, `pl-sessions`, `pl-glossary`, `pl-templates`,
  `pl-imports`, `pl-federation`, `pl-analysis-cache`, `pl-pandas`.
- `lambda/pl_authorizer/` — the `X-Internal-Token` authorizer handler + its
  `resources.yaml`.
- `lambda/tool_registry/` — serves `GET /openapi.json` from `resources.json`
  (currently has 94 tool entries with description + input_schema).
- `utils/powerlifting-app/terraform/`: `lambda.tf`, `layers.tf`, `apigateway.tf`,
  `authorizer.tf`, `ssm.tf` — all validate green.
- `utils/powerlifting-app/backend/src/utils/lambda.ts` `invokeLambda` +
  `lambdaCache.ts` (LRU + invalidation) — `npm run build` green.
- `tools/health_lambda_mcp/server.py` reads `POWERLIFTING_LAMBDA_BASE_URL`
  + `INTERNAL_API_TOKEN` from env, sends `X-Internal-Token`, routes via `POST
  ${BASE}/${tool}`. Registered as `health_lambda` MCP category in
  `app/src/mcp_runtime/manager.py` + `app/src/config.py::MCP_SERVER_CATEGORIES`.
- `tools/health_lambda_mcp/README.md`.

### What's NOT shipped yet
- Lambda **Phase 4 (observability)** — the deferred CloudWatch → Vector → Loki
  path. If the operator goes straight to the Fission plan, this becomes moot:
  Fission pods log to stdout → existing `promtail` DaemonSet ships them to Loki
  with zero new plumbing. **Do not implement the Lambda Phase 4 if the operator
  has chosen the Fission path** — it's wasted work.
- `AGENTS.md` migration section — the `## Powerlifting Health Lambda Migration`
  H2 was never written by the original `docs` subagent. Needs to land to reflect
  either the Lambda-complete state OR the Fission-complete state depending on
  the path chosen.
- `HEALTH_LAMBDA_MIGRATION_PLAN.md` — only partially cleaned up (Phase 1-3
  checkbox deltas are rough, no Phase 2.5 / Phase 4 structure as the plan
  intended). Worth a `docs` rewrite pass when you have a quiet moment.

## The two paths (pick one based on operator's call)

If the operator says **continue the AWS-Lambda track** → implement the deferred
Phase 4 (observability) of the LAMBDA plan + the AGENTS.md/docs polish.

If the operator says **do the Fission swap** → start the FISSION plan from Phase
0. Most LAMBDA-plan work is preserved (per-folder folders, `resources.yaml`,
`resources.json`, OpenAPI registry, agent MCP server, backend LRU cache).

If the operator says **do both, Lambda polish first** → scope the Lambda polish to
the must-do (`AGENTS.md` migration section + plan checkbox cleanup +
observability IF they don't plan to switch), then move to the Fission plan.

Default if operator gives no preference: ASK. Use `ask_question` with 2-3
options. Never guess between "continue AWS" vs "swap to Fission" — those are
weeks apart in implementation effort.

## File ownership boundaries (critical for team-subagent firing)

These boundaries are the SOURCE OF TRUTH for what each subagent can write.
Cross-boundary edits cause git-soup and were the original cause of wasted
quota. NEVER let two subagents write to the same file. If two subagents both
need to touch a file (e.g. `apigateway.tf` + `authorizer.tf` + `lambda.tf` all
need `ssm.tf` data sources), serialize those — Wave 1 fixes the shared file,
Wave 2 fans out on strictly-owned distinct files.

### Bot repo (`/home/sirsimpalot/Downloads/discord-ai-bot/`)

- `AGENTS.md` — owned by `docs` subagent only.
- `app/src/config.py` — owned by `agent-mcp` subagent only (the
  `POWERLIFTING_LAMBDA_BASE_URL` + `MCP_SERVER_CATEGORIES` lines).
- `app/src/mcp_runtime/manager.py` — owned by `agent-mcp` subagent only.
- `tools/health_lambda_mcp/server.py` — owned by `agent-mcp` subagent only.
- `tools/health_lambda_mcp/README.md` — owned by `docs` subagent only.
- `tools/health/*.py` and `tools/health/prompts/*.j2` — READ ONLY for
  subagents. They are SOURCE-OF-TRUTH for the tool functions and the AI system
  prompts. Never edit these to "convert to lambda/fission" — instead, each
  per-tool lambda/fission folder COPIES the relevant `*_ai.py` into its own
  folder and edits the COPY.
- `terraform/k8s-*.tf` — cluster-level k8s resources (namespace, observability,
  fission helm release, tinyauth, cloudflared, secrets, rbac, services).
  Phase boundaries inside the Fission plan say exactly which file each phase
  writes. Do not let the `docs` subagent touch these.

### Powerlifting-app repo (`utils/powerlifting-app/`)

- `lambda/<tool>/` — per-tool folder. Owned by whichever `ai-N` / `deterministic-N`
  subagent owns THAT tool's cluster (see FISSION plan Phase 2 for cluster/group
  list). One subagent per tool group.
- `lambda/layers/` — owned by `pl-ai-foundation` subagent only (LAMBDA plan) or
  `pl-fission-env` subagent only (FISSION plan Phase 1).
- `lambda/tool_registry/` — `handler.py` stays; `resources.json` is WHOLLY
  OWNED by the `tool-registry` subagent who regenerates it from per-folder
  `resources.yaml` AFTER all per-tool subagents land (end-of-wave regeneration).
- `lambda/pl_authorizer/` — owned by `api-gateway-authz` subagent (LAMBDA plan) —
  reused as-is by the FISSION plan's Phase 3 pre-function worker.
- `terraform/lambda.tf`, `layers.tf`, `apigateway.tf`, `authorizer.tf`, `ssm.tf`,
  `iam.tf`, `variables.tf` — owned by `pl-ai-foundation` + `api-gateway-authz`
  subagents in the LAMBDA plan (per the plan's phase boundaries). NOT touched
  after the Fission swap (Phase 5 tears them down).
- `terraform/fission-*.tf` — owned by `fission-functions` subagent only (FISSION
  plan Phase 2).
- `terraform/k8s-*.tf` if any new file (for the slim env / hostPath — e.g.
  `k8s-fission-powerlifting.tf`) — owned by `pl-fission-env` subagent only.
- `backend/src/utils/lambda.ts` — owned by `backend-rewire-cache` subagent
  only.
- `backend/src/utils/lambdaCache.ts` — same owner as above.
- `backend/src/routes/*.ts`, `backend/src/services/*.ts` — owned by
  `backend-rewire-cache` subagent only (any invokeToolDirect / invokeLambda swap
  + cache thread).
- `backend/src/utils/agent.ts` — READ-ONLY. Keep the in-process health path
  alive for `health_rag_search`.
- `backend/package.json` — owned by `backend-rewire-cache` subagent, only if a
  dependency must be added (no new dep expected).
- `Dockerfile`, `docker/` — owned by `pl-fission-env` (FISSION plan Phase 1) for
  the slim env image build.

## Team-subagent fire pattern (favour parallel, never overlap)

You have 6+1 subagents from the previous fan-out. The pattern that worked:

1. **Plan-verify first** (single-agent, you, ~30 seconds). Read the 3 plan
   files + `AGENTS.md`. Confirm which path the operator picked (or ask). Do
   not spawn anything until you know the path.
2. **Wave 1 — foundation serially** (1 subagent). The foundation subagent owns
   the shared contract files that every other subagent reads. Do NOT fan out
   until this lands, because every other subagent depends on its output
   (`layer_arns` map, `lambda_common_env`, SSM data sources, hostPath layer
   mounts, slim env image, etc., depending on the plan). Use `team_run_task`
   `runMode="sync"` for this one and await it before going further.
3. **Wave 2 — fan out parallel** (N subagents, all async). Each owns strictly
   non-overlapping files. Dispatch all Wave-2 team tasks in ONE
   `team_run_task`-per-agent block — they all return `queued` and run
   concurrently. This is the operator's "favour parallel invocation" directive.
   Use `runMode="async"` for each.
4. **Wave 3 — regeneration serially** (1 subagent). After Wave 2 lands, the
   `tool-registry` subagent regenerates `resources.json` from the per-folder
   `resources.yaml` (so the OpenAPI doc + agent MCP discovery include every
   newly-created or moved tool). This must run LAST in the wave order —
   run-mode `sync`, await it.
5. **Wave 4 — verification serially** (you, single agent). Run `terraform
   fmt`/`validate` both stacks. `npm run build`. `py_compile` across every
   new folder. `grep` for stray comments, reserved AWS env-var leakage
   (`AWS_REGION`), escaped-`\n` artifacts from editor misadventures. Report.

### Per-phase subagent cluster (FISSION plan — operator's likely path)

Match each FISSION phase to one of these subagent teams:

- **Phase 0 (audit, no writes)**: you, single agent, read-only commands.
- **Phase 1 (slim env + layer mounts)**: 1 subagent `pl-fission-env` (owns the
  env image, the hostPath setup, `terraform/k8s-fission-powerlifting.tf`
  if created, `Dockerfile` for env). Serially.
- **Phase 2 (per-folder handlers → Fission functions)**:
  - `fission-cluster-1` (deterministic reads + math, the 75): own their folders + terraform fragment
  - `fission-cluster-2` (19 AI tools): own their folders + terraform fragment
  - `fission-cluster-3` (`tool_registry` + `pl_authorizer` wiring as Fission pre-function): owns those folders + fission env spec overrides
  All three fan out in parallel.
- **Phase 3 (auth + routing swap)**: 1 subagent `backend-routing-swap` (owns
  `backend/src/utils/lambda.ts` env read + `app/src/config.py` + manifest envs).
  Serially after Phase 2 lands.
- **Phase 4 (HPA / scale-to-zero)**: 1 subagent `fission-hpa` (owns HPA
  configs + Fission `Function` spec executor overrides). Can run parallel with
  Phase 3 — different files.
- **Phase 5 (AWS teardown + secret source migration)**: 1 subagent
  `teardown-aws` (owns removal of `lambda.tf`, `layers.tf`, `apigateway.tf`,
  `authorizer.tf`, `ssm.tf`, `iam.tf` + k8s Secret creation). Serially after
  operator approval only — `terraform destroy -target` requires the operator's
  explicit nod per `AGENTS.md`.
- **Phase 6 (observability)**: 1 subagent `grafana` (owns the existing
  `terraform/k8s-observability.tf` dashboard ConfigMap additions only).
- **Phase 7 (docs + cutover)**: 1 subagent `docs` (owns `AGENTS.md` + both
  migration plan files + `tools/health_lambda_mcp/README.md`). Serially at end.

### Per-phase subagent cluster (LAMBDA plan continuation — if operator picks this)

- **Lambda Phase 4 (observability)**: `observability` (owns new
  `terraform/k8s-cloudwatch-exporter.tf` if used, additions to
  `k8s-observability.tf` dashboards, optional `lambda.tf` CloudWatch alarms).
- **Lambda polish (docs + AGENTS.md + plan cleanup)**: `docs` (owns Markdown
  only). Parallel-safe with `observability` (no file overlap).

## Hard rules (re-stated because quota got burned on these before)

1. **No comments.** `grep -c '^[[:space:]]*#' <file>` must return 0 in any
   file you write. Shebangs are the only exception. The operator has been
   explicit about this twice.
2. **No reserved AWS env vars.** `AWS_REGION`, `AWS_DEFAULT_REGION`, etc. are
   reserved by the Lambda runtime and CANNOT be set by user env. Lambda handlers
   read the live region from the runtime context, not from env.
3. **No escaped-`\n` artifacts.** The default `editor` tool has a bug where
   multi-line new_content becomes a single-line string with literal `\n`. For
   ANY multi-line file edit, use `run_commands` with a Python `pathlib`
   `read_text`/`replace`/`write_text` block, OR `sed -i`. NEVER the `editor`
   tool for anything longer than a single line. I repeat: NEVER `editor` for
   multi-line.
4. **No inference.** When an `*_ai.py` function signature is vague, read it
   FIRST — don't write a Lambda handler that calls a function name that doesn't
   exist. `grep -n '<tool_name>' tools/health/tool.py` finds the ROUTES mapping
   line; the actual function follows.
5. **DynamoDB floats**. Any handler or layer code that writes to DynamoDB must
   convert Python `float` to `Decimal(str(x))` before any put/update. Reuse the
   existing helpers (`ProgramStore._floats_to_decimals`, etc.).
6. **Single test namespace**. `if-portals-test`, `pk=test`, never `operator`.
   `HEALTH_PROGRAM_PK=test`. Test models use `deepseek/deepseek-v4-flash`.
7. **Portal verification** is via pod → `kubectl port-forward` → browser, not
   `npm run dev` against a local Vite. After Fission swap: same pattern,
   `POWERLIFTING_LAMBDA_BASE_URL` overridden in the test backend to the
   in-cluster Fission router DNS. Local Vite is supporting evidence only.
8. **File-boundary conflicts are quota-killing**. Re-read the ownership table
   above. If two subagent tasks would touch the same file, serialize them.
   NEVER overlap.
9. **No `terraform apply`, `terraform destroy` without operator approval.**
   `terraform fmt`/`validate`/`plan` are fine. The Fission plan's Phase 5
   teardown needs an explicit `ask_question` green-light first.
10. **No git writes, no AWS deletes, no kubectl mutate.** AGENTS.md covers all of
    this.

## Tools you have

- `read_files` — read multiple files in one call; always batch.
- `search_codebase` — regex search across repo; prefer narrow patterns.
- `run_commands` — non-interactive shell. Batch independent commands.
- `fetch_web_content` — for AWS provider docs / Fission CRD schema if needed.
- `ask_question` — for operator decisions (LAMBDA-cont vs Fission swap,
  teardown green-light, found-vs-built ambiguities).
- `spawn_agent` — spawn a one-shot subagent for a focused task. Useful for
  file-boundary-strict writes where the agent won't need to share context with
  others.
- `team_spawn_teammate` / `team_run_task` / `team_await_runs` — the
  parallel-subagent system. Use `team_spawn_teammate` once per role at start,
  then `team_run_task` to dispatch work to each. `runMode="async"` fans out;
  `runMode="sync"` awaits. ALWAYS `team_await_runs` before reporting done.
- `team_shutdown_teammate` — clean up at end. Failing to do this leaves zombie
  teammates consuming quota even after their runs finish.

## Quota discipline (because it got burned before)

- Subagents have a 5-hour rolling quota; firing 7+ in one shot when only 4 are
  load-bearing causes the runtime to kill the extra ones at the 5h mark mid-run
  and leave half-written files on disk.
- Prefer 2-4 parallel subagents at a time over 6+. Each phase of the FISSION
  plan CAN be done in 2-3 parallel passes plus a serial foundation + serial
  regeneration wrapper.
- If `team_await_runs` returns `run_error` with "5-hour usage limit reached",
  check the filesystem with `run_commands` (any half-written folders? any
  broken `.tf` / `resources.yaml` entries that block `terraform validate`?).
  Then `team_shutdown_teammate` the dead ones and `team_spawn_teammate`
  replacements with the SAME role-prompt + a note "PARTIAL STATE — prior run
  was killed mid-write. Verify filesystem before proceeding."
- Never let a subagent verifier block on quota. Do the verification yourself in
  the orchestrator agent using `run_commands`.

## Smoke test at the end of every phase

For either plan path, before declaring a phase done:

- `terraform fmt -check` in `utils/powerlifting-app/terraform/` → Success
- `terraform validate` in same dir → Success
- `npm run build` in `utils/powerlifting-app/backend/` → green
- `python -m py_compile` across every new `.py` file
- `grep -c '^[[:space:]]*#' <every written .py/.ts/.tf>` = 0 (modulo shebangs)
- `grep -rn 'AWS_REGION' utils/powerlifting-app/terraform/lambda.tf` = 0
- `python3 -c "import json; len(json.load(open('utils/powerlifting-app/lambda/tool_registry/resources.json')))" ` returns the count of deployed tools if the registry was touched.
- (After Fission swap) Test invocation: a `curl" or `python`-based POST to
  `router.fission.svc.cluster.local/health_get_program` from a pod with the
  INTERNAL_API_TOKEN env, confirms end-to-end.

If any check fails, fix the offending file IN THE ORCHESTRATOR (you) before
reporting to the operator. Do not punt verification failures back to the user.

## Where to stop and report back

At the end of every phase (or every wave), report to the operator with:
- What landed (file deltas).
- Verification output (validate / build / py_compile / grep-comment-counts).
- What's next on the other plan path (if relevant).
- Any decisions you want operator confirmation on (e.g. teardown green-light,
  HPA timeout values, hostPath vs composite-image layer mount).

Never report "done" with a broken `terraform validate`. Never. The operator's
previous frustration was largely with "thinking" reported as work and quota
burned without file writes landing. Every phase ends with files on disk + a
verification sweep by you. That is the contract.

## TL;DR for a fresh agent

1. `AGENTS.md` → read in full first.
2. `utils/powerlifting-app/lambda/HEALTH_LAMBDA_MIGRATION_PLAN.md` — current
   state (Phases 1-3 done).
3. `utils/powerlifting-app/lambda/FISSION_MIGRATION_PLAN.md` — planned
   follow-on (all phases not started).
4. `utils/powerlifting-app/lambda/AGENT_HANDOFF.md` (this file) — the contract.
5. Ask the operator: AWS-Lambda continuation OR Fission swap?
6. Spawn `pl-fission-env` (or `observability`+`docs` if Lambda-polish path).
7. Sync-await foundation → fan-out async Workload 2-3 parallel subagents →
   sync-await regeneration → verification sweep by you.
8. Files on disk, `terraform validate` green, build green, no comments, no
   reserved env vars, no half-written editors.
9. Report honestly. No "planning" reporting-as-work.
