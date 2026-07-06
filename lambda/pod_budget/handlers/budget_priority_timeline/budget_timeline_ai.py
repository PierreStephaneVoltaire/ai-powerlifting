"""LLM-powered budget priority timeline for powerlifting equipment, supplements,
memberships, and competition fees.

Stateless: receives the user's budget config, items, competitions, and federation
membership state from the caller and returns a purchase timeline that adheres to
the monthly cap while prioritising competition deadlines.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from ai_config import LLM_BASE_URL, OPENROUTER_API_KEY, ANALYSIS_MODEL, ANALYSIS_MODEL_THINKING_BUDGET
from prompts.loader import load_system_prompt

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = load_system_prompt("budget_timeline_system")

_ENTRY_OBJECT = {
    "type": "object",
    "properties": {
        "item_id": {"type": "string"},
        "name": {"type": "string"},
        "category": {
            "type": "string",
            "enum": ["equipment", "supplement", "gym_membership", "federation_membership", "competition_entry"],
        },
        "priority": {"type": "string", "enum": ["buy_now", "buy_later", "optional", "drop"]},
        "suggested_month": {"type": "string", "description": "YYYY-MM"},
        "cost": {"type": "number"},
        "reason": {"type": "string"},
    },
    "required": ["item_id", "name", "category", "priority", "suggested_month", "cost", "reason"],
}

_MONTH_OBJECT = {
    "type": "object",
    "properties": {
        "month": {"type": "string", "description": "YYYY-MM"},
        "due": {"type": "number"},
        "budget": {"type": "number"},
        "remaining": {"type": "number"},
        "entries": {"type": "array", "items": _ENTRY_OBJECT},
    },
    "required": ["month", "due", "budget", "remaining", "entries"],
}

_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "submit_budget_timeline",
        "description": "Return a powerlifting budget purchase timeline that stays under the monthly cap and prioritises competitions.",
        "parameters": {
            "type": "object",
            "properties": {
                "months": {"type": "array", "items": _MONTH_OBJECT},
                "notes": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["months", "notes"],
        },
    },
}

_VALID_CATEGORIES = {"equipment", "supplement", "gym_membership", "federation_membership", "competition_entry"}
_VALID_PRIORITIES = {"buy_now", "buy_later", "optional", "drop"}


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


def _default_timeline(reason: str) -> dict[str, Any]:
    return {
        "months": [],
        "notes": [reason] if reason else [],
        "insufficient_data": True,
        "insufficient_data_reason": reason,
    }


def _normalize_entry(raw: Any, item_by_id: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    item_id = str(raw.get("item_id", "")).strip()
    item = item_by_id.get(item_id, {})
    name = str(raw.get("name") or item.get("name") or "").strip()
    category = str(raw.get("category") or item.get("category") or "equipment")
    if category not in _VALID_CATEGORIES:
        category = "equipment"
    priority = str(raw.get("priority") or item.get("priority") or "optional")
    if priority not in _VALID_PRIORITIES:
        priority = "optional"
    suggested_month = str(raw.get("suggested_month") or item.get("start_month") or "").strip()
    cost = _as_number(raw.get("cost"), _as_number(item.get("cost")))
    reason = str(raw.get("reason") or "").strip()
    return {
        "item_id": item_id,
        "name": name,
        "category": category,
        "priority": priority,
        "suggested_month": suggested_month,
        "cost": cost,
        "reason": reason,
    }


def _normalize_timeline(args: dict[str, Any], item_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    months_raw = args.get("months") if isinstance(args.get("months"), list) else []
    months: list[dict[str, Any]] = []
    for raw_month in months_raw:
        if not isinstance(raw_month, dict):
            continue
        entries: list[dict[str, Any]] = []
        for raw_entry in raw_month.get("entries", []) if isinstance(raw_month.get("entries"), list) else []:
            norm = _normalize_entry(raw_entry, item_by_id)
            if norm is not None:
                entries.append(norm)
        month = str(raw_month.get("month", "")).strip()
        if not month:
            continue
        due = _as_number(raw_month.get("due"))
        if due == 0.0 and entries:
            due = sum(_as_number(e.get("cost")) for e in entries)
        budget = _as_number(raw_month.get("budget"))
        months.append({
            "month": month,
            "due": due,
            "budget": budget,
            "remaining": budget - due,
            "entries": entries,
        })
    months.sort(key=lambda m: m["month"])
    notes = args.get("notes") if isinstance(args.get("notes"), list) else []
    notes = [str(n).strip() for n in notes if str(n).strip()]
    return {"months": months, "notes": notes, "insufficient_data": False, "insufficient_data_reason": ""}


def _fallback_timeline(payload: dict[str, Any]) -> dict[str, Any]:
    """Deterministic fallback: place each unpurchased item on its start_date,
    grouped by month (YYYY-MM), without LLM reasoning."""
    config = payload.get("config") if isinstance(payload.get("config"), dict) else {}
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    budget = _as_number(config.get("monthly_budget"))

    by_month: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        if not isinstance(item, dict) or item.get("purchased"):
            continue
        start_date = str(item.get("start_date") or "").strip()
        if not start_date:
            continue
        month = start_date[:7]
        by_month.setdefault(month, []).append({
            "item_id": str(item.get("id", "")),
            "name": str(item.get("name", "")),
            "category": str(item.get("category", "equipment")),
            "priority": str(item.get("priority", "optional")) if item.get("priority") else "optional",
            "suggested_date": start_date,
            "cost": _as_number(item.get("cost")),
            "reason": "Scheduled on its configured start date (AI unavailable).",
        })

    months = []
    for month in sorted(by_month):
        entries = by_month[month]
        due = sum(_as_number(e.get("cost")) for e in entries)
        months.append({
            "month": month,
            "due": due,
            "budget": budget,
            "remaining": budget - due,
            "entries": entries,
        })
    return {
        "months": months,
        "notes": ["AI timeline generation unavailable; items placed on their configured start dates."],
        "insufficient_data": False,
        "insufficient_data_reason": "",
    }



async def generate_budget_timeline(payload: dict[str, Any]) -> dict[str, Any]:
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    item_by_id: dict[str, dict[str, Any]] = {}
    unpurchased = []
    for item in items:
        if not isinstance(item, dict):
            continue
        item_by_id[str(item.get("id", ""))] = item
        if not item.get("purchased"):
            unpurchased.append(item)

    if not unpurchased:
        return _default_timeline("No unpurchased budget items to schedule.")

    user_msg = json.dumps(_sanitize(payload), indent=2, default=str)
    logger.info("[BudgetTimelineAI] model=%s payload_chars=%s items=%s", ANALYSIS_MODEL, len(user_msg), len(unpurchased))

    if not OPENROUTER_API_KEY:
        return _fallback_timeline(payload)

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
                logger.error("[BudgetTimelineAI] HTTP %s: %s", resp.status_code, resp.text[:2000])
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
        return _normalize_timeline(args if isinstance(args, dict) else {}, item_by_id)
    except Exception as exc:
        logger.error("[BudgetTimelineAI] generation failed: %s", exc)
        return _fallback_timeline(payload)
