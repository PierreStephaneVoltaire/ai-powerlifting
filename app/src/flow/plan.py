
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from channels.execution_models import ClassifierDecision

INTERACTION_TYPES = {"social", "domain", "technical"}

VALID_CLASSIFIER_KINDS = {"social", "task", "implementation_control", "clarification", "ignore"}

VALID_CLASSIFIER_ACTIONS = {
    "social_response",
    "start_new_task",
    "append_to_active_implementation",
    "pivot_active_implementation",
    "cancel_active_implementation",
    "queue_on_active_implementation",
    "await_instruction_for_active_implementation",
    "ask_clarifying_target",
    "ignore",
}

KIND_ACTION_COMPAT: dict[str, set[str]] = {
    "social": {"social_response", "ignore"},
    "task": {"start_new_task", "ignore"},
    "implementation_control": {
        "append_to_active_implementation",
        "pivot_active_implementation",
        "cancel_active_implementation",
        "queue_on_active_implementation",
        "await_instruction_for_active_implementation",
        "ignore",
    },
    "clarification": {"ask_clarifying_target", "ignore"},
    "ignore": {"ignore"},
}

class PlanParseError(ValueError):
    pass

class ClassificationParseError(ValueError):
    pass

@dataclass(frozen=True)
class IFPlan:
    intent_summary: str
    interaction_type: str
    specialist: str
    thinking_mode: bool
    selected_model: str
    prompt: str
    raw: str

_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.DOTALL)

def parse_plan_text(
    text: str,
    eligible_models: list[str],
    known_specialists: set[str],
) -> IFPlan:
    match = _FRONTMATTER_RE.match(text.strip())
    if not match:
        raise PlanParseError("plan.md must start with YAML front matter")

    metadata_raw, prompt = match.group(1), match.group(2).strip()
    metadata = yaml.safe_load(metadata_raw) or {}
    if not isinstance(metadata, dict):
        raise PlanParseError("plan.md front matter must be a mapping")

    missing = [
        key
        for key in ("intent_summary", "interaction_type", "specialist", "thinking_mode", "selected_model")
        if key not in metadata
    ]
    if missing:
        raise PlanParseError(f"plan.md missing required fields: {', '.join(missing)}")

    interaction_type = str(metadata["interaction_type"]).strip().lower()
    if interaction_type not in INTERACTION_TYPES:
        raise PlanParseError(f"invalid interaction_type: {interaction_type}")

    specialist = str(metadata["specialist"]).strip()
    if specialist and specialist not in known_specialists and specialist != "general":
        raise PlanParseError(f"unknown specialist: {specialist}")

    selected_model = str(metadata["selected_model"]).strip()
    if selected_model not in set(eligible_models):
        raise PlanParseError(f"selected_model is not in models/model_ids.txt: {selected_model}")

    if not prompt:
        raise PlanParseError("plan.md prompt body is empty")

    return IFPlan(
        intent_summary=str(metadata["intent_summary"]).strip(),
        interaction_type=interaction_type,
        specialist=specialist or "general",
        thinking_mode=bool(metadata["thinking_mode"]),
        selected_model=selected_model,
        prompt=prompt,
        raw=text,
    )

def parse_plan_file(
    path: Path,
    eligible_models: list[str],
    known_specialists: set[str],
) -> IFPlan:
    return parse_plan_text(path.read_text(encoding="utf-8"), eligible_models, known_specialists)

def fallback_plan(
    prompt: str,
    selected_model: str,
    specialist: str = "general",
    interaction_type: str = "social",
    reason: str = "Planner fallback",
) -> IFPlan:
    raw = (
        "---\n"
        f"intent_summary: {reason!r}\n"
        f"interaction_type: {interaction_type!r}\n"
        f"specialist: {specialist!r}\n"
        "thinking_mode: false\n"
        f"selected_model: {selected_model!r}\n"
        "---\n\n"
        f"{prompt.strip()}\n"
    )
    return IFPlan(
        intent_summary=reason,
        interaction_type=interaction_type,
        specialist=specialist,
        thinking_mode=False,
        selected_model=selected_model,
        prompt=prompt.strip(),
        raw=raw,
    )

@dataclass(frozen=True)
class ClassificationResult:
    batch_id: str
    batch_summary: str
    decisions: list[ClassifierDecision]
    raw: str

_CAMEL_TO_SNAKE = {
    "intentId": "intent_id",
    "sourceMessageIds": "source_message_ids",
    "targetTaskId": "target_task_id",
    "needsPlanning": "needs_planning",
    "selectedSpecialist": "selected_specialist",
    "selectedModel": "selected_model",
    "socialResponseText": "social_response_text",
    "responseText": "response_text",
    "plannerIntent": "planner_intent",
    "topicUpdate": "topic_update",
    "batchSummary": "batch_summary",
}

def _camelize_to_snake(d: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in d.items():
        out[_CAMEL_TO_SNAKE.get(k, k)] = v
    return out

def parse_classification_text(
    text: str,
    eligible_models: list[str],
    known_specialists: set[str],
) -> ClassificationResult:
    text = text.strip()
    if not text:
        raise ClassificationParseError("classification output is empty")

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        json_match = re.search(r"\{[\s\S]*\}", text)
        if not json_match:
            raise ClassificationParseError("classification output is not valid JSON and no JSON object found")
        try:
            data = json.loads(json_match.group(0))
        except json.JSONDecodeError:
            raise ClassificationParseError("classification output is not valid JSON")

    if not isinstance(data, dict):
        raise ClassificationParseError("classification output must be a JSON object")

    mapped = _camelize_to_snake(data)
    batch_summary = str(mapped.get("batch_summary") or "").strip()
    if not batch_summary:
        raise ClassificationParseError("classification output missing batchSummary")

    raw_decisions = mapped.get("decisions")
    if not isinstance(raw_decisions, list) or not raw_decisions:
        raise ClassificationParseError("classification output missing or empty decisions array")

    eligible_set = set(eligible_models)
    parsed: list[ClassifierDecision] = []
    errors: list[str] = []

    for i, raw_dec in enumerate(raw_decisions):
        if not isinstance(raw_dec, dict):
            errors.append(f"decision[{i}] is not an object")
            continue
        dec = _camelize_to_snake(raw_dec)

        intent_id = str(dec.get("intent_id") or "").strip()
        if not intent_id:
            errors.append(f"decision[{i}] missing intentId")
            continue

        kind = str(dec.get("kind") or "").strip().lower()
        if kind not in VALID_CLASSIFIER_KINDS:
            errors.append(f"decision[{i}] invalid kind: {kind}")
            continue

        action = str(dec.get("action") or "").strip()
        if action not in VALID_CLASSIFIER_ACTIONS:
            errors.append(f"decision[{i}] invalid action: {action}")
            continue

        allowed_actions = KIND_ACTION_COMPAT.get(kind, set())
        if action not in allowed_actions:
            errors.append(f"decision[{i}] action {action} incompatible with kind {kind}")
            continue

        specialist = dec.get("selected_specialist")
        if specialist and str(specialist).strip() not in known_specialists and str(specialist).strip() != "general":
            errors.append(f"decision[{i}] unknown specialist: {specialist}")
            continue

        model = dec.get("selected_model")
        if model and str(model).strip() not in eligible_set:
            errors.append(f"decision[{i}] selected_model not in models/model_ids.txt: {model}")
            continue

        confidence = float(dec.get("confidence", 0.0))

        parsed.append(ClassifierDecision(
            intent_id=intent_id,
            kind=kind,
            action=action,
            source_message_ids=[str(m) for m in (dec.get("source_message_ids") or [])],
            target_task_id=str(dec["target_task_id"]).strip() if dec.get("target_task_id") else None,
            confidence=confidence,
            reason=str(dec.get("reason") or ""),
            needs_planning=bool(dec.get("needs_planning")),
            selected_specialist=str(specialist).strip() if specialist else None,
            selected_model=str(model).strip() if model else None,
            social_response_text=str(dec["social_response_text"]).strip() if dec.get("social_response_text") else None,
            response_text=str(dec["response_text"]).strip() if dec.get("response_text") else None,
            planner_intent=dec.get("planner_intent"),
            topic_update=dec.get("topic_update"),
            conflict=dec.get("conflict"),
        ))

    if errors and not parsed:
        raise ClassificationParseError("; ".join(errors))
    if errors:
        import logging
        logging.getLogger(__name__).warning("Classification parse warnings: %s", "; ".join(errors))

    return ClassificationResult(
        batch_id="",
        batch_summary=batch_summary,
        decisions=parsed,
        raw=text,
    )

def parse_classification_file(
    path: Path,
    eligible_models: list[str],
    known_specialists: set[str],
    batch_id: str = "",
) -> ClassificationResult:
    result = parse_classification_text(
        path.read_text(encoding="utf-8"),
        eligible_models,
        known_specialists,
    )
    return ClassificationResult(
        batch_id=batch_id,
        batch_summary=result.batch_summary,
        decisions=result.decisions,
        raw=result.raw,
    )

