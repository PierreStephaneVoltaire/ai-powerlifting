
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from typing import Any

def _load_args() -> tuple[str, dict[str, Any]]:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python -m flow.runtime_tool <tool_name> [json_args]")
    tool_name = sys.argv[1]
    raw_args = sys.argv[2] if len(sys.argv) > 2 else "{}"
    args = json.loads(raw_args)
    if not isinstance(args, dict):
        raise SystemExit("json_args must be a JSON object")
    return tool_name, args

def _print(value: Any) -> int:
    print(json.dumps(value, indent=2, default=str))
    return 0

def _user_facts_search(args: dict[str, Any]) -> list[dict[str, Any]]:
    from memory.user_facts import FactCategory, get_user_fact_store

    context_id = str(args.get("context_id") or "")
    query = str(args.get("query") or "")
    if not context_id or not query:
        raise ValueError("context_id and query are required")
    category_raw = args.get("category")
    category = FactCategory(category_raw) if category_raw else None
    facts = get_user_fact_store().search(
        context_id=context_id,
        query=query,
        category=category,
        limit=int(args.get("limit") or 5),
    )
    return [fact.to_dict() for fact in facts]

def _user_facts_add(args: dict[str, Any]) -> dict[str, Any]:
    from memory.user_facts import FactCategory, FactSource, get_user_fact_store

    context_id = str(args.get("context_id") or "")
    content = str(args.get("content") or "")
    if not context_id or not content:
        raise ValueError("context_id and content are required")
    fact_id = get_user_fact_store().add(
        context_id=context_id,
        content=content,
        category=FactCategory(str(args.get("category") or "personal")),
        source=FactSource(str(args.get("source") or "user_stated")),
        username=str(args.get("username") or "operator"),
        confidence=float(args.get("confidence") or 0.8),
        cache_key=str(args.get("cache_key") or ""),
        metadata=args.get("metadata") if isinstance(args.get("metadata"), dict) else None,
    )
    return {"ok": True, "fact_id": fact_id}

def _user_facts_supersede(args: dict[str, Any]) -> dict[str, Any]:
    from memory.user_facts import get_user_fact_store

    context_id = str(args.get("context_id") or "")
    old_fact_id = str(args.get("old_fact_id") or "")
    new_content = str(args.get("new_content") or "")
    reason = str(args.get("reason") or "updated by opencode runtime")
    if not context_id or not old_fact_id or not new_content:
        raise ValueError("context_id, old_fact_id, and new_content are required")
    fact = get_user_fact_store().supersede(
        context_id=context_id,
        old_fact_id=old_fact_id,
        new_content=new_content,
        reason=reason,
        cache_key=str(args.get("cache_key") or ""),
    )
    return {"ok": True, "fact": fact.to_dict() if fact else None}

def _capability_gap_log(args: dict[str, Any]) -> dict[str, Any]:
    from config import REFLECTION_CONTEXT_ID
    from memory.user_facts import get_user_fact_store

    source_context_id = str(args.get("context_id") or "")
    content = str(args.get("content") or "")
    if not content:
        raise ValueError("content is required")
    trigger_context = str(args.get("trigger_context") or source_context_id or args.get("cache_key") or "")
    if args.get("suggested_tool") or args.get("acceptance_criteria"):
        trigger_context = (
            f"{trigger_context}\n"
            f"suggested_tool={args.get('suggested_tool') or ''}\n"
            f"acceptance_criteria={args.get('acceptance_criteria') or []}"
        ).strip()

    fact_id = get_user_fact_store().log_capability_gap(
        context_id=REFLECTION_CONTEXT_ID,
        content=content,
        trigger_context=trigger_context,
        cache_key=str(args.get("cache_key") or ""),
        workaround=args.get("workaround"),
    )
    return {
        "ok": True,
        "gap_id": fact_id,
        "reflection_context_id": REFLECTION_CONTEXT_ID,
        "source_context_id": source_context_id,
        "logged_at": datetime.now(timezone.utc).isoformat(),
    }

def main() -> int:
    tool_name, args = _load_args()
    tools = {
        "user_facts_search": _user_facts_search,
        "user_facts_add": _user_facts_add,
        "user_facts_supersede": _user_facts_supersede,
        "capability_gap_log": _capability_gap_log,
    }
    fn = tools.get(tool_name)
    if fn is None:
        raise SystemExit(f"Unknown runtime tool: {tool_name}")
    try:
        return _print(fn(args))
    except Exception as exc:
        return _print({"ok": False, "error": f"{type(exc).__name__}: {exc}"})

if __name__ == "__main__":
    raise SystemExit(main())
