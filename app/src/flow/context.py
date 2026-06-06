
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from config import (
    AWS_REGION,
    HEALTH_PROGRAM_PK,
    IF_USER_PK,
    IF_DIARY_SIGNALS_TABLE_NAME,
    IF_HEALTH_TABLE_NAME,
    IF_SELF_REPO_URL,
    SKILLS_PATH,
    PROJECT_ROOT,
    APP_SRC,
)

logger = logging.getLogger(__name__)

def _project_root() -> Path:
    return PROJECT_ROOT

def _text_from_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text", "")))
        return "\n".join(parts)
    return str(content or "")

def _latest_user_text(messages: list[dict[str, Any]]) -> str:
    for msg in reversed(messages):
        if msg.get("role") == "user":
            return _text_from_content(msg.get("content"))
    return ""

def _runtime_tool_command() -> str:
    pythonpath = os.pathsep.join([str(APP_SRC), str(PROJECT_ROOT)])
    return f"PYTHONPATH={pythonpath!r} {sys.executable} -m flow.runtime_tool"

def _load_prompt_text(name: str) -> str:
    try:
        from agent.prompts.loader import load_prompt

        return load_prompt(name)
    except Exception as exc:
        logger.debug("Prompt template unavailable: %s: %s", name, exc)
        return ""

def _load_skill_text(name: str) -> str:
    path = Path(SKILLS_PATH) / name / "SKILL.md"
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception as exc:
        logger.debug("Skill unavailable: %s: %s", name, exc)
        return ""

def _thinking_skill_block() -> str:
    skills = []
    for name in ("deep_think", "sequential_plan", "parallel_analysis"):
        text = _load_skill_text(name)
        if text:
            skills.append(f"## {name}\n{text}")
    if not skills:
        return ""
    return "═══ THINKING MODE SKILLS ═══\n" + "\n\n".join(skills)

def get_operator_context(messages: list[dict[str, Any]], context_id: str) -> str:

    if not context_id:
        return ""
    query = _latest_user_text(messages).strip()
    if not query:
        return ""

    try:
        from memory.user_facts import FactCategory, FactSource, get_user_fact_store

        store = get_user_fact_store()
        facts = store.search(context_id, query, limit=5)
        assessments = store.search(context_id, query, category=FactCategory.MODEL_ASSESSMENT, limit=3)
        merged = {fact.id: fact for fact in facts + assessments}.values()
        if not merged:
            return ""

        lines = ["═══ OPERATOR CONTEXT (LanceDB) ═══"]
        for fact in merged:
            source = "observed" if fact.source in (FactSource.MODEL_OBSERVED, FactSource.MODEL_ASSESSED) else "stated"
            updated = (fact.updated_at or fact.created_at or "")[:10]
            lines.append(f"- [{fact.category.value}] [{source}] {fact.content} ({updated})")
        lines.append("════════════════════════════════")
        return "\n".join(lines)
    except Exception as exc:
        logger.warning("Failed to retrieve operator context: %s", exc)
        return ""

def get_current_signals(user_pk: str = IF_USER_PK) -> dict[str, Any]:

    result: dict[str, Any] = {
        "mental_health_score": None,
        "trend": None,
        "themes": [],
        "life_load": None,
        "social_battery": None,
        "training_status": None,
        "life_chapter": None,
    }
    try:
        import boto3

        diary_table = boto3.resource("dynamodb", region_name=AWS_REGION).Table(IF_DIARY_SIGNALS_TABLE_NAME)
        diary = diary_table.get_item(Key={"pk": user_pk, "sk": "signal#latest"}).get("Item")
        if diary:
            result.update(
                {
                    "mental_health_score": diary.get("score"),
                    "trend": diary.get("trend"),
                    "themes": diary.get("themes", []),
                    "life_load": diary.get("life_load"),
                    "social_battery": diary.get("social_battery"),
                }
            )
    except Exception as exc:
        logger.debug("Diary signal injection unavailable: %s", exc)

    try:
        import boto3

        table = boto3.resource("dynamodb", region_name=AWS_REGION).Table(IF_HEALTH_TABLE_NAME)
        pointer = table.get_item(Key={"pk": HEALTH_PROGRAM_PK, "sk": "program#current"}).get("Item")
        ref_sk = pointer.get("ref_sk") if pointer else None
        program = table.get_item(Key={"pk": HEALTH_PROGRAM_PK, "sk": ref_sk}).get("Item") if ref_sk else None
        if program:
            result["training_status"] = "active"
            result["life_chapter"] = "training"
    except Exception as exc:
        logger.debug("Health signal injection unavailable: %s", exc)

    return {key: value for key, value in result.items() if value not in (None, [], {})}

def _upload_manifest(session_dir: Path, uploaded_files: list[dict[str, Any]] | None) -> str:
    files: list[Path] = []
    for item in uploaded_files or []:
        local_path = item.get("local_path")
        if local_path:
            files.append(Path(local_path))
    uploads_dir = session_dir / "uploads"
    if uploads_dir.exists():
        files.extend(path for path in uploads_dir.rglob("*") if path.is_file())

    deduped = sorted({path.resolve() for path in files if path.exists()})
    if not deduped:
        return ""

    lines = ["═══ DISCORD UPLOADS ═══"]
    for path in deduped:
        try:
            rel = path.relative_to(session_dir)
        except ValueError:
            rel = path
        lines.append(f"- {rel} ({path})")
    lines.append("Use text/CSV/spreadsheet files directly. For images or media, use the attached file context or choose `media_reader`.")
    return "\n".join(lines)

def _self_aware_context_block() -> str:
    """Inject IF self-aware context when the channel is flagged as self_aware."""
    repo_url = IF_SELF_REPO_URL.strip()
    lines = [
        "═══ IF SELF-AWARE CONTEXT ═══",
        "This channel is designated as the IF meta channel.",
        "You are operating on IF itself — treat all questions in this conversation as being about the IF codebase unless explicitly stated otherwise.",
        "",
        "REPO ACCESS:",
    ]
    if repo_url:
        lines.append(f"  IF_SELF_REPO_URL={repo_url}")
        lines.append("  Clone into the current session workspace directory if not already present:")
        lines.append("    git clone --no-checkout \"$IF_SELF_REPO_URL\" ./if-repo")
        lines.append("    cd ./if-repo")
        lines.append("    git sparse-checkout init --cone")
        lines.append("    git sparse-checkout set app specialists skills tools models scripts")
        lines.append("    git checkout main")
        lines.append("  If already cloned in this session, fetch and fast-forward before reading:")
        lines.append("    cd ./if-repo && git fetch --quiet && git pull --ff-only")
        lines.append("")
        lines.append("BRANCH WORK:")
        lines.append("  Before any write, create a feature branch (never commit to main):")
        lines.append("    git checkout main && git pull --ff-only")
        lines.append("    git checkout -b if/YYYYMMDD-short-slug")
        lines.append("  Before pushing a branch, merge latest main and resolve all conflicts:")
        lines.append("    git fetch origin && git merge origin/main")
        lines.append("    # resolve conflicts, then: git add . && git commit")
        lines.append("  Before opening a PR, verify no merge conflicts exist:")
        lines.append("    git diff --check && git merge --no-commit --no-ff origin/main")
        lines.append("    # clean merge required before gh pr create")
    else:
        lines.append("  IF_SELF_REPO_URL is not configured. Set it in the pod config map to enable repo access.")
    lines.append("")
    lines.append("Read AGENTS.md at the repo root first for any unfamiliar subsystem.")
    lines.append("All self-aware directives (self_aware dtype) apply to this conversation.")
    lines.append("═════════════════════════════════")
    return "\n".join(lines)


def build_runtime_context(
    *,
    messages: list[dict[str, Any]],
    context_id: str,
    cache_key: str,
    session_dir: Path,
    uploaded_files: list[dict[str, Any]] | None = None,
    thinking_mode_requested: bool = False,
    self_aware: bool = False,
) -> str:

    blocks: list[str] = []

    signals = get_current_signals()
    if signals:
        blocks.append(f"═══ CURRENT SIGNALS ═══\n{json.dumps(signals, indent=2, default=str)}")

    operator_context = get_operator_context(messages, context_id)
    if operator_context:
        blocks.append(operator_context)

    uploads = _upload_manifest(session_dir, uploaded_files)
    if uploads:
        blocks.append(uploads)

    blocks.append(_load_prompt_text("runtime_compatibility"))

    blocks.append(_load_prompt_text("discord_delivery_contract"))

    runtime_tool = _runtime_tool_command()
    from agent.prompts.loader import render_template
    blocks.append(render_template(
        "runtime_memory_tools",
        runtime_tool_command=runtime_tool,
        context_id=context_id,
        cache_key=cache_key,
    ))

    memory_protocol = _load_prompt_text("memory_protocol.j2")
    if memory_protocol:
        blocks.append(memory_protocol)
    media_protocol = _load_prompt_text("media_protocol.j2")
    if media_protocol:
        blocks.append(media_protocol)

    if self_aware:
        blocks.append(_self_aware_context_block())

    if thinking_mode_requested:
        pondering = _load_prompt_text("pondering_addendum.md")
        if pondering:
            blocks.append(pondering)
        skill_block = _thinking_skill_block()
        if skill_block:
            blocks.append(skill_block)

    return "\n\n".join(block for block in blocks if block).strip()

def uploaded_file_paths(uploaded_files: list[dict[str, Any]] | None) -> list[Path]:
    paths: list[Path] = []
    for item in uploaded_files or []:
        local_path = item.get("local_path")
        if local_path:
            path = Path(local_path)
            if path.exists():
                paths.append(path)
    return paths
