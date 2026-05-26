"""Plan.md parser and validator."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


INTERACTION_TYPES = {"social", "domain", "technical"}


class PlanParseError(ValueError):
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

