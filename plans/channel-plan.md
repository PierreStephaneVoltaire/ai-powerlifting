Read `.claude/CLAUDE.md`  first.

Classification is NOT per Discord message.

The classifier is an OpenCode execution that should run per debounced Discord channel batch.

For a channel:
- collect new Discord messages for a short debounce window
- run exactly one classifier OpenCode execution for that channel
- classifier receives the full relevant chat history, all newly accumulated messages, active implementation tasks, pending conflicts, and effective directives
- classifier emits an ARRAY of intent/action JSON objects
- orchestrator applies those decisions and can fan out unrelated work in parallel

Do not launch one classifier per message.
Do not allow multiple classifiers to run concurrently for the same Discord channel.

Core flow:
1. Discord message arrives.
2. Store/dedupe the message in DynamoDB as pending classification.
3. Update the channel classification state and debounce deadline.
4. A channel classifier coordinator waits for the debounce deadline.
5. It acquires a short per-channel classifier lock.
6. It loads:
   - full relevant chat history
   - pending unclassified messages since the last classifier cursor
   - active implementation tasks in the channel
   - recent completed tasks if useful
   - pending conflicts / awaiting-instruction tasks
   - effective global + user directives
7. It starts one OpenCode classifier run for the channel batch.
8. Classifier emits JSON with an array of decisions/intents.
9. Orchestrator records the classification batch and intent records.
10. Orchestrator starts planner/implementer runs for task decisions.
11. Orchestrator enqueues social/clarifying/final Discord responses into a per-channel outbound queue.
12. If new messages arrived while classification was running, mark the channel dirty and schedule another debounced classification pass.

Required rule:
- `channelId` is the classifier serialization scope.
- `channelId` is NOT a long-running implementation lock.
- A channel can have many active implementation tasks.
- Only one classifier may run per channel at a time.
- Many implementers may run in parallel if the classifier batch produced multiple unrelated intents.
- Discord sends must be serialized per channel through an outbound queue/lock.

Add or update these concepts:

```ts
type ChannelClassificationState = {
  channelId: string

  status:
    | "idle"
    | "debouncing"
    | "classifying"

  debounceUntil: string
  lastClassifierStartedAt?: string
  lastClassifierFinishedAt?: string

  activeClassifierRunId?: string
  classifierLockOwner?: string
  classifierLockExpiresAt?: string

  lastClassifiedMessageCursor?: string
  lastClassifiedAt?: string

  dirty: boolean
  pendingMessageCount: number

  version: number
  updatedAt: string
}
```

```ts
type PendingChannelMessage = {
  messageId: string
  channelId: string
  authorId: string
  content: string
  createdAt: string

  status:
    | "pending_classification"
    | "included_in_batch"
    | "classified"
    | "ignored"

  classificationBatchId?: string
  sourceIntentIds?: string[]

  replyToMessageId?: string
  mentionedTaskIds?: string[]

  ttlEpochSeconds?: number
}
```

```ts
type ClassificationBatch = {
  batchId: string
  channelId: string
  classifierRunId: string

  startedAt: string
  completedAt?: string

  includedMessageIds: string[]
  historyCursorBefore?: string
  historyCursorAfter?: string

  status:
    | "running"
    | "completed"
    | "failed"

  decisions?: ClassifierDecision[]

  version: number
  ttlEpochSeconds?: number
}
```

```ts
type ClassifierDecision = {
  intentId: string

  kind:
    | "social"
    | "task"
    | "implementation_control"
    | "clarification"
    | "ignore"

  action:
    | "social_response"
    | "start_new_task"
    | "append_to_active_implementation"
    | "pivot_active_implementation"
    | "cancel_active_implementation"
    | "queue_on_active_implementation"
    | "await_instruction_for_active_implementation"
    | "ask_clarifying_target"
    | "ignore"

  sourceMessageIds: string[]

  targetTaskId?: string

  confidence: number
  reason: string

  needsPlanning: boolean

  selectedPersonality?: string

  socialResponseText?: string

  plannerIntent?: {
    title: string
    intent: string
    summary: string
    currentGoal: string
    acceptanceCriteria: string[]
    constraints: string[]
    keywords: string[]
    entities: string[]
    likelyFiles?: string[]
    nonGoals?: string[]
  }

  topicUpdate?: {
    title?: string
    intent?: string
    summary?: string
    currentGoal?: string
    acceptanceCriteria?: string[]
    constraints?: string[]
    keywords?: string[]
    entities?: string[]
    likelyFiles?: string[]
    nonGoals?: string[]
  }

  conflict?: {
    summary: string
    requiresOperator: boolean
    options: Array<{
      label: string
      summary: string
      supportingUserIds: string[]
    }>
  }

  responseText?: string
}
```

```ts
type IntentRecord = {
  intentId: string
  batchId: string
  channelId: string

  action: ClassifierDecision["action"]
  kind: ClassifierDecision["kind"]

  sourceMessageIds: string[]
  targetTaskId?: string

  status:
    | "pending"
    | "applying"
    | "running"
    | "completed"
    | "failed"
    | "skipped"

  createdAt: string
  updatedAt: string

  ttlEpochSeconds?: number
}
```

Implementation task remains separate from classifier batch:

```ts
type ImplementationTask = {
  taskId: string
  channelId: string

  status:
    | "implementing"
    | "awaiting_instruction"
    | "cancel_requested"
    | "pivot_requested"
    | "completed"
    | "failed"
    | "stale"

  rootDiscordMessageId: string
  relatedDiscordMessageIds: string[]

  activeImplementerRunId?: string
  latestPlannerRunId?: string

  selectedPersonality?: string

  topic: {
    title: string
    intent: string
    summary: string
    currentGoal: string
    acceptanceCriteria: string[]
    constraints: string[]
    keywords: string[]
    entities: string[]
    repo?: string
    branch?: string
    worktree?: string
    likelyFiles?: string[]
    touchedFiles?: string[]
    nonGoals?: string[]
  }

  pendingConflict?: {
    createdAt: string
    createdByMessageIds: string[]
    summary: string
    requiresOperator: boolean
    options: Array<{
      label: string
      summary: string
      supportingUserIds: string[]
    }>
  }

  queuedMessages: Array<{
    messageId: string
    authorId: string
    content: string
    createdAt: string
    reason: "extra_context" | "post_completion_followup" | "wait_until_safe"
  }>

  control?: {
    stopRequested?: boolean
    stopRequestedBy?: string
    stopRequestedAt?: string
    stopReason?: string

    pivotRequested?: boolean
    pivotRequestedBy?: string
    pivotRequestedAt?: string
    pivotReason?: string
  }

  createdAt: string
  updatedAt: string
  version: number
  ttlEpochSeconds?: number
}
```

Add a per-channel outbound queue so parallel implementers do not mix Discord responses:

```ts
type DiscordOutboundMessage = {
  outboundId: string
  channelId: string

  taskId?: string
  intentId?: string
  batchId?: string

  type:
    | "social_response"
    | "clarifying_question"
    | "task_started"
    | "task_update"
    | "task_completed"
    | "task_failed"
    | "await_instruction"
    | "cancel_confirmation"

  priority: number

  content: string

  replyToMessageId?: string
  allowedMentions?: unknown

  status:
    | "queued"
    | "sending"
    | "sent"
    | "failed"

  sendAfter?: string
  createdAt: string
  updatedAt: string

  discordMessageId?: string

  idempotencyKey: string
  ttlEpochSeconds?: number
}
```

```ts
type ChannelOutboundState = {
  channelId: string
  status: "idle" | "sending"

  lockOwner?: string
  lockExpiresAt?: string

  lastSentAt?: string
  version: number
  updatedAt: string
}
```

Outbound rule:
- No planner or implementer should post directly to Discord.
- OpenCode produces output.
- The app converts output to `DiscordOutboundMessage`.
- A single outbound sender per channel drains the queue using a short DynamoDB lock.
- This allows parallel implementation work while serializing visible Discord messages.

DynamoDB table:
Use a new table, for example `AgentExecutionRegistry`.

Store item types:
1. channel classification state
2. pending Discord messages
3. classification batch records
4. intent records
5. implementation task cards
6. OpenCode run records
7. outbound Discord queue messages
8. channel outbound locks/states

Suggested single-table keys:

```ts
// Channel state
pk = `CHANNEL#${channelId}`
sk = `STATE#classification`

// Pending/included/classified messages by channel
pk = `CHANNEL#${channelId}`
sk = `MSG#${createdAt}#${messageId}`

// Message dedupe direct lookup
pk = `MESSAGE#${messageId}`
sk = `META`

// Classification batch
pk = `CHANNEL#${channelId}`
sk = `BATCH#${batchId}`

// Intent records
pk = `BATCH#${batchId}`
sk = `INTENT#${intentId}`

// Active implementation task
pk = `CHANNEL#${channelId}`
sk = `TASK#${taskId}`

// OpenCode run direct lookup
pk = `RUN#${runId}`
sk = `META`

// Runs by task
pk = `TASK#${taskId}`
sk = `RUN#${runId}`

// Outbound queue
pk = `CHANNEL#${channelId}`
sk = `OUTBOX#${priority}#${createdAt}#${outboundId}`

// Outbound state/lock
pk = `CHANNEL#${channelId}`
sk = `STATE#outbound`
```

Classifier debounce behavior:
- On each new message:
  - dedupe by Discord `messageId`
  - store as `pending_classification`
  - set `ChannelClassificationState.status = "debouncing"` unless currently `classifying`
  - set `debounceUntil = now + debounceMs`
  - increment `pendingMessageCount`
  - if already classifying, set `dirty = true`
- When debounce fires:
  - try to acquire `STATE#classification` lock for the channel
  - if another classifier owns it, exit
  - if `debounceUntil` is still in the future, wait/retry
  - start one classifier OpenCode run
  - mark included pending messages as `included_in_batch`
  - create `ClassificationBatch`
- While classifier runs:
  - new messages do not start another classifier
  - they are stored as pending and `dirty = true`
- When classifier finishes:
  - parse JSON array of decisions
  - store decisions as intent records
  - mark included messages as `classified`
  - release classifier lock
  - if `dirty === true` or pending messages remain, schedule another debounce pass

Add a max wait:
- Use both debounce and max wait.
- Example:
  - debounce quiet window: 1500ms-3000ms
  - max batch wait: 8000ms-15000ms
- This prevents endless typing from delaying classification forever.

Classifier OpenCode prompt update:
The classifier prompt must say something along the lines of (edit the exsiting one to add the4 missing pieces never fully rewrite the prompts as they are working fine):

```markdown
You are classifying a debounced batch of Discord channel activity.

You are not classifying a single message.

You will receive:
- recent/full relevant channel history
- the new unclassified messages in this batch
- active implementation tasks in this channel
- pending conflicts and awaiting-instruction tasks
- bot's recent messages
- effective global/user directives
- operator/admin info

Return JSON only.

Return an object:

{
  "batchSummary": string,
  "decisions": ClassifierDecision[]
}

You may return multiple decisions if the batch contains multiple independent conversations/intents.

Rules:
- Group related new messages into the same decision.
- Split unrelated conversations into separate decisions.
- If several people are brainstorming or disagreeing about one active implementation, do not treat each message as a separate command.
- Resolve the batch-level intent.
- Operator/admin instructions take precedence over conflicting non-operator opinions.
- If non-operators conflict and there is no clear operator direction, return `await_instruction_for_active_implementation`.
- Only stop/pivot/wait active implementation tasks, not classifier runs.
- Social responses do not interrupt active implementations.
- If a social/simple question appears alongside a task update, return separate decisions.
- If unrelated code tasks appear in the same batch, return multiple `start_new_task` decisions.
- If two decisions would conflict on the same target task, merge them into one decision, or return `await_instruction_for_active_implementation`.
}
```

Classifier output schema:

```ts
type ClassifierBatchOutput = {
  batchSummary: string
  decisions: ClassifierDecision[]
}
```

Application of decisions:
- Apply decisions idempotently by `intentId`.
- `social_response`:
  - enqueue Discord outbound message
- `start_new_task`:
  - create new `ImplementationTask`
  - start planner
  - start implementer
- `append_to_active_implementation`:
  - attach messages to task
  - queue as context or feed live if supported
- `pivot_active_implementation`:
  - stop active implementer
  - update task topic
  - rerun planner
  - start new implementer
- `cancel_active_implementation`:
  - request stop on active implementer
  - enqueue cancel confirmation
- `queue_on_active_implementation`:
  - append to task queue
- `await_instruction_for_active_implementation`:
  - stop/pause implementer
  - mark task awaiting instruction
  - enqueue conflict summary asking for operator/consensus
- `ask_clarifying_target`:
  - enqueue clarifying question
- `ignore`:
  - mark source messages classified/ignored

OpenCode run identity:
- Add `runId` to every OpenCode execution.
- Classifier run title should be batch/channel based, not message based:

```bash
opencode run \
  --agent classifier \
  --format json \
  --title "classifier:discord:<channelId>:batch:<batchId>:run:<runId>" \
  "<classifier prompt>"
```

Planner:

```bash
opencode run \
  --agent planner \
  --format json \
  --title "planner:discord:<channelId>:task:<taskId>:run:<runId>" \
  "<planner prompt>"
```

Implementer:

```bash
opencode run \
  --agent "<selectedPersonality>" \
  --format json \
  --title "implementer:discord:<channelId>:task:<taskId>:run:<runId>" \
  "<implementation prompt>"
```

Directive resolver:
- Before classifier/planner/implementer prompts, resolve effective directives.
- Always include global directives.
- Merge global directives with user directives for users represented in the batch.
- If multiple users are in the batch, include:
  - global directives
  - operator directives if operator is involved
  - user directives grouped by user for authors in the batch
- Deduplicate by directive id first; otherwise canonical hash.
- If `global` is missing:
  - `alpha0` directives are global by default
  - lower-tier directives default to non-global unless existing code has a stronger rule
- Preserve contradictory directives with priority metadata.
- Do not silently discard contradictions.

Acceptance tests:
1. Three messages arrive quickly in the same channel.
   - only one classifier run starts.
   - classifier input includes all three messages.
2. A message arrives while classifier is running.
   - no second classifier starts immediately.
   - channel is marked dirty.
   - another debounced classifier pass runs after the first finishes.
3. One batch contains a social question and a separate code request.
   - classifier returns two decisions.
   - social response is enqueued.
   - task planner/implementer starts separately.
4. One batch contains two unrelated code tasks.
   - classifier returns two `start_new_task` decisions.
   - two planners/implementers may run in parallel.
5. One batch contains conflicting non-operator opinions about one active implementation.
   - classifier returns one `await_instruction_for_active_implementation`.
   - implementation is paused/stopped.
   - one Discord conflict-summary message is enqueued.
6. Operator resolves the conflict.
   - next channel batch routes operator instruction to that task.
   - implementation continues/pivots according to operator direction.
7. Two implementers finish at the same time.
   - both enqueue outbound messages.
   - only one outbound sender posts to Discord at a time.
   - messages do not interleave.
8. Duplicate Discord webhook delivery.
   - same `messageId` is ignored after first write.
9. Multiple pods receive messages for the same channel.
   - Dynamo classifier lock ensures one active classifier.
10. Multiple pods try to send Discord responses to the same channel.
   - outbound lock ensures one sender drains the channel queue.
```

The main architecture should be:

```text
per-channel inbox
  -> debounce
  -> one classifier for channel batch
  -> array of intent records
  -> parallel internal work where safe
  -> per-channel outbound queue
  -> serialized Discord messages
```
