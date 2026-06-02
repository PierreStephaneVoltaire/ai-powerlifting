




from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from channels.execution_models import ClassifierDecision, ClassificationBatch, IntentRecord
from channels.execution_store import get_execution_store
from channels.status import StatusType, send_status
from config import IF_DEFAULT_DIRECT_MODEL, OPENCODE_PLANNER_MODEL, PROJECT_ROOT

from .context import build_runtime_context
from .model_catalog import format_model_catalog, load_model_ids, load_model_selection_rules
from .opencode import run_opencode
from .opencode_config import write_opencode_config
from .plan import (
    ClassificationParseError,
    ClassificationResult,
    IFPlan,
    fallback_plan,
    parse_classification_file,
)

logger = logging.getLogger(__name__)

def _main_system_prompt() -> str:
    path = PROJECT_ROOT / "main_system_prompt.txt"
    if not path.exists():
        path = PROJECT_ROOT / "app" / "main_system_prompt.txt"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return "You are IF, a direct, pragmatic assistant."

def _directive_block(types: list[str] | None = None) -> str:
    try:
        from storage.factory import get_directive_store
        store = get_directive_store()
        if types is None:
            directives = store.get_for_subagent(["core"])
        else:
            directives = store.get_for_subagent(types)
        return store.format_directives(directives)
    except Exception as exc:
        logger.debug("Directive injection unavailable: %s", exc)
        return ""

def _specialist_catalog() -> tuple[set[str], str]:
    try:
        from agent.specialists import list_specialists
    except Exception as exc:
        logger.warning("Specialist catalog unavailable: %s", exc)
        return {"general"}, "- general: General IF response"
    specialists = list_specialists()
    lines = []
    slugs = {"general"}
    for spec in specialists:
        slugs.add(spec.slug)
        lines.append(f"- {spec.slug}: {spec.description}")
    return slugs, "\n".join(lines)

async def _opencode_status(line: str) -> None:
    await send_status(StatusType.TOOL_STARTED, "opencode", line)

def batch_classifier_prompt(
    history_path: Path,
    model_ids: list[str],
    model_selection_rules: str,
    specialist_catalog: str,
    runtime_context: str,
    batch_id: str,
    candidate_source_message_ids: list[str],
    active_tasks_summary: str,
    bot_id: str | None = None,
) -> str:
    classification_file = f"classification.batch.{batch_id}.json"
    candidate_ids_text = "\n".join(f"- {mid}" for mid in candidate_source_message_ids) if candidate_source_message_ids else "(none)"
    active_tasks_block = f"\nActive implementation tasks in this channel:\n{active_tasks_summary}\n" if active_tasks_summary else "\nNo active implementation tasks in this channel.\n"
    bot_id_note = f"\nBot user ID (exclude this bot's own messages): {bot_id}\n" if bot_id else ""
    return f"""You are IF's batch classification stage for a Discord channel.

Read `{history_path.name}` in the current directory as the source of truth.
You are classifying a debounced batch of Discord channel activity.
You are not classifying a single message.

Candidate new messages for this batch (Discord message IDs):
{candidate_ids_text}
{active_tasks_block}{bot_id_note}
Write your classification output to `{classification_file}` with this exact JSON structure:

```json
{{
  "batchSummary": "short summary of the batch",
  "decisions": [
    {{
      "intentId": "unique id for this intent",
      "kind": "social|task|implementation_control|clarification|ignore",
      "action": "social_response|start_new_task|append_to_active_implementation|pivot_active_implementation|cancel_active_implementation|queue_on_active_implementation|await_instruction_for_active_implementation|ask_clarifying_target|ignore",
      "sourceMessageIds": ["discord message ids"],
      "targetTaskId": "optional existing task id",
      "confidence": 0.0,
      "reason": "why this decision was made",
      "needsPlanning": true,
      "selectedSpecialist": "optional specialist slug",
      "selectedModel": "optional model from eligible models",
      "socialResponseText": "optional immediate social text",
      "responseText": "optional immediate text",
      "plannerIntent": {{
        "title": "string", "intent": "string", "summary": "string", "currentGoal": "string",
        "acceptanceCriteria": [], "constraints": [], "keywords": [], "entities": [],
        "likelyFiles": [], "nonGoals": []
      }},
      "topicUpdate": null,
      "conflict": null
    }}
  ]
}}
```

Write ONLY the JSON file. Do not write plan.md.

IF personality and core posture:
{_main_system_prompt()}

Core directives:
{_directive_block(["core"])}

Runtime compatibility and available context:
{runtime_context}

Specialists:
{specialist_catalog}

Eligible models:
{format_model_catalog(model_ids)}

Model selection policy from `models/model_selection_rules.md`:
{model_selection_rules or "No model selection rules file was found."}

Classification rules:
- You are classifying a debounced batch of Discord channel activity.
- You are not classifying a single message.
- Read history.md as the source of truth. Return batch decisions for the new unclassified messages only.
- You may return multiple decisions when the batch contains independent intents.
- Group related new messages into the same decision.
- Split unrelated conversations into separate decisions.
- If several people are brainstorming or disagreeing about one active task, resolve the batch-level intent; do not treat each message as a separate command.
- Operator/admin instructions take precedence over conflicting non-operator opinions.
- If non-operators conflict and there is no clear operator direction, return await_instruction_for_active_implementation.
- Only stop/pivot/wait active implementation tasks, not classifier/router runs.
- Social responses do not interrupt active implementations.
- If a social/simple question appears alongside a task update, return separate decisions.
- If unrelated code tasks appear in the same batch, return multiple start_new_task decisions.
- If two decisions would conflict on the same target task, merge them or return await_instruction_for_active_implementation.
- `selectedModel` must be exactly one ID from the eligible model list.
- `selectedSpecialist` must be one of the listed specialist slugs or omitted.
- Every decision must have a unique `intentId`.
"""

class BatchClassificationError(RuntimeError):
    pass

def decision_to_ifplan(decision: ClassifierDecision) -> IFPlan:
    specialist = decision.selected_specialist or "general"
    model = decision.selected_model or IF_DEFAULT_DIRECT_MODEL
    if decision.kind == "social":
        interaction_type = "social"
    elif decision.action == "start_new_task" and decision.needs_planning:
        interaction_type = "domain"
    elif decision.kind == "task":
        interaction_type = "domain"
    else:
        interaction_type = "domain"
    prompt = decision.social_response_text or decision.response_text or decision.reason
    if decision.planner_intent:
        intent = decision.planner_intent
        parts = []
        if intent.get("title"):
            parts.append(f"Title: {intent['title']}")
        if intent.get("intent"):
            parts.append(f"Intent: {intent['intent']}")
        if intent.get("summary"):
            parts.append(f"Summary: {intent['summary']}")
        if intent.get("currentGoal"):
            parts.append(f"Current Goal: {intent['currentGoal']}")
        if intent.get("acceptanceCriteria"):
            parts.append(f"Acceptance Criteria: {', '.join(str(c) for c in intent['acceptanceCriteria'])}")
        if intent.get("constraints"):
            parts.append(f"Constraints: {', '.join(str(c) for c in intent['constraints'])}")
        if parts:
            prompt = "\n".join(parts)
    return fallback_plan(
        prompt=prompt,
        selected_model=model,
        specialist=specialist,
        interaction_type=interaction_type,
        reason=decision.reason or "Batch classifier decision",
    )

async def run_batch_classification(
    session_dir: Path,
    channel_id: str,
    candidate_source_message_ids: list[str],
    runtime_context: str = "",
    active_tasks_summary: str = "",
    bot_id: str | None = None,
) -> ClassificationResult:
    batch_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    classification_file = session_dir / f"classification.batch.{batch_id}.json"
    classification_file.unlink(missing_ok=True)
    model_ids = load_model_ids()
    model_selection_rules = load_model_selection_rules()
    known_specialists, catalog = _specialist_catalog()
    write_opencode_config(session_dir, tool_names=[], mcp_servers=[])
    status_dir = session_dir / ".if"
    status_dir.mkdir(parents=True, exist_ok=True)
    status_path = status_dir / f"status.classifier.{run_id}.log"
    status_path.write_text("", encoding="utf-8")
    store = get_execution_store()
    now = datetime.now(timezone.utc).isoformat()
    batch = ClassificationBatch(
        batch_id=batch_id,
        channel_id=channel_id,
        classifier_run_id=run_id,
        started_at=now,
        completed_at=None,
        history_fetched_at=None,
        history_oldest_message_id=None,
        history_newest_message_id=None,
        cursor_before_message_id=None,
        cursor_after_message_id=None,
        edited_since=None,
        candidate_source_message_ids=candidate_source_message_ids,
        status="running",
        batch_summary=None,
        decisions=[],
        error=None,
        version=1,
        ttl=None,
    )
    await store.put_classification_batch(batch)
    try:
        result = await run_opencode(
            agent="planner",
            model=OPENCODE_PLANNER_MODEL,
            session_dir=session_dir,
            prompt=batch_classifier_prompt(
                history_path=session_dir / "history.md",
                model_ids=model_ids,
                model_selection_rules=model_selection_rules,
                specialist_catalog=catalog,
                runtime_context=runtime_context,
                batch_id=batch_id,
                candidate_source_message_ids=candidate_source_message_ids,
                active_tasks_summary=active_tasks_summary,
                bot_id=bot_id,
            ),
            status_file=status_path,
            status_callback=_opencode_status,
        )
        if result.returncode != 0:
            raise BatchClassificationError(result.stderr or result.stdout or "Batch classifier non-zero exit")
    except Exception as exc:
        if not isinstance(exc, BatchClassificationError):
            exc = BatchClassificationError(str(exc))
        batch.status = "failed"
        batch.error = str(exc)[:2000]
        batch.completed_at = datetime.now(timezone.utc).isoformat()
        await store.put_classification_batch(batch)
        raise
    if not classification_file.exists():
        raise BatchClassificationError(f"Batch classifier did not write {classification_file.name}")
    try:
        classification = parse_classification_file(classification_file, model_ids, known_specialists, batch_id=batch_id)
    except ClassificationParseError as exc:
        batch.status = "failed"
        batch.error = str(exc)[:2000]
        batch.completed_at = datetime.now(timezone.utc).isoformat()
        await store.put_classification_batch(batch)
        raise BatchClassificationError(str(exc)) from exc
    completed_at = datetime.now(timezone.utc).isoformat()
    batch.status = "completed"
    batch.completed_at = completed_at
    batch.batch_summary = classification.batch_summary
    batch.decisions = [
        {"intent_id": d.intent_id, "kind": d.kind, "action": d.action,
         "source_message_ids": d.source_message_ids, "target_task_id": d.target_task_id,
         "confidence": d.confidence, "reason": d.reason}
        for d in classification.decisions
    ]
    await store.put_classification_batch(batch)
    for decision in classification.decisions:
        intent = IntentRecord(
            intent_id=decision.intent_id,
            batch_id=batch_id,
            channel_id=channel_id,
            action=decision.action,
            kind=decision.kind,
            source_message_ids=decision.source_message_ids,
            target_task_id=decision.target_task_id,
            status="pending",
            created_at=completed_at,
            updated_at=completed_at,
            error=None,
            ttl=None,
        )
        await store.put_intent_record(intent)
    return classification
