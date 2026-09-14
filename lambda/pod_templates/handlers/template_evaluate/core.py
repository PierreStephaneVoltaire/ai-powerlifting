import asyncio
import os
from datetime import date
from typing import Optional

_program_store: Optional[object] = None
_template_store: Optional[object] = None


def _athlete_context(program):
    meta = program.get("meta") or {}
    maxes = program.get("current_maxes") or {}
    values = [maxes.get(lift) for lift in ("squat", "bench", "deadlift")]
    try:
        total = sum(float(value) for value in values)
        bodyweight = float(meta.get("current_body_weight_kg"))
        sex = {"m": "male", "male": "male", "f": "female", "female": "female"}.get(str(meta.get("sex") or "").lower())
        from lift_calculations import calculate_dots
        dots_score = calculate_dots(total, bodyweight, sex) if sex else None
    except (TypeError, ValueError):
        dots_score = None
    try:
        weeks_to_comp = round((date.fromisoformat(meta["comp_date"]) - date.today()).days / 7, 1)
    except (KeyError, TypeError, ValueError):
        weeks_to_comp = None
    return {"current_maxes": maxes, "dots_score": dots_score, "weeks_to_comp": weeks_to_comp}


def _get_program_store(args):
    from program_store import ProgramStore
    _program_store = ProgramStore(
        table_name=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"),
        pk=args["pk"],
        region=os.environ.get("AWS_REGION", "ca-central-1"),
    )
    return _program_store


def _get_template_store():
    from template_store import TemplateStore
    _template_store = TemplateStore(
        table_name=os.environ.get("IF_TEMPLATES_TABLE_NAME", "if-health-templates"),
        pk=os.environ.get("IF_TEMPLATES_LIBRARY_PK", "template_library"),
        region=os.environ.get("AWS_REGION", "ca-central-1"),
    )
    return _template_store


async def _dispatch(args):
    from .template_evaluate_ai import generate_template_evaluate_report
    sk = args["sk"]
    actor_pk = args.get("actor_pk") or args.get("pk")
    template = await _get_template_store().get_template(sk, actor_pk=actor_pk)
    if not template:
        raise ValueError(f"Template not found: {sk}")
    program = await _get_program_store(args).get_program()
    athlete_context = _athlete_context(program)
    report = await generate_template_evaluate_report(template, athlete_context)
    if isinstance(template, dict) and isinstance(template.get("meta"), dict):
        template["meta"]["ai_evaluation"] = report
    return report


def template_evaluate(args):
    return asyncio.run(_dispatch(args))
