import asyncio

from services.templates.template_evaluate.core import load_report


async def _dispatch(args):
    template, _, metrics = await load_report(args)
    meta = template.get("meta") or {}
    return {
        "sk": args["sk"],
        "name": meta.get("name"),
        "program_context": meta.get("program_context") or "",
        "evaluation": meta.get("ai_evaluation"),
        "metrics": metrics,
    }


def template_report(args):
    return asyncio.run(_dispatch(args))
