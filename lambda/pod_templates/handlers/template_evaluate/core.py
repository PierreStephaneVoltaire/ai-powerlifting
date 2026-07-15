import asyncio
import os
from typing import Optional

_program_store: Optional[object] = None
_template_store: Optional[object] = None


def _get_program_store():
    global _program_store
    if _program_store is None:
        from program_store import ProgramStore
        _program_store = ProgramStore(
            table_name=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"),
            pk=os.environ.get("HEALTH_PROGRAM_PK", "operator"),
            region=os.environ.get("AWS_REGION", "ca-central-1"),
        )
    return _program_store


def _get_template_store():
    global _template_store
    if _template_store is None:
        from template_store import TemplateStore
        _template_store = TemplateStore(
            table_name=os.environ.get("IF_TEMPLATES_TABLE_NAME", "if-health-templates"),
            pk=os.environ.get("IF_TEMPLATES_LIBRARY_PK", "template_library"),
            region=os.environ.get("AWS_REGION", "ca-central-1"),
        )
    return _template_store


async def _dispatch(args):
    from template_evaluate_ai import generate_template_evaluate_report
    sk = args["sk"]
    actor_pk = args.get("actor_pk") or args.get("pk")
    template = await _get_template_store().get_template(sk, actor_pk=actor_pk)
    if not template:
        raise ValueError(f"Template not found: {sk}")
    program = await _get_program_store().get_program()
    athlete_context = {
        "current_maxes": program.get("current_maxes", {}),
        "dots_score": 350,
        "weeks_to_comp": 12,
    }
    report = await generate_template_evaluate_report(template, athlete_context)
    if isinstance(template, dict) and isinstance(template.get("meta"), dict):
        template["meta"]["ai_evaluation"] = report
    return report


def template_evaluate(args):
    return asyncio.run(_dispatch(args))
