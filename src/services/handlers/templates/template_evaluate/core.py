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
        from services.lib.lift_calculations import calculate_dots
        dots_score = calculate_dots(total, bodyweight, sex) if sex else None
    except (TypeError, ValueError):
        dots_score = None
    from services.lib.competition_entries import next_competition
    fallback = [{"date": meta.get("comp_date"), "status": "confirmed"}] if meta.get("comp_date") else []
    competition = next_competition(program.get("competitions") or []) or next_competition(fallback)
    if competition:
        competition_date = date.fromisoformat(str(competition.get("date") or competition.get("start_date"))[:10])
        weeks_to_comp = round((competition_date - date.today()).days / 7, 1)
        next_comp = {"name": competition.get("name"), "date": competition_date.isoformat(), "status": competition.get("status")}
    else:
        weeks_to_comp = None
        next_comp = None
    return {"current_maxes": maxes, "dots_score": dots_score, "weeks_to_comp": weeks_to_comp, "next_competition": next_comp}


def _get_program_store(args):
    from services.lib.program_store import ProgramStore
    _program_store = ProgramStore(
        table_name=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"),
        pk=args["pk"],
        region=os.environ.get("AWS_REGION", "ca-central-1"),
    )
    return _program_store


def _get_template_store():
    from services.lib.template_store import TemplateStore
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
    from services.lib.competition_entries import with_competition_entries
    program = await _get_program_store(args).get_program()
    program = await asyncio.to_thread(with_competition_entries, program, args["pk"])
    athlete_context = _athlete_context(program)
    report = await generate_template_evaluate_report(template, athlete_context)
    await _get_template_store().set_evaluation(sk, report, actor_pk=actor_pk)
    return report


def template_evaluate(args):
    return asyncio.run(_dispatch(args))
