import asyncio
import os

from .metrics import strip_calendar, template_metrics


def _lift_profiles(program):
    from services.runtime.lift_profiles import describe
    return [describe(profile) for profile in program.get("lift_profiles") or []]


def _athlete_context(program):
    return {
        "current_maxes": program.get("current_maxes") or {},
        "lift_profiles": _lift_profiles(program),
    }


def _get_program_store(args):
    from services.runtime.program_store import ProgramStore
    _program_store = ProgramStore(
        table_name=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"),
        pk=args["pk"],
        region=os.environ.get("AWS_REGION", "ca-central-1"),
    )
    return _program_store


def _get_template_store():
    from services.runtime.template_store import TemplateStore
    _template_store = TemplateStore(
        table_name=os.environ.get("IF_TEMPLATES_TABLE_NAME", "if-health-templates"),
        pk=os.environ.get("IF_TEMPLATES_LIBRARY_PK", "template_library"),
        region=os.environ.get("AWS_REGION", "ca-central-1"),
    )
    return _template_store


def _get_glossary(args):
    from services.runtime.glossary_store import GlossaryStore
    return GlossaryStore(os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"), pk=args["pk"], region=os.environ.get("AWS_REGION", "ca-central-1")).get_glossary_sync()


def template_actor(args):
    return args.get("actor_pk") or args.get("_person_pk") or args.get("pk")


async def load_report(args):
    sk = args["sk"]
    actor_pk = template_actor(args)
    template = await _get_template_store().get_template(sk, actor_pk=actor_pk)
    if not template:
        raise ValueError(f"Template not found: {sk}")
    program = await _get_program_store(args).get_program()
    glossary = await asyncio.to_thread(_get_glossary, args)
    metrics = await asyncio.to_thread(template_metrics, template, glossary, program.get("current_maxes") or {}, program.get("lift_profiles") or [])
    return template, program, metrics


async def _dispatch(args):
    from .template_evaluate_ai import generate_template_evaluate_report
    sk = args["sk"]
    actor_pk = template_actor(args)
    template, program, metrics = await load_report(args)
    context = args.get("context")
    if context is None:
        context = (template.get("meta") or {}).get("program_context") or ""
    stripped = strip_calendar(template)
    stripped["meta"]["program_context"] = context
    report = await generate_template_evaluate_report(stripped, _athlete_context(program), metrics, context)
    await _get_template_store().set_evaluation(sk, report, actor_pk=actor_pk, program_context=context)
    return report


def template_evaluate(args):
    return asyncio.run(_dispatch(args))
