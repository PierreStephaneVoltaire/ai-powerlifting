
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from config import MODELS_PATH

MODEL_IDS_FILENAME = "model_ids.txt"
MODEL_SELECTION_RULES_FILENAME = "model_selection_rules.md"

def load_model_ids(path: str | Path | None = None) -> list[str]:
    models_file = Path(path) if path else Path(MODELS_PATH) / MODEL_IDS_FILENAME
    if not models_file.exists():
        return []

    model_ids: list[str] = []
    for raw_line in models_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        model_ids.append(line)
    return model_ids

def load_model_selection_rules(path: str | Path | None = None) -> str:
    rules_file = Path(path) if path else Path(MODELS_PATH) / MODEL_SELECTION_RULES_FILENAME
    if not rules_file.exists():
        return ""

    return rules_file.read_text(encoding="utf-8").strip()

def group_model_ids(model_ids: list[str]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for model_id in model_ids:
        provider = model_id.split("/", 1)[0] if "/" in model_id else "other"
        grouped[provider].append(model_id)
    return dict(sorted(grouped.items()))

def format_model_catalog(model_ids: list[str]) -> str:
    grouped = group_model_ids(model_ids)
    lines: list[str] = []
    for provider, ids in grouped.items():
        lines.append(f"## {provider}")
        for model_id in ids:
            lines.append(f"- {model_id}")
        lines.append("")
    return "\n".join(lines).strip()
