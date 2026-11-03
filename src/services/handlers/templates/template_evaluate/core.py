import asyncio
import os
from datetime import date
from typing import Optional

from .metrics import strip_calendar, template_metrics

_program_store: Optional[object] = None
_template_store: Optional[object] = None

LIFT_PROFILE_FIELDS = ("lift", "style", "primary_muscle", "sticking_points", "stance", "grip", "bar_position", "notes", "stimulus")


def _lift_profiles(program):
    return [{key: value for key, value in profile.items() if key in LIFT_PROFILE_FIELDS} for profile in program.get("lift_profiles") or []]


def _timeline(program, template_weeks):
    from services.lib.competition_entries import next_competition
    meta = program.get("meta") or {}
    fallback = [{"date": meta.get("comp_date"), "status": "confirmed"}] if meta.get("comp_date") else []
    competition = next_competition(program.get("competitions") or []) or next_competition(fallback)
    if not competition:
        return {"template_weeks": template_weeks, "next_confirmed_competition": None}
    competition_date = date.fromisoformat(str(competition.get("date") or competition.get("start_date"))[:10])
    weeks_away = round((competition_date - date.today()).days / 7, 1)
    return {
        "template_weeks": template_weeks,
        "next_confirmed_competition": {"name": competition.get("name"), "weeks_away": weeks_away},
        "weeks_until_template_must_start": round(weeks_away - template_weeks, 1),
    }


def _athlete_context(program, template_weeks=0):
    return {
        "current_maxes": program.get("current_maxes") or {},
        "lift_profiles": _lift_profiles(program),
        "timeline": _timeline(program, template_weeks),
    }


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


def _get_glossary(args):
    from services.lib.glossary_store import GlossaryStore
    return GlossaryStore(os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"), pk=args["pk"], region=os.environ.get("AWS_REGION", "ca-central-1")).get_glossary_sync()


def _specificity_band():
    from services.handlers.analysis_reports.analytics import _specificity_expected_band
    return _specificity_expected_band


async def _dispatch(args):
    from .template_evaluate_ai import generate_template_evaluate_report
    from services.lib.competition_entries import with_competition_entries
    sk = args["sk"]
    actor_pk = args.get("actor_pk") or args.get("pk")
    template = await _get_template_store().get_template(sk, actor_pk=actor_pk)
    if not template:
        raise ValueError(f"Template not found: {sk}")
    context = args.get("context")
    if context is None:
        context = (template.get("meta") or {}).get("program_context") or ""
    program = await _get_program_store(args).get_program()
    program = await asyncio.to_thread(with_competition_entries, program, args["pk"])
    glossary = await asyncio.to_thread(_get_glossary, args)
    metrics = template_metrics(template, glossary, program.get("current_maxes") or {}, _specificity_band())
    stripped = strip_calendar(template)
    stripped["meta"]["program_context"] = context
    report = await generate_template_evaluate_report(stripped, _athlete_context(program, metrics.get("weeks", 0)), metrics, context)
    await _get_template_store().set_evaluation(sk, report, actor_pk=actor_pk, program_context=context)
    return report


def template_evaluate(args):
    return asyncio.run(_dispatch(args))
