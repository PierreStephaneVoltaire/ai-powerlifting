# Discord Channel Orchestration Plan

Read `./.claude/CLAUDE.md` first.

## Objective

Make the Discord webhook/listener flow robust for short bursts of messages in the same channel. A burst may contain:

- a normal social message;
- a new task;
- multiple unrelated tasks that should run in parallel;
- extra context for an already-running task;
- a pivot/stop/cancel instruction for an active task;
- conflicting instructions that require operator clarification;
- multiple intents in the same channel history window.

Responses must not mix. The app must know whether it is currently classifying, responding, or implementing for a channel/task, and Discord sends must be serialized per channel.

## Deployment Reality and Invariants (read before any phase)

- `if-agent-api` currently runs at `replicas = 1` (`terraform/k8s-deployments.tf`, and the test deployment in `terraform/k8s-test.tf`). The plan intentionally prepares for horizontal scaling, so all locks/dedupe must be correct across pods, not only across in-process threads.
- Because horizontal scaling is the goal, cross-pod coordination via DynamoDB conditional writes is a hard requirement, not an optimization. Today the same locks also serialize the in-process concurrency (Discord listener threads, the main asyncio loop, and `ThreadPoolExecutor` paths).
- AWS credentials are already injected into the pod via the host-path `~/.aws` mount (`aws-credentials` volume in `terraform/k8s-deployments.tf`) and consumed through the boto3 default credential chain. There is no IRSA and no per-table IAM policy resource. Adding the new DynamoDB table requires no IAM/IRSA change. Do not add IAM or IRSA work to this plan.
- The per-channel workspace is shared on purpose. There is one workspace directory per channel (`{mount}/{guild_id}/{channel_id}` from `flow/session_dirs.py`). Do not create a workspace per task. Concurrency safety comes from naming the per-run files and per-run OpenCode config/session state inside the shared directory, not from splitting directories.
- `history.md`/`history.json` is one file per channel and is the source of truth for conversation content used by the classifier. New Discord messages (and edits) always update this single per-channel history file. DynamoDB never stores Discord message bodies.

## Existing Code Facts This Plan Must Respect

This is a Python/FastAPI app running in pods, not a TypeScript service.

Current Discord path:

1. `./app/src/channels/listeners/discord_listener.py`
   - `on_message` / `on_message_edit` receive Discord messages.
   - They call `channels.debounce.push_message(conversation_id, message_dict)` from the Discord listener thread/event loop.
   - The dict already includes `message_id`, `guild_id`, `channel_id`, author display name, content, attachments, `channel_ref`, `discord_loop`, timestamps, and edit metadata (`is_edit`, `previous_content`).
   - The live `channel_ref` (discord.TextChannel) and `discord_loop` are Python objects; they cannot be persisted to DynamoDB. When a coordinator wakes from a timer it must resolve a live channel handle from the active Discord client registry (`channels.listeners.discord_listener._active_clients` -> `client.get_channel(channel_id)`).
2. `./app/src/channels/debounce.py`
   - Current debounce is in-memory only: module-level `_buffers`/`_timers` dicts guarded by a `threading.Lock`, with a `loop.call_later` flush timer that resets on every message.
   - It has no DynamoDB dedupe, no max wait, no per-channel classifier lock, no dirty flag.
   - `push_message()` runs on the listener thread; `_schedule_flush()`/`_flush()` run on the main loop via `call_soon_threadsafe`.
3. `./app/src/channels/dispatcher.py`
   - `dispatch_channel_batch()` fetches recent Discord history (`_fetch_discord_history`, limit 100, via `run_coroutine_threadsafe` on `discord_loop`).
   - Translates history + current batch to OpenAI-style messages.
   - Calls `process_chat_completion_internal()` once.
   - Directly chunks and sends the final response to Discord via `deliver_to_channel()`.
4. `./app/src/channels/translators/discord_translator.py`
   - Builds `messages` and `_history_events` for the runtime.
5. `./app/src/api/completions.py`
   - `process_chat_completion_internal()` handles slash commands, pinned specialists, interceptor, cache, and then calls `run_if_flow()`.
6. `./app/src/flow/runner.py`
   - The first OpenCode `planner` run is already the router/classifier.
   - `_planner_prompt()` classifies into `interaction_type`, `specialist`, `thinking_mode`, and `selected_model`, and writes `plan.md`.
   - `run_if_flow()` then executes social/domain/technical routes.
   - `_run_planner()`, `_run_domain()`, `_run_technical()`, and `_synthesize_handoffs()` currently hardcode the filenames `history.md`, `plan.md`, `response.md`, `review.md`, and `.if/status.log`.
   - This plan extends that first planner/router into the batch classifier and parameterizes those filenames per run.
7. `./app/src/flow/opencode.py`
   - `run_opencode()` launches `opencode run --agent ... --model ... --dir <session_dir>` with `cwd=session_dir` and `env=os.environ.copy()`.
   - Session continuation is keyed on a per-agent marker file `.if/opencode-<agent>.session` inside the session dir.
   - There is no subprocess registry and no external cancellation hook today; it only returns after `proc.communicate()` (or kills on timeout).
8. `./app/src/flow/opencode_config.py`
   - `write_opencode_config()` writes a single `opencode.json` at `session_dir/opencode.json` (the project config OpenCode reads from `--dir`).
9. Directives:
   - Existing directive injection already happens through `_directive_block()` in `flow/runner.py`.
   - Specialist directives are injected through `_specialist_prompt()`.
   - Directive storage supports `global_directive` (confirm exact field/read path in `storage/directive_model.py` / `DirectiveStore.get_for_subagent()` before Phase 8).
   - The directive task here is only to ensure global directives are present in the relevant prompt contexts, not to invent a new directive system.
10. DynamoDB/Terraform:

- Existing table definitions live in `./terraform/tables.tf` (all PK/SK, `PAY_PER_REQUEST`, `prevent_destroy`; `if-health` shows the TTL-on-`ttl` pattern to copy).
- Agent API config maps live in `./terraform/k8s-secrets.tf` (live) and `./terraform/k8s-test.tf` (test).
- Use DynamoDB for the execution registry from the first implementation phase that needs persistence/locks.
- don't add comments to the code

## Non-Negotiable Design Rules

- Classification is not per Discord message.
- The existing first OpenCode planner/router is the classifier boundary.
- Classification scope is `channel_id`.
- Only one classifier/router execution may run per Discord channel at a time, enforced with a DynamoDB conditional-write lock so it holds across pods.
- `channel_id` is not a long-running implementation lock.
- A channel may have multiple active implementation tasks.
- Independent tasks may run in parallel inside the one shared per-channel workspace.
- Discord outbound sends must be serialized per channel.
- Planner/domain/technical OpenCode runs must not send directly to Discord in the orchestrated path; they produce app-handled output that is enqueued to the outbox.
- Use DynamoDB conditional writes for dedupe and locks.
- The listener thread must never block on synchronous boto3 calls. All DynamoDB state updates triggered by an incoming Discord event must be scheduled off the listener thread (e.g. onto the main loop via `call_soon_threadsafe`, with boto3 wrapped in `asyncio.to_thread`).
- Every phase below must leave the app in a fully functional state.
- The end state replaces the Discord flow; each phase must define a working Discord path, not a parallel alternate product path.

## Target Runtime Flow

```text
Discord message/create-edit event (listener thread)
  -> schedule lightweight ChannelClassificationState update in DynamoDB off the listener thread
      (pending=true, dirty/debounce/max-wait timestamps, latest observed event metadata)
  -> update the single per-channel history.md/history.json source of truth
  -> no Discord message content is persisted in DynamoDB
  -> one channel coordinator reaches debounce/max-wait deadline
  -> acquire DynamoDB classifier lock for channel (conditional write, cross-pod safe)
  -> resolve live channel handle from active Discord client registry
  -> fetch fresh Discord channel history after the lock is acquired
  -> reconcile fresh history into the per-channel history.md/history.json
  -> derive batch activity from fresh history + stored cursors/timestamps
      (new messages after last cursor + edited messages since last classified time)
  -> run existing OpenCode planner/router as batch classifier (reads history.md)
  -> parse batch decisions
  -> persist ClassificationBatch + IntentRecord items
  -> apply decisions idempotently
      -> enqueue social/clarification/ack responses
      -> create or update ImplementationTask items
      -> start/stop/pivot task workers where safe
  -> task workers run existing planner/domain/technical execution as needed
      -> each run reads history.md and writes its own named plan/response/status files
      -> each run uses its own per-run OpenCode config and session marker
  -> task outputs become DiscordOutboundMessage items
  -> per-channel outbound sender drains queue with DynamoDB lock
  -> if messages arrived while classifying, schedule next debounced classifier pass
```

Important source-of-truth rule:

- Discord channel history is the source of truth for message content. It is reconciled into the single per-channel `history.md`/`history.json`, which the classifier and workers read.
- DynamoDB tracks pending activity, locks, cursors, task state, run records, decisions, and outbound queue items.
- DynamoDB must not store full Discord message content as a parallel history store.
- Edits are handled by marking the channel pending/dirty, refetching updated channel history once the classifier lock is free, and updating the existing per-channel history entries in place.

## Shared Workspace File Naming

The per-channel workspace is shared. Do not create a new workspace per task. Keep one shared per-channel directory and namespace the runtime files by batch/task/run so concurrent runs never read or write the same plan/response/status file.

The single exception is history: `history.md`/`history.json` stay as one shared per-channel file and remain the source of truth. The classifier and every worker read the same `history.md`.

Required file naming pattern:

```text
# Shared, one per channel (source of truth)
history.md
history.json

# Classifier/router batch run
classification.batch.<batch_id>.json
plan.batch.<batch_id>.md
.if/status.classifier.<run_id>.log

# Implementation task run (written directly in the channel workspace root, IDs in the filename)
plan.task.<task_id>.run.<run_id>.md
response.task.<task_id>.run.<run_id>.md
review.task.<task_id>.run.<run_id>.md
.if/status.task.<task_id>.run.<run_id>.log
```

Note: all per-run files live directly in the one shared per-channel workspace directory root, with the task/run IDs encoded in the filename. Do not create per-task subdirectories. OpenCode runs with `--dir <channel_workspace>` so every run shares the same `history.md`.

Prompt rule:

- Every OpenCode prompt must explicitly name the history file to read (`history.md`) and the exact plan, response, review, and status files for that run.
- Do not tell two concurrent OpenCode runs to read/write the same plan, response, review, or status file.
- The classifier writes its plan/decisions to the batch-named files; a task worker writes to its task/run-named files.
- Update helper functions such as `write_history()`, `_run_planner()`, `_run_domain()`, `_run_technical()`, and `_synthesize_handoffs()` to accept explicit file paths/names instead of assuming global filenames. `history.md`/`history.json` remain shared; `plan`/`response`/`review`/`status` become per-run.

## Per-Run OpenCode Config and Session State

Two pieces of OpenCode state currently collide if multiple runs share the workspace. Both are fixed inside the shared directory; do not split the workspace.

1. Project config (`opencode.json`). `write_opencode_config()` currently writes a single `session_dir/opencode.json`, which OpenCode reads from `--dir`. Two concurrent runs needing different scoped MCP tools would clobber each other.

   Fix selection rule:
   - If the run already has a `run_id` (every classifier and task executor run does, since this plan tracks runs via `OpenCodeRunRecord`), use **Option A**: `write_opencode_config()` writes a per-run config file `.if/opencode.run.<run_id>.json` and `run_opencode()` exports `OPENCODE_CONFIG=<that path>` in the subprocess environment. Do not write a root `session_dir/opencode.json` in the orchestrated path, because the project-directory `opencode.json` outranks `OPENCODE_CONFIG` in OpenCode's precedence and would override it.
   - If a run has no `run_id`, use **Option B**: pass the scoped config inline via `OPENCODE_CONFIG_CONTENT`, which sits at the highest non-managed precedence tier and wins even if a root `opencode.json` is present.

   OpenCode config precedence (lowest to highest): remote, global, `OPENCODE_CONFIG` file, project `opencode.json`, `.opencode` dirs, `OPENCODE_CONFIG_CONTENT`. Option A relies on there being no project `opencode.json`; Option B does not.

2. Continue-session marker. `run_opencode()` keys continuation on `.if/opencode-<agent>.session`. Two concurrent runs of the same agent in one channel would share/clobber continue state.

   Fix: namespace the marker per run, e.g. `.if/opencode-<agent>.run.<run_id>.session`, still inside the shared `.if/` directory. `run_opencode()` accepts the per-run marker path. The classifier may keep its existing per-agent marker since only one classifier runs per channel at a time.

`run_opencode()` already does `env = os.environ.copy()`, so setting `OPENCODE_CONFIG` (Option A) or `OPENCODE_CONFIG_CONTENT` (Option B) is an additive env key. It must also accept the explicit config path / inline content, the per-run session-marker path, and (Phase 7) a `run_id` for the cancellable process registry.

## DynamoDB Execution Registry

Add one new single-table DynamoDB registry for channel execution state.

Suggested table name/env:

- Terraform variable: `dynamodb_execution_registry_table`
- Default: `if-agent-execution-registry`
- App env: `IF_EXECUTION_REGISTRY_TABLE_NAME`

Terraform locations:

- Add variable in `./terraform/variables.tf`.
- Add table resource in `./terraform/tables.tf`.
- Add env to live agent API ConfigMap in `./terraform/k8s-secrets.tf`.
- Add env to test agent API ConfigMap in `./terraform/k8s-test.tf`.
- No IAM/IRSA changes are required (host-path credentials already cover DynamoDB).

Table shape:

```hcl
resource "aws_dynamodb_table" "if_execution_registry" {
  name         = var.dynamodb_execution_registry_table
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"

  attribute { name = "pk" type = "S" }
  attribute { name = "sk" type = "S" }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  lifecycle { prevent_destroy = true }

  tags = {
    Project = "if-prototype-a1"
    Service = "agent-execution-registry"
  }
}
```

Use this single-table key layout:

```text
# Channel classifier/debounce state and pending activity signal
pk = CHANNEL#<channel_id>
sk = STATE#classification

# Channel outbound state/lock
pk = CHANNEL#<channel_id>
sk = STATE#outbound

# Classification/router batch metadata
pk = CHANNEL#<channel_id>
sk = BATCH#<batch_id>

# Intent records for a batch
pk = BATCH#<batch_id>
sk = INTENT#<intent_id>

# Implementation task cards
pk = CHANNEL#<channel_id>
sk = TASK#<task_id>

# OpenCode run direct lookup
pk = RUN#<run_id>
sk = META

# Runs by task
pk = TASK#<task_id>
sk = RUN#<run_id>

# Outbound Discord queue
pk = CHANNEL#<channel_id>
sk = OUTBOX#<priority>#<send_after_or_created_at>#<outbound_id>
```

The outbound drainer reads the next item with a `query` on `pk = CHANNEL#<channel_id>` and `begins_with(sk, "OUTBOX#")`, ascending. No GSI is required for single-channel draining; do not add one unless a cross-channel scan need appears.

Do not add `MSG#...` or `MESSAGE#...` registry items for Discord message bodies. The only Discord-message-related data in DynamoDB should be lightweight cursor/event metadata on channel state, batch records, intent source IDs, and task related IDs.

DynamoDB write requirements:

- Use `ConditionExpression` for lock acquire, idempotent intent application, and idempotent outbox enqueue.
- Lock acquire must allow takeover when `lock_expires_at < now`.
- Use `version` or conditional status checks for state transitions.
- Convert all Python floats recursively to `Decimal(str(value))` before `put_item`, `update_item`, or batch writes. This applies to classifier confidence and nested decision payloads. Include a shared recursive float-to-Decimal helper in the new store.

## Data Objects

Use Python dataclasses/Pydantic models in a new module such as:

`./app/src/channels/execution_models.py`

Keep JSON field names stable. Internal Python is snake_case; DynamoDB payload uses snake_case to match Python conventions.

### ChannelClassificationState

```python
@dataclass
class ChannelClassificationState:
    channel_id: str
    status: Literal["idle", "debouncing", "classifying"]
    pending: bool
    dirty: bool
    debounce_until: str | None
    batch_first_event_at: str | None
    max_wait_until: str | None
    latest_observed_event_at: str | None
    latest_observed_message_id: str | None
    latest_observed_edit_at: str | None
    last_classifier_started_at: str | None
    last_classifier_finished_at: str | None
    active_classifier_run_id: str | None
    classifier_lock_owner: str | None
    classifier_lock_expires_at: str | None
    last_classified_message_id: str | None
    last_classified_at: str | None
    pending_event_count: int
    version: int
    updated_at: str
```

Notes:

- `pending=True` means "there is channel activity to classify"; it does not mean messages are stored in DynamoDB.
- `latest_observed_message_id` and timestamps are cursors/hints only.
- On old message edits, `latest_observed_edit_at` and `dirty=True` are enough to force a fresh history fetch and reclassification pass.
- `classifier_lock_owner` is a pod/instance identity (e.g. hostname + uuid) so lock ownership is meaningful once `replicas > 1`.

### ClassificationBatch

This represents one execution of the existing planner/router over freshly fetched Discord history after a debounced pending signal.

```python
@dataclass
class ClassificationBatch:
    batch_id: str
    channel_id: str
    classifier_run_id: str
    started_at: str
    completed_at: str | None
    history_fetched_at: str | None
    history_oldest_message_id: str | None
    history_newest_message_id: str | None
    cursor_before_message_id: str | None
    cursor_after_message_id: str | None
    edited_since: str | None
    candidate_source_message_ids: list[str]
    status: Literal["running", "completed", "failed"]
    batch_summary: str | None
    decisions: list[dict[str, Any]]
    error: str | None
    version: int
    ttl: int | None
```

### ClassifierDecision

The existing planner/router must be extended so its output can represent multiple decisions, not just one route.

```python
@dataclass
class ClassifierDecision:
    intent_id: str
    kind: Literal["social", "task", "implementation_control", "clarification", "ignore"]
    action: Literal[
        "social_response",
        "start_new_task",
        "append_to_active_implementation",
        "pivot_active_implementation",
        "cancel_active_implementation",
        "queue_on_active_implementation",
        "await_instruction_for_active_implementation",
        "ask_clarifying_target",
        "ignore",
    ]
    source_message_ids: list[str]
    target_task_id: str | None
    confidence: float
    reason: str
    needs_planning: bool
    selected_specialist: str | None
    selected_model: str | None
    social_response_text: str | None
    response_text: str | None
    planner_intent: dict[str, Any] | None
    topic_update: dict[str, Any] | None
    conflict: dict[str, Any] | None
```

### IntentRecord

```python
@dataclass
class IntentRecord:
    intent_id: str
    batch_id: str
    channel_id: str
    action: str
    kind: str
    source_message_ids: list[str]
    target_task_id: str | None
    status: Literal["pending", "applying", "running", "completed", "failed", "skipped"]
    created_at: str
    updated_at: str
    error: str | None
    ttl: int | None
```

### ImplementationTask

```python
@dataclass
class ImplementationTask:
    task_id: str
    channel_id: str
    conversation_id: str
    status: Literal[
        "implementing",
        "awaiting_instruction",
        "cancel_requested",
        "pivot_requested",
        "completed",
        "failed",
        "stale",
    ]
    root_discord_message_id: str
    related_discord_message_ids: list[str]
    active_implementer_run_id: str | None
    latest_planner_run_id: str | None
    selected_specialist: str | None
    selected_model: str | None
    topic: dict[str, Any]
    pending_conflict: dict[str, Any] | None
    queued_message_refs: list[dict[str, Any]]
    control: dict[str, Any]
    created_at: str
    updated_at: str
    version: int
    ttl: int | None
```

`queued_message_refs` contains message IDs/timestamps/reasons, not full message content. Workers read the current per-channel `history.md` (reconciled from fresh Discord history) before using those refs.

### OpenCodeRunRecord

```python
@dataclass
class OpenCodeRunRecord:
    run_id: str
    channel_id: str | None
    task_id: str | None
    batch_id: str | None
    kind: Literal["classifier", "planner", "implementer", "social", "domain", "technical", "review", "handoff"]
    agent: str
    model: str
    status: Literal["running", "completed", "failed", "cancel_requested", "cancelled", "timed_out"]
    started_at: str
    completed_at: str | None
    title: str | None
    session_dir: str | None
    config_path: str | None
    session_marker_path: str | None
    history_path: str | None
    plan_path: str | None
    response_path: str | None
    status_path: str | None
    returncode: int | None
    error: str | None
    ttl: int | None
```

`config_path` and `session_marker_path` capture the per-run OpenCode config file and continue-marker introduced in the per-run OpenCode section.

### DiscordOutboundMessage

```python
@dataclass
class DiscordOutboundMessage:
    outbound_id: str
    channel_id: str
    conversation_id: str
    task_id: str | None
    intent_id: str | None
    batch_id: str | None
    type: Literal[
        "social_response",
        "clarifying_question",
        "task_started",
        "task_update",
        "task_completed",
        "task_failed",
        "await_instruction",
        "cancel_confirmation",
    ]
    priority: int
    content: str
    attachments: list[dict[str, Any]]
    reply_to_message_id: str | None
    allowed_mentions: dict[str, Any] | None
    status: Literal["queued", "sending", "sent", "failed"]
    send_after: str | None
    created_at: str
    updated_at: str
    discord_message_id: str | None
    idempotency_key: str
    ttl: int | None
```

## Phase 0 — Foundations and Invariants

Functional outcome: shared models and helpers exist and the documented invariants are encoded, with no behavior change to the live Discord path.

Implementation:

1. Add `app/src/channels/execution_models.py` with all dataclasses above.
2. Add a shared recursive float-to-Decimal helper (reuse the pattern from `ProgramStore._floats_to_decimals` / `tools/health/core.py::_floats_to_decimals`).
3. Add a small instance-identity helper (hostname + uuid) for lock ownership, used later by classifier/outbound locks.
4. Add config in `app/src/config.py`:
   - `IF_EXECUTION_REGISTRY_TABLE_NAME` (default `if-agent-execution-registry`).
   - `CHANNEL_CLASSIFIER_MAX_WAIT_SECONDS` (max wait ceiling; default e.g. 30).
   - Reuse existing `CHANNEL_DEBOUNCE_SECONDS` for the quiet window, or add `CHANNEL_CLASSIFIER_DEBOUNCE_SECONDS` if a distinct value is needed.
5. Do not wire anything into the live path yet.

Definition of done:

- Models and helpers import cleanly.
- Unit tests cover float-to-Decimal conversion of nested decision payloads.
- The existing Discord flow is byte-for-byte unchanged at runtime.

## Phase 1 — DynamoDB Execution Registry and Pending Activity Signal

Functional outcome: Discord channel activity is durably signaled in DynamoDB before classification, without storing message content, the single per-channel `history.md` stays the source of truth, and the existing one-response pipeline still works after fetching fresh channel history.

Implementation:

1. Add the DynamoDB table and env vars:
   - `terraform/variables.tf`
   - `terraform/tables.tf`
   - `terraform/k8s-secrets.tf`
   - `terraform/k8s-test.tf`
   - `app/src/config.py` (done in Phase 0)
2. Add DynamoDB store:
   - `app/src/channels/execution_store.py`
   - Uses DynamoDB conditional writes for all registry state.
   - Uses the shared recursive float-to-Decimal helper.
3. Update `discord_listener.py` message dicts:
   - add `author_id`;
   - add `reply_to_message_id` where available;
   - add `event_type` as `message_create` or `message_edit` (alongside the existing `is_edit`).
4. Update `channels/debounce.py` or introduce `channels/channel_coordinator.py` so incoming Discord events update `CHANNEL#<channel_id>/STATE#classification` only, off the listener thread:
   - schedule the state write onto the main loop (`call_soon_threadsafe`) and run boto3 via `asyncio.to_thread`; the listener thread must not block on DynamoDB;
   - set `pending=True`;
   - set/extend `debounce_until`;
   - set `batch_first_event_at` and `max_wait_until` when opening a new pending window;
   - update `latest_observed_event_at`, `latest_observed_message_id`, `latest_observed_edit_at`, and `pending_event_count`;
   - if state is already `classifying`, set `dirty=True`.
5. For this phase only, after debounce expires and the classifier lock is acquired:
   - resolve a live channel handle from `discord_listener._active_clients` -> `client.get_channel(channel_id)` (and its loop) since `channel_ref`/`discord_loop` are not persisted;
   - fetch fresh Discord channel history using the existing dispatcher history fetch path;
   - reconcile that fresh history into the single per-channel `history.md`/`history.json`;
   - derive the current batch from `last_classified_message_id`/`last_classified_at`;
   - pass those freshly fetched messages to the existing `dispatch_channel_batch()` exactly once;
   - update cursors after the existing pipeline returns.

Definition of done:

- Duplicate delivery does not create duplicate registry message records because no message records are written; repeated events only coalesce into the channel pending state.
- Three rapid messages in the same channel become one pending channel state and one existing pipeline execution after fresh history fetch.
- A message or edit arriving while the batch is being processed marks the channel dirty/pending for the next pass.
- The listener thread is never blocked on a synchronous DynamoDB call.
- Terraform validates and plans for the new DynamoDB table/env changes.
- Existing Discord behavior still produces a response, now through DynamoDB-backed pending activity state and fresh-history reconciliation into the shared `history.md`.

## Phase 2 — Debounce/Classifier Locking and Dirty Reclassification

Functional outcome: one and only one router/classifier execution can run per channel at a time across pods; new message/edit events arriving during classification mark pending/dirty state and trigger a later fresh-history pass.

Implementation:

1. Implement `ChannelClassificationState` transitions in DynamoDB:
   - `idle -> debouncing`
   - `debouncing -> classifying`
   - `classifying -> idle/debouncing`
2. Add quiet-window and max-wait behavior:
   - quiet window: existing `CHANNEL_DEBOUNCE_SECONDS` (or `CHANNEL_CLASSIFIER_DEBOUNCE_SECONDS`);
   - max wait: `CHANNEL_CLASSIFIER_MAX_WAIT_SECONDS`.
   - The coordinator replaces or wraps the current `call_later` reset loop so the quiet window cannot starve a busy channel past the max-wait ceiling.
3. Add classifier lock fields on `STATE#classification`:
   - `classifier_lock_owner` (instance identity)
   - `classifier_lock_expires_at`
   - `active_classifier_run_id`
4. Use DynamoDB conditional update for lock acquisition:
   - acquire if no lock owner or `classifier_lock_expires_at < now`;
   - fail if another pod owns a valid lock.
5. While locked/classifying:
   - new message/edit events update lightweight channel state only and reconcile into `history.md`;
   - state gets `dirty=True` and `pending=True`;
   - no second classifier starts immediately.
6. When the current classifier finishes:
   - release lock;
   - if `dirty=True` or pending messages remain, schedule another debounced pass.

Definition of done:

- Two pods/store instances racing to classify one channel result in one winner via the conditional write.
- New messages during classification do not start a concurrent classifier.
- Dirty pass runs after the first classification finishes.
- Existing single-route response still works.

## Phase 3 — Extend the Existing Planner/Router into Batch Classification

Functional outcome: the first OpenCode planner/router run classifies the full debounced channel batch and can emit multiple intent decisions.

Do not create an unrelated classifier. Extend the existing planner/router path in `flow/runner.py`.

Implementation:

1. Extend `_planner_prompt()` so it explicitly knows when it is classifying a Discord channel batch.
   - It reads the shared `history.md`, plus a derived list of candidate source message IDs, active tasks, pending conflicts, bot recent messages, and directives.
   - It must state: "You are classifying a debounced batch of Discord channel activity. You are not classifying a single message."
2. Extend planner output without breaking single-route parsing.
   - Keep `plan.md`/`IFPlan` single-route parsing intact for the non-batch path.
   - Write batch decisions to a sibling file `classification.batch.<batch_id>.json`, not into `plan.md` front matter.
   - Add a separate `parse_classification()` in `flow/plan.py` rather than overloading `IFPlan`.
   - A classification with exactly one route decision must remain equivalent to today's single-route behavior.
3. Update `flow/plan.py` to parse/validate batch decisions (specialist slugs must be known; `selected_model` must be in `models/model_ids.txt`).
4. Required classifier/router output shape:

```json
{
  "batchSummary": "string",
  "decisions": [
    {
      "intentId": "string",
      "kind": "social|task|implementation_control|clarification|ignore",
      "action": "social_response|start_new_task|append_to_active_implementation|pivot_active_implementation|cancel_active_implementation|queue_on_active_implementation|await_instruction_for_active_implementation|ask_clarifying_target|ignore",
      "sourceMessageIds": ["discord message ids"],
      "targetTaskId": "optional task id",
      "confidence": 0.0,
      "reason": "string",
      "needsPlanning": true,
      "selectedSpecialist": "optional existing specialist slug",
      "selectedModel": "optional model from models/model_ids.txt",
      "socialResponseText": "optional immediate text",
      "responseText": "optional immediate text",
      "plannerIntent": {
        "title": "string",
        "intent": "string",
        "summary": "string",
        "currentGoal": "string",
        "acceptanceCriteria": [],
        "constraints": [],
        "keywords": [],
        "entities": [],
        "likelyFiles": [],
        "nonGoals": []
      },
      "topicUpdate": null,
      "conflict": null
    }
  ]
}
```

5. Prompt rules to add to the existing planner/router prompt:

```markdown
You are classifying a debounced batch of Discord channel activity.
You are not classifying a single message.
Read history.md as the source of truth. Return batch decisions for the new unclassified messages only, using history and active tasks as context.
You may return multiple decisions when the batch contains independent intents.
Group related new messages into the same decision.
Split unrelated conversations into separate decisions.
If several people are brainstorming or disagreeing about one active task, resolve the batch-level intent; do not treat each message as a separate command.
Operator/admin instructions take precedence over conflicting non-operator opinions.
If non-operators conflict and there is no clear operator direction, return await_instruction_for_active_implementation.
Only stop/pivot/wait active implementation tasks, not classifier/router runs.
Social responses do not interrupt active implementations.
If a social/simple question appears alongside a task update, return separate decisions.
If unrelated code tasks appear in the same batch, return multiple start_new_task decisions.
If two decisions would conflict on the same target task, merge them or return await_instruction_for_active_implementation.
```

6. Store `ClassificationBatch` and `IntentRecord` items after parsing.
7. Update channel cursors (`last_classified_message_id`, `last_classified_at`) after successful classification. Do not write per-message registry rows.

Definition of done:

- One batch containing social + code request produces two decisions and two intent records.
- One batch containing two unrelated code tasks produces two `start_new_task` decisions.
- One batch containing conflicting non-operator task direction produces one await-instruction decision.
- Single-intent normal messages still route correctly through the current planner/domain/social/technical machinery.

## Phase 4 — Decision Applier and Task Records

Functional outcome: classifier/router decisions are applied idempotently, and task state is tracked separately from channel classification.

Implementation:

1. Add `app/src/channels/decision_applier.py`.
2. Add idempotent application with conditional updates on `IntentRecord.status` and idempotency keys on outbox enqueue.
3. Implement actions:
   - `social_response`: enqueue a `DiscordOutboundMessage` using `socialResponseText`/`responseText`, or run a social response route if text was not provided.
   - `ask_clarifying_target`: enqueue clarifying question.
   - `ignore`: mark skipped/completed.
   - `start_new_task`: create `ImplementationTask`, enqueue task-started message if desired, and start async task worker.
   - `append_to_active_implementation`: attach message IDs/refs to task and queued context.
   - `queue_on_active_implementation`: queue for later task use.
   - `await_instruction_for_active_implementation`: set task `awaiting_instruction`, store conflict, enqueue conflict summary.
   - `cancel_active_implementation`: set `cancel_requested`, enqueue cancel confirmation.
   - `pivot_active_implementation`: set `pivot_requested`, merge topic update, request worker restart in Phase 6/7.
4. Task creation must not lock the entire channel.
5. All task state writes go to the DynamoDB registry.

Definition of done:

- Decisions can be replayed without duplicate outbox/task creation.
- `start_new_task` creates task records independent of classifier batches.
- Social responses can be enqueued while an implementation task is running.
- Await-instruction creates one visible conflict message and updates the targeted task.

## Phase 4.5 — Correctness Hardening of the Phase 0–4 Base

Review-driven course correction. This phase fixes outright-wrong items found in the
Phase 0–4 implementation. It adds no new product behavior; it only makes the
existing base actually run the batch classifier on the live path, makes the
coordinator and store agree, makes the durable debounce/max-wait ceiling work
across pods, makes intent state machines reach terminal states, and stops the
classifier lock from being held during task execution. Complete this before Phase 5
and Phase 6.

Functional outcome: a normal Discord message no longer crashes the coordinator/store
path, batch classification (not the legacy fallback) runs end to end, the max-wait
ceiling is enforced from durable state, intents reach terminal status idempotently,
and the classifier lock is released before any task route execution begins.

### Findings being corrected

A. Hard runtime bugs:

1. `flow/plan.py` defines `parse_classification_file` three times; the final
   winning definition computes `result` but never returns it, so it returns
   `None`. `batch_classifier.run_batch_classification` then fails on
   `classification.batch_summary`, so batch classification never runs and the
   coordinator silently falls back to the legacy `dispatch_channel_batch()` path.
2. Coordinator↔store signature mismatches raise `TypeError` on the live path:
   - `channel_coordinator` calls
     `store.update_channel_state_on_event(..., debounce_seconds=..., max_wait_seconds=...)`
     but the store method accepts no such kwargs.
   - `store.release_classifier_lock(channel_id, owner, debounce_seconds=...)` is
     called with a kwarg the method does not accept.
   - `store.update_cursors(channel_id, newest_user_id, now)` is called with three
     positional args but the method only accepts two.
3. `batch_first_event_at`, `max_wait_until`, and `debounce_until` are read by the
   coordinator but never written by `_update_state_on_event_sync`, so the durable
   cross-pod max-wait ceiling is dead and starvation protection depends only on
   the in-process `_max_wait_timers`.

B. State-machine / idempotency bug: 4. In `decision_applier`, `apply_decision` transitions `pending→applying`, then
`_apply_start_new_task` transitions `applying→running`, then `apply_decision`
attempts `applying→completed`. The record is already in `running`, so the
conditional fails and `start_new_task` intents stick in `running` forever.

C. Architectural invariant violation: 5. `_process_channel_batch` holds the classifier lock (duration 600s) across the
entire `apply_batch_decisions` → `_apply_start_new_task` → `execute_route`
call, turning the per-channel classifier lock into a long-running
implementation lock. This violates "`channel_id` is not a long-running
implementation lock" and "a channel may have multiple active implementation
tasks run in parallel," and it pre-empts the Phase 5–6 worker/outbox design.

D. Lower severity but fix now: 6. Duplicate `decision_to_ifplan` logic exists in both `flow/runner.py`
(`_decision_to_ifplan`, dead) and `flow/batch_classifier.py` (used). 7. `update_cursors` ignores the timestamp and never stores `last_classified_at`;
`_derive_batch`/`_newest_user_message_id` compare snowflake IDs
lexicographically as strings instead of as integers; edited-message handling
(`edited_since`/`latest_observed_edit_at`) is not wired so edits below the
cursor never re-enter a batch. 8. The `force=True` max-wait path bypasses the "already classifying" guard and can
double-dispatch.

### Implementation

1. `flow/plan.py`: remove the duplicate `parse_classification_file` definitions.
   Keep exactly one that returns a `ClassificationResult` carrying the passed
   `batch_id`. Confirm `run_batch_classification` receives a non-None result.

2. Reconcile coordinator↔store signatures (treat the store as the contract):
   - `update_channel_state_on_event` accepts and uses `debounce_seconds` and
     `max_wait_seconds`, or the coordinator stops passing them.
   - `release_classifier_lock` accepts `debounce_seconds` (used to set
     `debounce_until` on release), or the coordinator stops passing it.
   - `update_cursors` accepts and persists `last_classified_at`, or the coordinator
     stops passing the timestamp. Cursors must persist both
     `last_classified_message_id` and `last_classified_at`.

3. Persist the durable debounce/ceiling fields in `_update_state_on_event_sync`:
   - When opening a new pending window, set `batch_first_event_at` and
     `max_wait_until = batch_first_event_at + CHANNEL_CLASSIFIER_MAX_WAIT_SECONDS`.
     Do not extend `max_wait_until` on later events in the same window.
   - Set/extend `debounce_until = now + CHANNEL_CLASSIFIER_DEBOUNCE_SECONDS` on
     every event.
   - The coordinator's force decision must rely on the persisted `max_wait_until`
     so the ceiling holds across pods, not only via the in-process timer.

4. Fix the intent state machine in `decision_applier`:
   - A handler either owns its full lifecycle (and `apply_decision` must not force
     `applying→completed`), or handlers must not transition status themselves.
   - `start_new_task` intents must reach a terminal state (`completed`/`failed`)
     and never stick in `running`. Re-confirm replay idempotency.

5. Stop holding the classifier lock during task execution:
   - The classifier lock covers only: acquire lock → fetch/reconcile history → run
     batch classifier → persist batch + intents → enqueue social/clarification
     responses and create task records → release lock.
   - Task route execution (`execute_route`) must not run inside the classifier
     lock. For this phase, start it as a detached background task after the lock is
     released (the full async worker + outbox arrives in Phases 5–6). This restores
     the invariant that a channel can reclassify and run multiple tasks without the
     classifier lock blocking them.

6. Snowflake-safe cursors and edit handling:
   - Compare message IDs as integers, not lexicographically, in `_derive_batch` and
     `_newest_user_message_id`.
   - Wire edited-message handling: edits below the cursor that set `dirty` must be
     re-included in the next pass using `edited_since`/`latest_observed_edit_at`.

7. Remove the dead duplicate `_decision_to_ifplan` in `flow/runner.py`; keep one
   shared implementation.

8. Add a re-entrancy guard so a `force=True` max-wait fire cannot dispatch while a
   classifier is already `classifying` for that channel.

### Definition of done

- A normal incoming Discord message raises no `TypeError` in the coordinator or
  store, and batch classification (not the legacy fallback) runs end to end.
- `max_wait_until` is persisted, and a busy channel that keeps resetting the quiet
  window is force-classified at the ceiling, verified via the stored field, not
  only the in-process timer.
- `start_new_task` intents end in a terminal status; replay creates no duplicate
  tasks or outbox items.
- The classifier lock is released before task route execution begins; a second
  classifier pass can run on the same channel while a task is executing.
- Cursor comparison is integer-based; an edit to an older message triggers a fresh
  reclassification pass.
- Unit tests cover: the single corrected `parse_classification_file`,
  store/coordinator signature agreement, durable max-wait persistence, intent
  terminal state, and integer cursor comparison.

## Phase 5 — Per-Channel Outbound Queue

Functional outcome: parallel workers may finish simultaneously, but Discord sends are serialized per channel and chunks do not interleave.

Implementation:

1. Add `app/src/channels/outbound_queue.py`.
2. Store `DiscordOutboundMessage` items under `CHANNEL#<channel_id>/OUTBOX#...`.
3. Add `STATE#outbound` lock with owner/expiry (instance identity), acquired by DynamoDB conditional update with expiry takeover.
4. Drainer behavior:
   - acquire lock;
   - `query` next queued item (`begins_with(sk, "OUTBOX#")`, ascending);
   - mark `sending`;
   - send through existing `channels.delivery.deliver_to_channel()` / Discord send logic (resolving the live channel handle from the active client registry);
   - mark `sent` with `discord_message_id` when available;
   - continue until empty or lock window ends;
   - release lock.
5. Change the orchestrated Discord path so final outputs are enqueued, not directly posted by `dispatcher.py`.
6. Status embeds:
   - existing operational status embeds may remain direct;
   - because tasks run in parallel, status-embed platform context must be re-established per worker (or each status carry its task identity) so a worker does not emit under another task's context;
   - final user-facing responses must go through the queue.

Definition of done:

- Two task workers completing at the same time produce two outbox items.
- Only one sender drains a channel at a time across pods.
- Chunks for one response remain contiguous.
- Failed sends are marked failed and do not block the queue forever.

## Phase 6 — First Fully Parallel Task Execution

Functional outcome: unrelated tasks from one channel batch can run in parallel inside the one shared channel workspace, and their final outputs are queued separately.

Implementation:

1. Add a task worker module, e.g. `app/src/channels/task_worker.py`.
2. Worker receives `ImplementationTask`, source message IDs/refs, selected specialist/model, and planner intent.
3. Before execution, the worker reads the current shared per-channel `history.md` (already reconciled from fresh Discord history by the classifier pass) and resolves source message refs against it.
4. For each task, build a request/plan context scoped to that task, not the entire latest channel burst.
5. Reuse existing execution functions:
   - for route planning, use the existing planner/router logic where needed;
   - for domain/technical/social, reuse the existing `flow.runner` machinery rather than inventing a second agent stack.
6. Make concurrent runs safe in the shared workspace:
   - each OpenCode run is told the exact plan/response/review/status file paths for that run (task/run-named), and reads the shared `history.md`;
   - each run uses a per-run OpenCode config via `OPENCODE_CONFIG=.if/opencode.run.<run_id>.json` (Option A, since task runs have a `run_id`); do not write a root `session_dir/opencode.json` in this path;
   - each run uses a per-run continue marker `.if/opencode-<agent>.run.<run_id>.session`;
   - `write_opencode_config()`, `_run_planner()`, `_run_domain()`, `_run_technical()`, `_synthesize_handoffs()`, and `run_opencode()` accept these explicit paths.
7. Add `run_id` recording around OpenCode calls:
   - `run_opencode()` accepts an optional `run_id` and records lifecycle (`OpenCodeRunRecord`) to DynamoDB, including `config_path` and `session_marker_path`;
   - do not assume unsupported OpenCode CLI flags such as `--title`/`--format json`; run identity is app-side metadata.
8. When a worker completes:
   - update task status;
   - enqueue `task_completed` or `task_failed` outbound message;
   - include attachments generated by existing `FILES:` handling/materialization (resolving artifacts from the task/run-named output files).

Definition of done:

- One batch with two unrelated tasks starts two workers in parallel in the same channel workspace without clobbering each other's plan/response/config/session files.
- Both write task/run records.
- Both final responses are queued and sent serially.
- A social response in the same batch can be sent without waiting for task completion.

## Phase 6.5 — Correctness Hardening of the Phase 5–6 Base

Review-driven course correction. This phase fixes outright-wrong items found in
the Phase 5–6 implementation. It adds no new product behavior; it only makes the
per-run OpenCode config and session marker actually take effect, removes a live-path
regression in `run_if_flow`, fixes the technical review prompt/RETRY loop, and makes
the outbound enqueue genuinely idempotent. Complete this before Phase 7 and Phase 8.

Functional outcome: orchestrated domain/technical runs receive their own scoped MCP
config and their own continue-session marker (so concurrent runs in the shared
workspace neither lose their tools nor clobber each other's session state), the
normal `run_if_flow` path no longer raises `NameError`, the technical RETRY loop
works with parameterized filenames, and replaying a decision or re-running a worker
does not create duplicate outbound messages.

### Findings being corrected

A. Per-run OpenCode config written but never used:

1. `_run_domain`, `_run_technical`, and `_synthesize_handoffs` call
   `write_opencode_config(..., run_id=run_id)`, which (per the Option A rule) writes
   only `.if/opencode.run.<run_id>.json` and intentionally does not write the root
   `session_dir/opencode.json`. But those functions then call `run_opencode()`
   without passing `config_path=`, so `OPENCODE_CONFIG` is never set in the
   subprocess env. The per-run config file is orphaned and the run executes with no
   scoped MCP config at all. The `write_opencode_config()` return value is discarded.

B. Per-run session marker never wired: 2. `run_opencode()` accepts `session_marker_path`, but `_run_domain`,
`_run_technical`, and `_synthesize_handoffs` never construct or pass one, so all
runs still key continuation on the shared `.if/opencode-<agent>.session`. Two
concurrent same-agent runs in one channel clobber each other's continue state,
which is exactly what the per-run marker was meant to prevent.
`_synthesize_handoffs` also does not pass `run_id` to `run_opencode()`.

C. Live-path regression in `run_if_flow`: 3. In `run_if_flow` (the normal, non-orchestrated path), the thinking-mode social
branch passes `run_id`, `response_filename`, and `status_filename` to
`_run_domain`, but those names are not defined in `run_if_flow`'s scope (they only
exist as parameters of `execute_route`). This raises `NameError` whenever that
branch is hit. The per-run-filename arguments belong only in `execute_route`, not
in `run_if_flow`.

D. Technical review prompt / RETRY loop bug: 4. In `_run_technical`, `review_prompt` is a plain (non-f) string but contains
`` `{_review_filename}` ``. The reviewer is told to write a literally-braced
filename instead of the real review file, while RETRY detection reads
`review_path` derived from `_review_filename`. The review file and RETRY check no
longer agree, so the retry path silently breaks.

E. Outbound enqueue idempotency is a no-op: 5. `_enqueue_message` builds `idempotency_key = "<batch>:<intent>:<type>:<outbound_id>"`
and the outbox `sk` also embeds the fresh `outbound_id`. The
`put_outbound_message` conditional write therefore never collides, so the
"idempotent outbox enqueue" requirement is not met. Today most enqueues are
gated by intent state, but Phase 7 pivot/retry re-runs a worker and would emit
duplicate `task_completed`/`task_failed` messages.

### Implementation

1. Make the per-run OpenCode config take effect in the orchestrated path:
   - Capture the path returned by `write_opencode_config(..., run_id=run_id)` in
     `_run_domain`, `_run_technical`, and `_synthesize_handoffs`.
   - Pass that path to `run_opencode()` as `config_path=` so it sets
     `OPENCODE_CONFIG` in the subprocess env.
   - Keep the Option A invariant: when `run_id` is set, do not also write a root
     `session_dir/opencode.json` (it would outrank `OPENCODE_CONFIG`).

2. Wire the per-run continue-session marker:
   - Construct `.if/opencode-<agent>.run.<run_id>.session` in `_run_domain`,
     `_run_technical`, and `_synthesize_handoffs` when `run_id` is set, and pass it as
     `session_marker_path=` to `run_opencode()`.
   - Give `_synthesize_handoffs` a `run_id` (already threaded from `_run_domain`) and
     pass it to `run_opencode()` so its run is recorded and isolated.
   - When `run_id` is absent (legacy single-run path), keep today's shared
     per-agent marker behavior.

3. Remove the live-path regression in `run_if_flow`:
   - Drop `run_id`, `response_filename`, and `status_filename` from the
     thinking-mode social `_run_domain` call inside `run_if_flow`; that path uses the
     default shared filenames. Only `execute_route` (the orchestrated worker path)
     passes per-run filenames.

4. Fix the technical review prompt and RETRY loop:
   - Make `review_prompt` an f-string (or `.format`) so `{_review_filename}` resolves
     to the actual review filename, and confirm RETRY detection reads the same file.

5. Make outbound enqueue idempotent:
   - Build a stable `idempotency_key` that does not include the random
     `outbound_id` (for example `"<batch>:<intent>:<type>"`, and for task lifecycle
     messages `"<task_id>:<type>"`). Base the dedupe condition on this stable key so
     replaying a decision or re-running a worker does not create duplicate outbox
     rows. Keep the float-to-Decimal conversion on the write.

### Definition of done

- An orchestrated domain run receives its scoped MCP config: `OPENCODE_CONFIG`
  points at `.if/opencode.run.<run_id>.json` and no root `opencode.json` is written
  for that run.
- Two concurrent same-agent runs in one channel use distinct per-run session markers
  and do not clobber each other's continue state.
- The normal `run_if_flow` thinking-mode social path runs without `NameError`.
- The technical RETRY loop writes and reads the same review file with parameterized
  filenames; a `RETRY` first line triggers exactly one retry.
- Replaying a decision and re-running a completed worker each produce no duplicate
  outbound messages.
- Unit tests cover: `config_path`/`session_marker_path` plumbing into `run_opencode`,
  the corrected review-prompt filename, and stable outbound idempotency-key dedupe.

## Phase 7 — Cancellation, Pivot, and Await-Instruction Enforcement

Functional outcome: stop/pivot/wait instructions affect active implementation tasks, not classifier/router runs.

Implementation:

1. Add a cancellable executor-process registry and extend `run_opencode()`:
   - maintain an in-process registry keyed by `run_id` holding the live `asyncio.subprocess.Process` handle;
   - record `OpenCodeRunRecord` lifecycle, including `cancel_requested`/`cancelled` statuses;
   - the worker checks task/run control state cooperatively, and a cancel path terminates the subprocess gracefully (`proc.terminate()`), then `proc.kill()` after a grace timeout;
   - only executor/task runs are cancellable; classifier/router runs are never cancelled.
   - Note: with horizontal scaling, the live process handle lives only on the owning pod. The cancel request is recorded in DynamoDB (`cancel_requested`), and the pod that owns `active_implementer_run_id` acts on it. Workers must poll their own run's control state.
2. `cancel_active_implementation`:
   - mark task `cancel_requested`;
   - owning worker stops the active run;
   - mark task completed/cancelled or stale according to final state;
   - enqueue confirmation.
3. `pivot_active_implementation`:
   - cancel current run;
   - merge `topicUpdate` into task topic;
   - start a new worker run (new `run_id`, new per-run files/config/marker) using updated topic and queued context;
   - enqueue pivot acknowledgement/update.
4. `await_instruction_for_active_implementation`:
   - pause/stop current active run if continuing would be unsafe;
   - store conflict and options;
   - task remains `awaiting_instruction` until operator resolves it.
5. Operator resolution:
   - next classifier/router batch targets the existing task;
   - decision updates task and resumes/pivots/cancels according to operator direction.

Definition of done:

- Cancel stops the targeted task run and does not stop channel classification.
- Pivot restarts the targeted task with updated topic and fresh per-run files.
- Await-instruction blocks unsafe continuation and posts one conflict summary.
- Operator follow-up resumes or pivots the same task.

## Phase 7.5 — Correctness Hardening of the Phase 7 Base

Review-driven course correction. Fixes outright-wrong items found in the Phase 7
implementation. No new product behavior; it makes pivot/await restart reliably,
stops internal runtime files from leaking to Discord, makes recurring lifecycle
messages enqueue correctly, and removes a busy-spin/broken test in the outbound
drainer. Complete this before Phase 8.

### Findings being corrected

A. Internal per-run artifacts leak to Discord:

1. `_artifact_refs` filters only the static names in
   `IF_TECHNICAL_ARTIFACT_EXCLUDES` (`response.md`, `plan.md`, `review.md`,
   `status.log`, etc.). The Phase 6 per-run files written in the workspace root
   (`response.task.<task_id>.run.<run_id>.md`, `plan.task.*.md`,
   `review.task.*.md`) do not match, so a task worker attaches its own
   response/plan/review markdown to the user as "generated artifacts."

B. Pivot/await restart is unreachable when no run is live: 2. `_apply_pivot_implementation` only sets `pivot_requested` and calls
`request_cancel`; the real restart happens in the running worker's
`_handle_cancel_outcome`. When `task.active_implementer_run_id` is None
(e.g., the task was `awaiting_instruction` and the prior run already exited),
no worker is running to catch the cancel and restart, so the task is stuck in
`pivot_requested`. Phase 7 DoD ("Pivot restarts the targeted task") is unmet.

C. Idempotency key drops legitimate recurring messages: 3. The stable lifecycle key `{task_id}:{msg_type}` is correct for terminal types
(`task_completed`, `task_failed`, `cancel_confirmation`), but `task_update`
and `await_instruction` recur over a task's life (each pivot/conflict). The
coarse key dedups the 2nd+ occurrence, so later pivot/await updates are
silently dropped from the outbox.

D. Outbound drainer busy-spin and broken tests: 4. `_drain_loop` has no `await` sleep or iteration guard; if `query_outbox` keeps
returning the same `queued` item, it spins as fast as DynamoDB will answer
until the lock window ends. `tests/test_outbound_queue.py` triggers exactly
this with a static `query_outbox` mock that never changes item status and
leaves `_resolve_discord_handle` unpatched, causing a ~120s, multi-GB hang.

E. Lower severity but fix now: 5. `test_task_worker.py` does not insert `app/src` on `sys.path`, so it cannot be
collected on its own (only works when run alongside a test that sets the path). 6. Duplicate `ConditionalCheckFailedException` block in
`_update_outbound_status_sync`. 7. The review and retry `run_opencode` calls in `_run_technical` do not pass
`run_id`/`cancel_event`, so a cancel during review/retry is ignored and those
runs are not registered/recorded. 8. The pivot restart in `_handle_cancel_outcome` passes a stale `from_status`
(`pivot_requested`) to the restarted worker's first task transition, which then
fails silently because the task is already `implementing`.

### Implementation

1. Exclude per-run runtime files from artifact attachment:
   - In `_artifact_refs` (or the worker before enqueue), skip files matching the
     per-run patterns `plan.task.*.run.*.md`, `response.task.*.run.*.md`,
     `review.task.*.run.*.md`, and `status.task.*.run.*.log`, in addition to the
     existing `IF_TECHNICAL_ARTIFACT_EXCLUDES`. Only genuine deliverables should be
     attached.

2. Make pivot/await restart reliable with no live run:
   - When `_apply_pivot_implementation` (or the next classifier batch that resolves
     an awaiting task) requests a pivot and there is no live
     `active_implementer_run_id`, start a fresh task worker directly instead of
     relying on a running worker to catch the cancel. The "running worker restarts
     itself" path stays for the live-run case; add the no-live-run fallback so the
     task cannot stick in `pivot_requested`.

3. Make recurring lifecycle messages enqueueable:
   - Keep `{task_id}:{msg_type}` only for genuinely terminal messages
     (`task_completed`, `task_failed`, `cancel_confirmation`). For recurring types
     (`task_update`, `await_instruction`), include a per-occurrence discriminator
     (e.g., `run_id` or `intent_id`) in the idempotency key so distinct
     pivots/conflicts are not collapsed, while still deduping true replays of the
     same occurrence.

4. Harden the outbound drainer and fix its tests:
   - Add a small `await asyncio.sleep(...)` and/or a max-iterations/no-progress
     guard in `_drain_loop` so it cannot busy-spin if an item fails to advance.
   - Fix `tests/test_outbound_queue.py` so `query_outbox` returns an empty list
     after items are marked sent/failed (or patches `_resolve_discord_handle`), so
     the drain loop terminates promptly instead of running for the full lock window.

5. Lower-severity cleanups:
   - Add the `sys.path` insert to `test_task_worker.py`.
   - Remove the duplicate conditional block in `_update_outbound_status_sync`.
   - Pass `run_id`/`cancel_event` (and per-run config/marker) to the review and
     retry `run_opencode` calls in `_run_technical`, or document that those phases
     are intentionally non-cancellable.
   - Pass the restarted worker its real current status as `from_status` on pivot
     restart.

### Definition of done

- A completed task worker attaches only real deliverables; its own
  `response.task.*`, `plan.task.*`, `review.task.*`, and `status.task.*` files are
  never sent to Discord.
- A pivot or await-resolution on a task with no live run starts a fresh run and the
  task never sticks in `pivot_requested`.
- Two successive `task_update`/`await_instruction` messages for the same task are
  both enqueued; a true replay of one occurrence is still deduped.
- `tests/test_outbound_queue.py` completes in well under a few seconds with no
  multi-GB memory growth, and `_drain_loop` cannot busy-spin.
- Unit tests cover: per-run artifact exclusion, pivot/await restart with no live
  run, recurring-vs-terminal idempotency keys, and bounded outbound drain.

## Phase 8 — Global Directive Inclusion Check

Functional outcome: global directives are guaranteed to be included in classifier/router and worker prompts, while preserving existing directive injection behavior.

Implementation:

1. First confirm the `global_directive` field and read path in `storage/directive_model.py` and `DirectiveStore.get_for_subagent()` / formatting methods.
2. Ensure directives with `global_directive=True` from the operator pk are included for:
   - the first planner/router classifier prompt;
   - domain/technical/social worker prompts as appropriate;
   - specialist prompts that already receive filtered directives.
3. Do not replace the directive system.
4. Do not invent a new multi-user directive store unless the current code lacks a needed read path.
5. If current `get_for_subagent()` excludes global directives accidentally, update that method or add a narrow helper so global directives are merged into existing filtered results.
6. Preserve directive priority/order metadata in formatted output.
7. all prompts text/templates shoiuld be writtent in the app/src/agent/prompts folder

Definition of done:

- A test directive with `global_directive=True` appears in the planner/router classifier prompt.
- It also appears in specialist/domain prompt where applicable.
- Existing type-filtered specialist directives still work.
- all the code involving prompts should never have inline prompt templates. all all prompts text/templates shoiuld be writtent in the app/src/agent/prompts folder

## Phase 8.5 — Correctness Hardening of the Phase 8 Base

Review-driven course correction. The Phase 8 implementation is on the right path:
`get_for_subagent()` now includes `global_directive=True` directives before the
`MAIN_AGENT_ONLY_TYPES` exclusion, all orchestration prompts route directive
injection through `_directive_block`/`get_for_subagent` (so globals reach the
planner, batch classifier, domain, social, technical, and specialist prompts), and
every inline prompt f-string/`join` block in `flow/runner.py`, `flow/batch_classifier.py`,
and `flow/context.py` was faithfully extracted into `app/src/agent/prompts/`
(`.j2`/`.md`) with the `batch_classifier` JSON protected by `{% raw %}`. The Phase 6.5
technical review/RETRY filename fix survived the extraction, all templates render,
and the prior suite plus the new Phase 8 tests pass. This phase only fixes the
items that are wrong or that fail to actually prove the Phase 8 DoD. No new product
behavior. Complete before Phase 9.

### Findings being corrected

A. Global directives are duplicated in the domain prompt:

1. `_domain_prompt` injects both `core_directives` (`_directive_block(["core"])`)
   and `specialist_block`, where `_specialist_prompt` separately renders
   `_directive_block(spec.directive_types)`. Both calls now route through
   `get_for_subagent`, which unconditionally includes every `global_directive`.
   A directive flagged global therefore appears twice in the same domain prompt
   (once in the core block, once in the specialist block). It is not wrong output,
   but it wastes context and can look like a contradiction to the model. The
   classifier/planner/social/technical prompts are unaffected because they only
   inject one directive block.

B. The Phase 8 tests do not prove the Phase 8 DoD:

2. `tests/test_phase8_global_directives.py` is entirely source-text grep
   (`assert 'd.global_directive' in source`, `assert '"planner_prompt"' in content`,
   etc.). The DoD explicitly requires "a test directive with `global_directive=True`
   appears in the planner/router classifier prompt" and "also appears in the
   specialist/domain prompt." Nothing in the current test constructs a global
   directive and renders a prompt, so a future refactor that drops the global
   directive from a real rendered prompt would still pass. The grep tests are
   acceptable as supporting checks but cannot be the proof of this phase.

C. Lower severity, confirm only (do not change behavior unless wrong):

3. `technical_prompt.j2` and `synthesis_prompt.j2` now inject `core_directives`,
   which the original inline strings did not. This is intentional and aligned with
   the Phase 8 goal (directives in worker prompts); keep it. Just confirm the
   technical/synthesis runs still parse and that adding the core block did not break
   any downstream expectation (e.g. RETRY first-line detection, handoff parsing).
4. `runtime_memory_tools.j2` renders `context_id={{ context_id }}` /
   `cache_key={{ cache_key }}` without the `repr()` quotes the original
   `{context_id!r}` produced. Cosmetic; only fix if a downstream consumer parses
   those values.

### Implementation

1. De-duplicate global directives across the two blocks in the domain path:
   - In `_domain_prompt` (or in the specialist directive assembly), ensure a
     directive is not emitted in both the core block and the specialist block.
     Prefer the simplest correct option: render the specialist block with the
     specialist's filtered directives minus those already present in the core
     `["core"]`/global block, or de-duplicate by `(alpha, beta)` before formatting.
   - Keep ordering and priority metadata intact (still sorted by `alpha, beta`).
   - Do not change `get_for_subagent` semantics for the single-block consumers
     (planner, classifier, social, technical); they still get globals exactly once.

### Definition of done

- A directive with `global_directive=True` is rendered exactly once in the
  domain/specialist prompt and still appears in the planner and batch classifier
  prompts.
- Existing type-filtered specialist directives still render; main-agent-only,
  non-global directives stay excluded from the specialist path.
- Technical and synthesis runs still parse correctly with the added core-directive
  block (RETRY detection and handoff parsing unaffected).
- The full existing suite plus the updated Phase 8 tests pass.

## Phase 9 — Tests and Pod Verification

Functional outcome: the deployed test pod proves the flow works under realistic Discord/channel conditions.

Required tests:

1. Three messages arrive quickly in one channel.
   - One classifier/router run starts.
   - Classifier input (via shared history.md) includes all three messages.
2. A message arrives while classifier/router is running.
   - No second classifier starts immediately.
   - Channel is marked dirty.
   - Another debounced pass runs after first finishes.
3. One batch has social + code request.
   - Two decisions.
   - Social outbox item sent separately.
   - Task starts separately.
4. One batch has two unrelated code tasks.
   - Two `start_new_task` decisions.
   - Two workers run in parallel in the same channel workspace with non-colliding per-run files/config/markers.
5. Conflicting non-operator opinions target one active task.
   - One await-instruction decision.
   - Task pauses/stops.
   - One conflict-summary outbox item.
6. Operator resolves conflict.
   - Existing task is resumed/pivoted/cancelled as instructed.
7. Two workers finish together.
   - Two outbox items.
   - One channel sender lock.
   - No interleaved chunks.
8. Duplicate Discord delivery or repeated gateway event.
   - No duplicate message rows are created; repeated events coalesce into the same pending channel state, and fresh history determines the actual batch.
9. Two store clients race on the classifier lock (simulating two pods; runnable today as two concurrent in-process coroutines against the conditional write).
   - One wins.
10. Two store clients race on the outbound lock.

- One drains.

Verification commands/process:

- Unit tests for models, DynamoDB float conversion, conditional lock/idempotency behavior with mocks/stubs, classifier output parsing, decision idempotency, cursor/edit handling, per-run file/config/marker isolation, and outbound ordering.
- Terraform validation only:
  - `terraform fmt`
  - `terraform validate`
  - `terraform plan`
- Test pod verification in `if-portals-test` after building/deploying test images per repo workflow (`scripts/build-test-images.sh`).
- Inspect pod logs for classifier lock, dirty pass, task worker, per-run OpenCode config/session, and outbound queue events.

## Implementation Order Summary

Each phase must be independently functional:

0. Shared models, helpers, config, and invariants in place; no behavior change.
1. DynamoDB registry + pending activity signal + fresh-history reconciled into shared history.md; existing response still works.
2. DynamoDB classifier locks + dirty/max-wait behavior works across pods.
3. Existing planner/router becomes batch classifier and emits decisions to a sibling classification file.
4. Decisions apply idempotently and create task/outbox state.
   4.5. Correctness hardening of the Phase 0–4 base: fix the triple `parse_classification_file`, coordinator↔store signature mismatches, durable debounce/max-wait persistence, intent terminal-state bug, snowflake-safe cursors/edit handling, and release the classifier lock before task execution.
5. Outbound queue serializes Discord sends.
6. Parallel task workers run in the shared channel workspace with per-run files/config/markers and enqueue outputs.
   6.5. Correctness hardening of the Phase 5–6 base: wire the per-run OpenCode config (`config_path`/`OPENCODE_CONFIG`) and per-run session marker into orchestrated runs, remove the `run_if_flow` thinking-mode `NameError` regression, fix the technical review prompt/RETRY filename, and make outbound enqueue idempotency-key dedupe stable.
7. Cancel/pivot/await-instruction control active tasks via the cancellable executor registry.
   7.5. Correctness hardening of the Phase 7 base: exclude per-run runtime files from Discord attachments, make pivot/await restart reliable when no run is live, fix idempotency keys for recurring task_update/await_instruction messages, and harden/repair the outbound drainer busy-spin and its tests.
8. Global directives are guaranteed in prompts using the existing directive system, and all orchestration prompts are externalized to `app/src/agent/prompts/`.
   8.5. Correctness hardening of the Phase 8 base: de-duplicate global directives across the core/specialist blocks in the domain prompt, and replace the source-grep Phase 8 tests with a behavioral test that renders a real global directive into the planner, classifier, and domain prompts.
9. Tests + Terraform validation + deployed pod verification.
