"""LLM-powered budget triage and pre-competition priority analysis.

Stateless: receives the athlete's budget config, items, and upcoming competitions
from the caller and returns a structured triage — overall assessment, locked-in
mandatory items, suggested cuts for over-budget athletes, missing-expense gaps,
and a coach-facing note. Competition day is the absolute north star: mandatory
comp-linked items are never suggested for cuts.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from ai_config import LLM_BASE_URL, OPENROUTER_API_KEY, ANALYSIS_MODEL, ANALYSIS_MODEL_THINKING_BUDGET
from prompts.loader import load_system_prompt

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = load_system_prompt("budget_advisor_system")

_LOCKED_ITEM = {
    "type": "object",
    "properties": {
        "item_id": {"type": "string"},
        "name": {"type": "string"},
        "note": {"type": "string", "description": "Brief AI note, e.g. 'Already purchased.' or 'Not marked as purchased yet.'"},
        "purchased": {"type": "boolean"},
    },
    "required": ["item_id", "name", "note", "purchased"],
}

_CUT_ITEM = {
    "type": "object",
    "properties": {
        "item_id": {"type": "string"},
        "name": {"type": "string"},
        "cost": {"type": "number"},
        "reason": {"type": "string", "description": "Brief, practical, sport-appropriate reason to cut"},
        "rank": {"type": "integer", "description": "1-based ordering, most-recommended cut first"},
    },
    "required": ["item_id", "name", "cost", "reason", "rank"],
}

_GAP_ITEM = {
    "type": "object",
    "properties": {
        "description": {"type": "string"},
        "severity": {"type": "string", "enum": ["info", "warning"]},
    },
    "required": ["description", "severity"],
}

_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "submit_budget_advisor",
        "description": "Return the budget triage and pre-competition priority analysis as structured JSON.",
        "parameters": {
            "type": "object",
            "properties": {
                "overall_assessment": {
                    "type": "string",
                    "description": "One sentence summary referencing the monthly cap, current spend, and nearest competition.",
                },
                "locked_in": {
                    "type": "array",
                    "description": "MANDATORY items that cannot be cut, with a brief note on each.",
                    "items": _LOCKED_ITEM,
                },
                "suggested_cuts": {
                    "type": "array",
                    "description": "Ordered OPTIONAL items recommended for cutting, only when over budget. Empty if under budget.",
                    "items": _CUT_ITEM,
                },
                "gaps": {
                    "type": "array",
                    "description": "Likely-missing expenses based on the competition date and existing items.",
                    "items": _GAP_ITEM,
                },
                "coach_note": {
                    "type": "string",
                    "description": "Short paragraph framed for a coach: things to discuss with the athlete. Empty string if not applicable.",
                },
                "insufficient_data": {"type": "boolean"},
                "insufficient_data_reason": {"type": "string"},
            },
            "required": ["overall_assessment", "locked_in", "suggested_cuts", "gaps", "coach_note"],
        },
    },
}


def _sanitize(value: Any) -> Any:
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return None
        return value
    if isinstance(value, dict):
        return {str(k): _sanitize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize(v) for v in value]
    return value


def _as_number(value: Any, default: float = 0.0) -> float:
    try:
        raw = float(value)
    except (TypeError, ValueError):
        return default
    if raw != raw or raw in (float("inf"), float("-inf")):
        return default
    return raw


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    return default


def _normalize_analysis(args: dict[str, Any], item_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    locked_in = []
    for raw in args.get("locked_in", []) or []:
        if not isinstance(raw, dict):
            continue
        item_id = str(raw.get("item_id", ""))
        item = item_by_id.get(item_id, {})
        locked_in.append({
            "item_id": item_id,
            "name": str(raw.get("name", item.get("name", ""))),
            "note": str(raw.get("note", "")),
            "purchased": _as_bool(raw.get("purchased", item.get("purchased", False))),
        })

    suggested_cuts = []
    for raw in args.get("suggested_cuts", []) or []:
        if not isinstance(raw, dict):
            continue
        item_id = str(raw.get("item_id", ""))
        item = item_by_id.get(item_id, {})
        suggested_cuts.append({
            "item_id": item_id,
            "name": str(raw.get("name", item.get("name", ""))),
            "cost": _as_number(raw.get("cost", item.get("cost", 0))),
            "reason": str(raw.get("reason", "")),
            "rank": int(raw.get("rank", 0) or 0),
        })
    suggested_cuts.sort(key=lambda c: c["rank"])

    gaps = []
    for raw in args.get("gaps", []) or []:
        if not isinstance(raw, dict):
            continue
        severity = str(raw.get("severity", "info"))
        if severity not in ("info", "warning"):
            severity = "info"
        gaps.append({
            "description": str(raw.get("description", "")),
            "severity": severity,
        })

    return {
        "overall_assessment": str(args.get("overall_assessment", "")),
        "locked_in": locked_in,
        "suggested_cuts": suggested_cuts,
        "gaps": gaps,
        "coach_note": str(args.get("coach_note", "")),
        "insufficient_data": _as_bool(args.get("insufficient_data"), False),
        "insufficient_data_reason": str(args.get("insufficient_data_reason", "")),
    }


def _fallback_analysis(payload: dict[str, Any], reason: str) -> dict[str, Any]:
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    item_by_id: dict[str, dict[str, Any]] = {}
    for item in items:
        if isinstance(item, dict):
            item_by_id[str(item.get("id", ""))] = item

    locked_in = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("needed_for_comp_day") or item.get("priority_tier") == "MANDATORY":
            locked_in.append({
                "item_id": str(item.get("id", "")),
                "name": str(item.get("name", "")),
                "note": "Marked mandatory; AI analysis unavailable.",
                "purchased": _as_bool(item.get("purchased", False)),
            })

    return {
        "overall_assessment": f"Budget advisor unavailable: {reason}",
        "locked_in": locked_in,
        "suggested_cuts": [],
        "gaps": [],
        "coach_note": "",
        "insufficient_data": True,
        "insufficient_data_reason": reason,
    }


async def generate_budget_advisor(payload: dict[str, Any]) -> dict[str, Any]:
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    item_by_id: dict[str, dict[str, Any]] = {}
    for item in items:
        if isinstance(item, dict):
            item_by_id[str(item.get("id", ""))] = item

    config = payload.get("config") if isinstance(payload.get("config"), dict) else {}
    monthly_cap = _as_number(config.get("monthly_cap"))
    if not items and monthly_cap <= 0:
        return _fallback_analysis(payload, "No budget items and no monthly cap set.")

    user_msg = json.dumps(_sanitize(payload), indent=2, default=str)
    logger.info(
        "[BudgetAdvisorAI] model=%s payload_chars=%s items=%s",
        ANALYSIS_MODEL,
        len(user_msg),
        len(items),
    )

    if not OPENROUTER_API_KEY:
        return _fallback_analysis(payload, "LLM API key not configured.")

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{LLM_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": ANALYSIS_MODEL,
                    "thinking": {"type": "enabled", "budget_tokens": ANALYSIS_MODEL_THINKING_BUDGET},
                    "messages": [
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user", "content": user_msg},
                    ],
                    "tools": [_TOOL_SCHEMA],
                    "tool_choice": "required",
                },
            )
            if resp.status_code >= 400:
                logger.error("[BudgetAdvisorAI] HTTP %s: %s", resp.status_code, resp.text[:2000])
            resp.raise_for_status()
            data = resp.json()

        choices = data.get("choices", [])
        if not choices:
            raise ValueError("No choices in LLM response")
        message = choices[0].get("message", {})
        tool_calls = message.get("tool_calls", [])
        if not tool_calls:
            raise ValueError("No tool calls in LLM response")

        args_str = tool_calls[0].get("function", {}).get("arguments", "{}")
        args = json.loads(args_str)
        return _normalize_analysis(args if isinstance(args, dict) else {}, item_by_id)
    except Exception as exc:
        logger.error("[BudgetAdvisorAI] generation failed: %s", exc)
        return _fallback_analysis(payload, str(exc))
