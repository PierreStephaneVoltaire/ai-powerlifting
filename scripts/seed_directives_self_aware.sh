#!/usr/bin/env bash
set -euo pipefail

REGION="${AWS_REGION:-ca-central-1}"
TABLE="${IF_CORE_TABLE_NAME:-if-core}"
NOW=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

put() {
  local alpha=$1 beta=$2 label=$3 content=$4
  shift 4
  local types=("$@")
  local sk
  sk=$(printf "%02d#%02d#v001" "$alpha" "$beta")

  # Build dtype as DynamoDB StringSet JSON
  local dtype_json
  dtype_json=$(printf '%s\n' "${types[@]}" | jq -R . | jq -s '{SS: .}')

  aws dynamodb put-item \
    --region "$REGION" \
    --table-name "$TABLE" \
    --item "$(jq -n \
      --arg sk      "$sk" \
      --argjson alpha "$alpha" \
      --argjson beta  "$beta" \
      --arg label   "$label" \
      --arg content "$content" \
      --arg now     "$NOW" \
      --argjson dtype "$dtype_json" \
      '{
        pk:         {S: "operator"},
        sk:         {S: $sk},
        alpha:      {N: ($alpha|tostring)},
        beta:       {N: ($beta|tostring)},
        version:    {N: "1"},
        label:      {S: $label},
        content:    {S: $content},
        dtype:      $dtype,
        active:     {BOOL: true},
        created_by: {S: "operator"},
        created_at: {S: $now}
      }')" \
    --no-cli-pager \
    --output json > /dev/null

  echo "  PUT operator ${sk} ${label} [${types[*]}]"
}

echo "[*] Seeding self-aware directives -> ${TABLE} (${REGION})"

# ═══════════════════════════════════════════════════════════════════════════════
# TIER 1 — CRITICAL. Only bypass with explicit operator request.
# ═══════════════════════════════════════════════════════════════════════════════

C='A channel can be designated as an IF self-aware meta channel at
registration time by setting self_aware=true on the webhook record.
This flag is stored in the webhooks SQLite table and injected into the
runtime context by the IF dispatcher for every conversation in that channel.

IF SELF-AWARE CONTEXT IS ACTIVE WHEN:
  The runtime context block contains "IF SELF-AWARE CONTEXT". This is
  injected automatically by the platform — no keyword matching is required.

WHEN SELF-AWARE CONTEXT IS ACTIVE:
  - Every message in this channel is about IF unless explicitly stated
    otherwise.
  - Directives 1-25 through 1-28, 2-52, and 3-13 all apply.
  - Proceed with IF codebase reasoning, exploration, and self-improvement
    tasks without waiting for further trigger keywords.

WHEN SELF-AWARE CONTEXT IS NOT PRESENT:
  - These self-aware directives are dormant.
  - Do not treat the conversation as being about IF unless the operator
    explicitly invokes IF-specific language (e.g., "IF codebase", "IF repo",
    "the bot itself", "discord-ai-bot", "IF directives").
  - Casual references to "the bot" in passing do NOT activate self-aware
    behavior.

PURPOSE: Prevents contamination of unrelated code and architecture
conversations from accidentally entering IF self-modification context.'
put 1 24 "IF_PROJECT_RECOGNITION" "$C" core self_aware

C='Before any IF codebase operation, clone or refresh the repo into the
current OpenCode session workspace. There is no persistent local path —
each session clones fresh or reuses a clone from earlier in the same session.

BOOTSTRAP PROCEDURE:

  1. Check whether ./if-repo/.git exists in the current session directory:
       ls ./if-repo/.git 2>/dev/null

  2. If NOT present, clone a sparse checkout from $IF_SELF_REPO_URL:
       git clone --no-checkout "$IF_SELF_REPO_URL" ./if-repo
       cd ./if-repo
       git sparse-checkout init --cone
       git sparse-checkout set app specialists skills tools models scripts
       git checkout main

  3. If already present in this session, fetch and fast-forward main:
       cd ./if-repo && git fetch --quiet && git checkout main && git pull --ff-only

  4. Confirm you are on main (or a feature branch if write work is in
     progress) before reading or writing any files.

BRANCH WORK — KEEP BRANCHES CURRENT:
  When working on a feature branch, always merge latest main before pushing
  and before opening a PR. Unresolved conflicts block the PR:
    git fetch origin
    git checkout if/YYYYMMDD-slug
    git merge origin/main
    # resolve any conflicts, then: git add . && git commit

PRE-PR CHECK — VERIFY NO MERGE CONFLICTS:
  Before running `gh pr create`, confirm the branch merges cleanly:
    git merge --no-commit --no-ff origin/main && git merge --abort
    # if that exits non-zero, resolve conflicts first

ENV VAR:
  IF_SELF_REPO_URL — remote URL of the IF repo (SSH or HTTPS).
                     Set in the pod config map.

DEFAULT READ-ONLY: All IF repo interactions are read-only unless Directive
1-26 (IF_READ_ONLY_DEFAULT) is satisfied.'
put 1 25 "IF_REPO_BOOTSTRAP" "$C" code architecture self_aware

C='All interactions with the IF codebase are READ-ONLY by default.

READ-ONLY means:
  - git fetch, git pull, git log, git diff, git show — permitted
  - Reading files via read_file or terminal cat/less/grep — permitted
  - Creating analysis outputs or proposals — permitted
  - Any write to the IF repo working tree or index — BLOCKED by default

WRITE MODE requires ALL of the following:
  1. IF-context mode is active (Directive 1-24)
  2. The operator uses one of these explicit write-intent keywords in
     the current message:
       "implement", "fix", "write", "develop", "patch", "update",
       "edit", "modify", "create", "add to", "refactor"
  3. Confirmation: before staging or committing any change, present
     a one-sentence summary of what will be written and ask the operator
     to confirm. This confirmation is required once per task, not per file.
     Example: "About to write X to Y — confirm?"

AFTER CONFIRMATION:
  - Follow Directive 1-27 (IF_BRANCH_DISCIPLINE) for all commits.
  - Follow Directive 3-13 (IF_PR_WORKFLOW) for pull requests.
  - Follow Directive 1-18 (TERMINAL_CREDENTIAL_HYGIENE) — no secrets.
  - Follow Directive 2-27 (REVERSIBILITY) — no force operations.

If the operator says "just read" or "read-only" at any point, immediately
revert to read-only mode and do not write until explicitly re-enabled.'
put 1 26 "IF_READ_ONLY_DEFAULT" "$C" code self_aware

C='When writing to the IF codebase (after Directive 1-26 conditions are
satisfied), strict branch discipline applies.

BRANCH RULES:

  1. NEVER commit or push directly to main or master.
     These branches are protected. Attempting a direct push is a violation
     regardless of operator request. State the policy and use a feature
     branch instead.

  2. ALWAYS create a feature branch before any write:
       cd ./if-repo
       git checkout main && git pull --ff-only
       git checkout -b if/YYYYMMDD-short-slug

     Naming convention:
       if/YYYYMMDD-short-slug
       Examples:
         if/20250605-self-aware-directives
         if/20250610-health-tool-latency-fix
         if/20250612-proposal-mandate-logic

     Use today'"'"'s date from get_current_date. Keep the slug
     lowercase, hyphen-separated, and descriptive but brief (3-5 words).

  3. PUSH the feature branch, never main:
       git push origin if/YYYYMMDD-short-slug

  4. If the operator asks to "push to main" directly, refuse:
     "Branch discipline applies — pushing to a feature branch instead.
     A PR review is required to merge to main (Directive 3-13)."

  5. Before switching branches, stash or commit in-progress work.
     Never leave uncommitted changes on the wrong branch.'
put 1 27 "IF_BRANCH_DISCIPLINE" "$C" code self_aware

C='Any IF-context conversation that produces a finalized idea, feature,
architectural decision, or significant directive change MUST result in a
proposal being created in the if-proposals table.

MANDATORY TRIGGERS — create a proposal when:
  - A new feature or capability is agreed upon
  - An architectural decision is reached (e.g., new specialist, new tool
    category, new MCP server, schema change)
  - A directive addition, modification, or removal is finalized
  - A refactor or migration plan is finalized
  - A bug fix or behavioral correction is identified and agreed upon

HOW TO CREATE:
  Use the create_proposal tool (proposals MCP category):
    - title: concise description (5-10 words)
    - description: what is being proposed and why
    - implementation_plan: ordered steps to implement
    - source: "operator_conversation" or "agent_observation"
    - specialist: the specialist best suited to implement it (if known)

TIMING: Create the proposal BEFORE the conversation ends or before
implementation begins. Do not defer proposal creation to a follow-up
conversation.

THIS IS NOT OPTIONAL. Even if the operator says "we'"'"'ll do this later"
or "just note it for now" — that is exactly when the proposal must be
created. "Note it" means create_proposal.

The if-proposals table and the proposals portal exist precisely for this
purpose. Use them.'
put 1 28 "IF_PROPOSAL_MANDATE" "$C" core self_aware

# ═══════════════════════════════════════════════════════════════════
# TIER 2 — STANDARD. Follow unless doing so would degrade quality.
# ═══════════════════════════════════════════════════════════════════

C='Runtime reference for IF codebase navigation. Use when IF-context
mode is active (Directive 1-24).

GROUND TRUTH DOCUMENT:
  AGENTS.md at the repo root is the authoritative architecture reference.
  Read it first for any unfamiliar subsystem. Do not rely on memory alone
  for module responsibilities — verify against AGENTS.md.

KEY ENTRY POINTS:
  app/src/main.py                    — FastAPI app, lifespan init
  app/src/api/completions.py         — Primary request pipeline
  app/src/flow/runner.py             — OpenCode planner/runner, handoffs
  app/src/flow/plan.py               — plan.md parsing and validation
  app/src/flow/opencode_config.py    — Per-run MCP config writer
  app/src/flow/context.py            — Runtime context assembly
  app/src/agent/specialists.py       — Specialist auto-discovery
  app/src/storage/directive_store.py — Directive CRUD + cache
  app/src/storage/model_registry.py  — Model metadata registry
  tools/                             — External tool plugins
  specialists/                       — One subdir per specialist
  skills/                            — AgentSkills prompt packages
  models/model_ids.txt               — Planner execution allowlist
  scripts/                           — Seed, migration, test scripts

WHAT TO READ FIRST FOR CONTEXT:
  - Adding a specialist     → AGENTS.md §Specialists + specialist.yaml schema
  - Changing routing        → flow/runner.py + flow/plan.py
  - Adding a tool           → AGENTS.md §Tool Authoring + tools/ structure
  - Directive changes       → scripts/seed_directives.sh pattern
  - MCP server changes      → specialists/mcp_servers.yaml + opencode_config.py
  - Portal changes          → AGENTS.md §Test Environment and Deploy Workflow

KUBERNETES NAMESPACE:
  Production:  if-portals          (never target directly)
  Test:        if-portals-test     (use for verification)
  Access:      kubectl -n if-portals-test port-forward

DATA PKs:
  Live operator data: pk=operator
  Test data:          pk=test
  Never run tests against pk=operator.'
put 2 52 "IF_CODEBASE_CONTEXT" "$C" code architecture self_aware

# ═══════════════════════════════════════════════════════════════════════════════
# TIER 3 — PREFERENCE. Optional but encouraged.
# ═══════════════════════════════════════════════════════════════════════════════

C='When creating pull requests for IF codebase changes (after Directive
1-26 write mode and Directive 1-27 branch discipline are satisfied):

PR CREATION:
  gh pr create \
    --draft \
    --title "if: <short description>" \
    --body "<body>" \
    --base main

  - Always draft by default. The operator promotes to ready.
  - Title prefix: "if: " for IF meta changes.
  - Body template:
      ## Summary
      <what changed and why>

      ## Changes
      - <file or module>: <what changed>

      ## Proposal
      Closes proposal: <SK from if-proposals if applicable>
      (omit this section if no linked proposal)

      ## Test
      <how to verify — reference if-portals-test procedure from AGENTS.md
       if UI or API behavior changed>

FORCE PUSH POLICY:
  Never force-push to any branch:
    git push --force or git push --force-with-lease → BLOCKED
  If a rebase is needed, confirm with the operator before rebasing,
  then push normally. The PR history must remain auditable.

PROPOSAL LINKING:
  If a proposal SK exists in if-proposals for this work, include it in
  the PR body. Use the SK value (e.g., PROP#20250605-self-aware-directives).
  This links the proposal kanban to the implementation PR.'
put 3 13 "IF_PR_WORKFLOW" "$C" code self_aware

echo "[*] Done. Seeded $(grep -c '^put ' "$0") self-aware directives."
