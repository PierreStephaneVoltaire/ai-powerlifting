import asyncio
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

_program_store: Optional[object] = None
_glossary_store: Optional[object] = None


def _get_program_store():
    global _program_store
    if _program_store is None:
        from program_store import ProgramStore as _PS
        _program_store = _PS(
            table_name=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"),
            pk=os.environ.get("HEALTH_PROGRAM_PK", "operator"),
            region=os.environ.get("AWS_REGION", "ca-central-1"),
        )
    return _program_store


def _get_glossary_store():
    global _glossary_store
    if _glossary_store is None:
        from glossary_store import GlossaryStore as _GS
        _glossary_store = _GS(
            table_name=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"),
            pk=os.environ.get("HEALTH_PROGRAM_PK", "operator"),
            region=os.environ.get("AWS_REGION", "ca-central-1"),
        )
    return _glossary_store


async def _dispatch(args):
    from .e1rm_backfill_ai import generate_e1rm_backfill_report
    exercise_id = args["id"]
    glossary = await _get_glossary_store().get_glossary()
    ex = next((e for e in glossary if e["id"] == exercise_id), None)
    if not ex:
        raise ValueError(f"Exercise not found: {exercise_id}")
    program = await _get_program_store().get_program()
    current_maxes = program.get("current_maxes", {})
    lift_profiles = program.get("lift_profiles", [])
    past_instances = {}
    for s in program.get("sessions", []):
        if not (s.get("completed") or s.get("status") in ("logged", "completed")):
            continue
        for ex_item in s.get("exercises", []):
            name = ex_item.get("name")
            if not name:
                continue
            if name not in past_instances:
                past_instances[name] = []
            past_instances[name].append(
                {
                    "date": s.get("date"),
                    "sets": ex_item.get("sets"),
                    "reps": ex_item.get("reps"),
                    "kg": ex_item.get("kg"),
                    "rpe": ex_item.get("rpe", ex_item.get("rpe_target")),
                    "notes": ex_item.get("notes"),
                }
            )
    report = await generate_e1rm_backfill_report(
        [ex["name"]],
        current_maxes,
        lift_profiles=lift_profiles,
        past_instances=past_instances,
    )
    estimates = report.get("estimates", [])
    if not estimates:
        return {"status": "error", "message": "AI failed to generate estimate"}
    est = estimates[0]
    await _get_glossary_store().set_e1rm(
        exercise_id,
        est["e1rm_kg"],
        method="ai_backfill",
        basis=est["basis"],
        confidence="low",
        manually_overridden=False,
    )
    return {"status": "estimated", "id": exercise_id, "estimate": est}


def glossary_estimate_e1rm(args):
    return asyncio.run(_dispatch(args))
