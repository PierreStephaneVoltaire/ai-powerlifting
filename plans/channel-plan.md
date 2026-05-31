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

## Existing Code Facts This Plan Must Respect

This is a Python/FastAPI app running in pods, not a TypeScript service.

Current Discord path:

1. `./app/src/channels/listeners/discord_listener.py`
   - `on_message` / `on_message_edit` receive Discord messages.
   - They call `channels.debounce.push_message(conversation_id, message_dict)`.
   - The dict already includes `message_id`, `guild_id`, `channel_id`, author display name, content, attachments, `channel_ref`, `discord_loop`, timestamps, and edit metadata.
2. `./app/src/channels/debounce.py`
   - Current debounce is in-memory only.
   - It buffers by `conversation_id` and flushes after `CHANNEL_DEBOUNCE_SECONDS`.
   - It has no DynamoDB dedupe, no max wait, no per-channel classifier lock, no dirty flag.
3. `./app/src/channels/dispatcher.py`
   - Fetches recent Discord history.
   - Translates history + current batch to OpenAI-style messages.
   - Calls `process_chat_completion_internal()` once.
   - Directly chunks and sends the final response to Discord.
4. `./app/src/channels/translators/discord_translator.py`
   - Builds `messages` and `_history_events` for the runtime.
5. `./app/src/api/completions.py`
   - `process_chat_completion_internal()` handles slash commands, pinned specialists, interceptor, cache, and then calls `run_if_flow()`.
6. `./app/src/flow/runner.py`
   - The first OpenCode `planner` run is already the router/classifier.
   - `_planner_prompt()` classifies into `interaction_type`, `specialist`, `thinking_mode`, and `selected_model`, and writes `plan.md`.
   - `run_if_flow()` then executes social/domain/technical routes.
   - This plan extends that first planner/router into the batch classifier.
7. Directives:
   - Existing directive injection already happens through `_directive_block()` in `flow/runner.py`.
   - Specialist directives are injected through `_specialist_prompt()`.
   - Directive storage already supports `global_directive` in `storage/directive_model.py`.
   - The directive task here is only to ensure global directives are present in the relevant prompt contexts, not to invent a new directive system.
8. DynamoDB/Terraform:
   - Existing table definitions live in `./terraform/tables.tf`.
   - Agent API config maps live in `./terraform/k8s-secrets.tf` and `./terraform/k8s-test.tf`.
   - Use DynamoDB for the execution registry from the first implementation phase that needs persistence/locks.

## Non-Negotiable Design Rules

- Classification is not per Discord message.
- The existing first OpenCode planner/router is the classifier boundary.
- Classification scope is `channel_id`.
- Only one classifier/router execution may run per Discord channel at a time.
- `channel_id` is not a long-running implementation lock.
- A channel may have multiple active implementation tasks.
- Independent tasks may run in parallel.
- Discord outbound sends must be serialized per channel.
- Planner/domain/technical OpenCode runs must not send directly to Discord in the orchestrated path; they produce app-handled output that is enqueued to the outbox.
- Use DynamoDB conditional writes for dedupe and locks.
- Every phase below must leave the app in a fully functional state.
- The end state replaces the Discord flow; each phase must define a working Discord path, not a parallel alternate product path.

## Target Runtime Flow

```text
Discord message/create-edit event
  -> update lightweight ChannelClassificationState in DynamoDB
      (pending=true, dirty/debounce/max-wait timestamps, latest observed event metadata)
  -> no Discord message content is persisted in DynamoDB
  -> one channel coordinator reaches debounce/max-wait deadline
  -> acquire DynamoDB classifier lock for channel
  -> fetch fresh Discord channel history after the lock is acquired
  -> derive batch activity from fresh history + stored cursors/timestamps
      (new messages after last cursor + edited messages since last classified time)
  -> run existing OpenCode planner/router as batch classifier
  -> parse batch decisions
  -> persist ClassificationBatch + IntentRecord items
  -> apply decisions idempotently
      -> enqueue social/clarification/ack responses
      -> create or update ImplementationTask items
      -> start/stop/pivot task workers where safe
  -> task workers run existing planner/domain/technical execution as needed
  -> task outputs become DiscordOutboundMessage items
  -> per-channel outbound sender drains queue with DynamoDB lock
  -> if messages arrived while classifying, schedule next debounced classifier pass
```

Important source-of-truth rule:

- Discord channel history is the source of truth for message content.
- DynamoDB tracks pending activity, locks, cursors, task state, run records, decisions, and outbound queue items.
- DynamoDB must not store full Discord message content as a parallel history store.
- Edits are handled by marking the channel pending/dirty and then refetching updated channel history once the classifier lock is free.

## Shared Workspace File Naming

Current `flow/history.py` and `flow/runner.py` use fixed names such as `history.md`, `history.json`, `plan.md`, `response.md`, `review.md`, and `.if/status.log` in the channel workspace. That is unsafe once one channel can have parallel tasks.

Do not create a new workspace per task unless later profiling proves file namespace isolation is easier than shared-workspace isolation. Prefer the existing per-channel workspace, but namespace runtime files by batch/task/run.

Required file naming pattern:

```text
# Classifier/router batch run
history.batch.<batch_id>.md
history.batch.<batch_id>.json
classification.batch.<batch_id>.json
plan.batch.<batch_id>.md
.if/status.classifier.<run_id>.log

# Implementation task run
tasks/<task_id>/history.task.<task_id>.run.<run_id>.md
tasks/<task_id>/history.task.<task_id>.run.<run_id>.json
tasks/<task_id>/plan.task.<task_id>.run.<run_id>.md
tasks/<task_id>/response.task.<task_id>.run.<run_id>.md
tasks/<task_id>/review.task.<task_id>.run.<run_id>.md
tasks/<task_id>/status.task.<task_id>.run.<run_id>.log
```

Prompt rule:

- Every OpenCode prompt must explicitly name the history, plan, response, review, and status files for that run.
- Do not tell two concurrent OpenCode runs to read/write the same `plan.md`, `history.md`, `response.md`, or `.if/status.log`.
- Update helper functions such as `write_history()`, `_run_planner()`, `_run_domain()`, and `_run_technical()` to accept explicit file paths/names instead of assuming global filenames.

## DynamoDB Execution Registry

Add one new single-table DynamoDB registry for channel execution state.

Suggested table name/env:

- Terraform variable: `dynamodb_execution_registry_table`
- Default: `if-agent-execution-registry`
- App env: `IF_EXECUTION_REGISTRY_TABLE_NAME`

Terraform locations:

- Add variable in `/home/sirsimpalot/Downloads/discord-ai-bot/terraform/variables.tf`.
- Add table resource in `/home/sirsimpalot/Downloads/discord-ai-bot/terraform/tables.tf`.
- Add env to live agent API ConfigMap in `/home/sirsimpalot/Downloads/discord-ai-bot/terraform/k8s-secrets.tf`.
- Add env to test agent API ConfigMap in `/home/sirsimpalot/Downloads/discord-ai-bot/terraform/k8s-test.tf`.

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

Do not add `MSG#...` or `MESSAGE#...` registry items for Discord message bodies. The only Discord-message-related data in DynamoDB should be lightweight cursor/event metadata on channel state, batch records, intent source IDs, and task related IDs.

DynamoDB write requirements:

- Use `ConditionExpression` for lock acquire, idempotent intent application, and idempotent outbox enqueue.
- Lock acquire must allow takeover when `lock_expires_at < now`.
- Use `version` or conditional status checks for state transitions.
- Convert all Python floats recursively to `Decimal(str(value))` before `put_item`, `update_item`, or batch writes. This applies to classifier confidence and nested decision payloads.

## Data Objects

Use Python dataclasses/Pydantic models in a new module such as:

`/home/sirsimpalot/Downloads/discord-ai-bot/app/src/channels/execution_models.py`

Keep JSON field names stable. Internal Python can be snake_case; DynamoDB payload can use snake_case to match Python conventions.

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

- `pending=True` means “there is channel activity to classify”; it does not mean messages are stored in DynamoDB.
- `latest_observed_message_id` and timestamps are cursors/hints only.
- On old message edits, `latest_observed_edit_at` and `dirty=True` are enough to force a fresh history fetch and reclassification pass.

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

`queued_message_refs` contains message IDs/timestamps/reasons, not full message content. Workers fetch current Discord history before using those refs.

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
    history_path: str | None
    plan_path: str | None
    response_path: str | None
    status_path: str | None
    returncode: int | None
    error: str | None
    ttl: int | None
```

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

## Phase 1 — DynamoDB Execution Registry and Pending Activity Signal

Functional outcome: Discord channel activity is durably signaled in DynamoDB before classification, without storing message content, and the existing one-response pipeline still works after fetching fresh channel history.

Implementation:

1. Add the DynamoDB table and env vars:
   - `terraform/variables.tf`
   - `terraform/tables.tf`
   - `terraform/k8s-secrets.tf`
   - `terraform/k8s-test.tf`
   - `app/src/config.py`
2. Add execution models:
   - `app/src/channels/execution_models.py`
3. Add DynamoDB store:
   - `app/src/channels/execution_store.py`
   - This store uses DynamoDB conditional writes for all registry state.
   - Include a shared recursive float-to-Decimal helper.
4. Update `discord_listener.py` message dicts:
   - add `author_id`;
   - add `reply_to_message_id` where available;
   - add `event_type` as `message_create` or `message_edit`.
5. Update `channels/debounce.py` or introduce `channels/channel_coordinator.py` so incoming Discord events update `CHANNEL#<channel_id>/STATE#classification` only:
   - set `pending=True`;
   - set/extend `debounce_until`;
   - set `batch_first_event_at` and `max_wait_until` when opening a new pending window;
   - update `latest_observed_event_at`, `latest_observed_message_id`, `latest_observed_edit_at`, and `pending_event_count`;
   - if state is already `classifying`, set `dirty=True`.
6. For this phase only, after debounce expires and the classifier lock is acquired, fetch fresh Discord channel history using the existing dispatcher history fetch path, derive the current batch from `last_classified_message_id`/`last_classified_at`, and pass those freshly fetched messages to existing `dispatch_channel_batch()` exactly once. Update cursors after the existing pipeline returns.

Definition of done:

- Duplicate delivery does not create duplicate registry message records because no message records are written; repeated events only coalesce into the channel pending state.
- Three rapid messages in the same channel become one pending channel state and one existing pipeline execution after fresh history fetch.
- A message or edit arriving while the batch is being processed marks the channel dirty/pending for the next pass.
- Terraform validates and plans for the new DynamoDB table/env changes.
- Existing Discord behavior still produces a response, but now through DynamoDB-backed pending activity state and fresh history fetch.

## Phase 2 — Debounce/Classifier Locking and Dirty Reclassification

Functional outcome: one and only one router/classifier execution can run per channel at a time across pods; new message/edit events arriving during classification mark pending/dirty state and trigger a later fresh-history pass.

Implementation:

1. Implement `ChannelClassificationState` transitions in DynamoDB:
   - `idle -> debouncing`
   - `debouncing -> classifying`
   - `classifying -> idle/debouncing`
2. Add quiet-window and max-wait behavior:
   - quiet window: use existing `CHANNEL_DEBOUNCE_SECONDS` or add more specific `CHANNEL_CLASSIFIER_DEBOUNCE_SECONDS` if needed;
   - max wait: add `CHANNEL_CLASSIFIER_MAX_WAIT_SECONDS`.
3. Add classifier lock fields on `STATE#classification`:
   - `classifier_lock_owner`
   - `classifier_lock_expires_at`
   - `active_classifier_run_id`
4. Use DynamoDB conditional update for lock acquisition:
   - acquire if no lock owner or lock expired;
   - fail if another pod owns a valid lock.
5. While locked/classifying:
   - new message/edit events update lightweight channel state only;
   - state gets `dirty=True` and `pending=True`;
   - no second classifier starts immediately.
6. When the current classifier finishes:
   - release lock;
   - if `dirty=True` or pending messages remain, schedule another debounced pass.

Definition of done:

- Two pods/store instances racing to classify one channel result in one winner.
- New messages during classification do not start a concurrent classifier.
- Dirty pass runs after the first classification finishes.
- Existing single-route response still works.

## Phase 3 — Extend the Existing Planner/Router into Batch Classification

Functional outcome: the first OpenCode planner/router run classifies the full debounced channel batch and can emit multiple intent decisions.

Do not create an unrelated classifier. Extend the existing planner/router path in `flow/runner.py`.

Implementation:

1. Extend `_planner_prompt()` so it explicitly knows when it is classifying a Discord channel batch.
   - It must receive freshly fetched relevant channel history, a derived list of candidate source message IDs, active tasks, pending conflicts, bot recent messages, and directives.
   - It must state: “You are classifying a debounced batch of Discord channel activity. You are not classifying a single message.”
2. Extend planner output format.
   - Current `plan.md` YAML supports one route.
   - Add a batch mode that can write a JSON/YAML decisions array either in `plan.md` front matter or a sibling file such as `classification.json`.
   - Keep existing single-route parsing valid only if the decisions array contains one route decision.
3. Update `./app/src/flow/plan.py` to parse/validate batch decisions.
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
Return batch decisions for the new unclassified messages only, using history and active tasks as context.
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
7. Update channel cursors (`last_classified_message_id`, `last_classified_at`) after successful classification. Do not mark per-message registry rows because message content/rows are not stored.

Definition of done:

- One batch containing social + code request produces two decisions and two intent records.
- One batch containing two unrelated code tasks produces two `start_new_task` decisions.
- One batch containing conflicting non-operator task direction produces one await-instruction decision.
- Single-intent normal messages still route correctly through the current planner/domain/social/technical machinery.

## Phase 4 — Decision Applier and Task Records

Functional outcome: classifier/router decisions are applied idempotently, and task state is tracked separately from channel classification.

Implementation:

1. Add `app/src/channels/decision_applier.py`.
2. Add idempotent application with conditional updates on `IntentRecord.status`.
3. Implement actions:
   - `social_response`: enqueue a `DiscordOutboundMessage` using `socialResponseText`/`responseText`, or run a social response route if text was not provided.
   - `ask_clarifying_target`: enqueue clarifying question.
   - `ignore`: mark skipped/completed.
   - `start_new_task`: create `ImplementationTask`, enqueue task-started message if desired, and start async task worker.
   - `append_to_active_implementation`: attach message IDs/content to task and queued context.
   - `queue_on_active_implementation`: queue for later task use.
   - `await_instruction_for_active_implementation`: set task `awaiting_instruction`, store conflict, enqueue conflict summary.
   - `cancel_active_implementation`: set `cancel_requested`, enqueue cancel confirmation.
   - `pivot_active_implementation`: set `pivot_requested`, merge topic update, request worker restart in Phase 6.
4. Task creation must not lock the entire channel.
5. All task state writes go to DynamoDB registry.

Definition of done:

- Decisions can be replayed without duplicate outbox/task creation.
- `start_new_task` creates task records independent of classifier batches.
- Social responses can be enqueued while an implementation task is running.
- Await-instruction creates one visible conflict message and updates the targeted task.

## Phase 5 — Per-Channel Outbound Queue

Functional outcome: parallel workers may finish simultaneously, but Discord sends are serialized per channel and chunks do not interleave.

Implementation:

1. Add `app/src/channels/outbound_queue.py`.
2. Store `DiscordOutboundMessage` items under `CHANNEL#<channel_id>/OUTBOX#...`.
3. Add `STATE#outbound` lock with owner/expiry.
4. Use DynamoDB conditional update to acquire outbound lock.
5. Drainer behavior:
   - acquire lock;
   - lease next queued item;
   - mark `sending`;
   - send through existing low-level `channels.delivery.deliver_to_channel()` / Discord send logic;
   - mark `sent` with `discord_message_id` when available;
   - continue until empty or lock window ends;
   - release lock.
6. Change orchestrated Discord path so final outputs are enqueued, not directly posted by `dispatcher.py`.
7. Decide how status embeds interact:
   - existing status embeds may remain direct operational messages;
   - final user-facing responses must go through the queue.

Definition of done:

- Two task workers completing at the same time produce two outbox items.
- Only one sender drains a channel at a time across pods.
- Chunks for one response remain contiguous.
- Failed sends are marked failed and do not block the queue forever.

## Phase 6 — First Fully Parallel Task Execution

Functional outcome: unrelated tasks from one channel batch can run in parallel, and their final outputs are queued separately.

Implementation:

1. Add a task worker module, e.g. `app/src/channels/task_worker.py`.
2. Worker receives `ImplementationTask`, source message IDs/refs, selected specialist/model, and planner intent.
3. Before execution, worker fetches fresh Discord channel history and resolves source message refs to current message content.
4. For each task, build a request/plan context scoped to that task, not the entire latest channel burst.
5. Reuse existing execution functions:
   - for route planning, use the existing planner/router logic where needed;
   - for domain/technical/social, reuse the existing `flow.runner` machinery rather than inventing a second agent stack.
6. Add `run_id` recording around OpenCode calls:
   - update `run_opencode()` to accept optional `run_id` and record lifecycle to DynamoDB;
   - do not assume unsupported OpenCode CLI flags such as `--title`/`--format json` unless verified. Run identity can be app-side metadata.
7. When worker completes:
   - update task status;
   - enqueue `task_completed` or `task_failed` outbound message;
   - include attachments generated by existing `FILES:` handling/materialization.

Definition of done:

- One batch with two unrelated tasks starts two workers in parallel.
- Both write task/run records.
- Both final responses are queued and sent serially.
- A social response in the same batch can be sent without waiting for task completion.

## Phase 7 — Cancellation, Pivot, and Await-Instruction Enforcement

Functional outcome: stop/pivot/wait instructions affect active implementation tasks, not classifier/router runs.

Implementation:

1. Extend `run_opencode()` and worker management to support cancellation:
   - task has `active_implementer_run_id`;
   - cancel request marks task/run;
   - worker checks control state;
   - running subprocess is terminated gracefully, then killed after timeout if needed.
2. `cancel_active_implementation`:
   - mark task `cancel_requested`;
   - stop active run;
   - mark task completed/cancelled or stale according to final state;
   - enqueue confirmation.
3. `pivot_active_implementation`:
   - cancel current run;
   - merge `topicUpdate` into task topic;
   - start a new worker run using updated topic and queued context;
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
- Pivot restarts the targeted task with updated topic.
- Await-instruction blocks unsafe continuation and posts one conflict summary.
- Operator follow-up resumes or pivots the same task.

## Phase 8 — Global Directive Inclusion Check

Functional outcome: global directives are guaranteed to be included in classifier/router and worker prompts, while preserving existing directive injection behavior.

Implementation:

1. Inspect current `_directive_block()` behavior in `flow/runner.py` and `DirectiveStore.get_for_subagent()` / formatting methods.
2. Ensure directives with `global_directive=True` from operator pk are included for:
   - the first planner/router classifier prompt;
   - domain/technical/social worker prompts as appropriate;
   - specialist prompts that already receive filtered directives.
3. Do not replace the directive system.
4. Do not invent a new multi-user directive store unless the current code lacks a needed read path.
5. If current `get_for_subagent()` excludes global directives accidentally, update that method or add a narrow helper so global directives are merged into existing filtered results.
6. Preserve directive priority/order metadata in formatted output.

Definition of done:

- A test directive with `global_directive=True` appears in the planner/router classifier prompt.
- It also appears in specialist/domain prompt where applicable.
- Existing type-filtered specialist directives still work.

## Phase 9 — Tests and Pod Verification

Functional outcome: the deployed test pod proves the flow works under realistic Discord/channel conditions.

Required tests:

1. Three messages arrive quickly in one channel.
   - One classifier/router run starts.
   - Classifier input includes all three messages.
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
   - Two workers run in parallel.
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
9. Two pods/store clients race on classifier lock.
   - One wins.
10. Two pods/store clients race on outbound lock.
   - One drains.

Verification commands/process:

- Unit tests for models, DynamoDB float conversion, conditional lock/idempotency behavior with mocks/stubs, classifier output parsing, decision idempotency, cursor/edit handling, and outbound ordering.
- Terraform validation only:
  - `terraform fmt`
  - `terraform validate`
  - `terraform plan`
- Test pod verification in `if-portals-test` after building/deploying test images per repo workflow.
- Inspect pod logs for classifier lock, dirty pass, task worker, and outbound queue events.

## Implementation Order Summary

Each phase must be independently functional:

1. DynamoDB registry + pending activity signal + fresh-history existing response still works.
2. DynamoDB classifier locks + dirty/max-wait behavior works.
3. Existing planner/router becomes batch classifier and emits decisions.
4. Decisions apply idempotently and create task/outbox state.
5. Outbound queue serializes Discord sends.
6. Parallel task workers run and enqueue outputs.
7. Cancel/pivot/await-instruction actually control active tasks.
8. Global directives are guaranteed in prompts using existing directive system.
9. Tests + Terraform validation + deployed pod verification.
