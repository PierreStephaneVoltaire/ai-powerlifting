import asyncio
import os

from services.handlers.templates.template_evaluate.core import _get_template_store, template_actor
from services.lib.template_patch import Resolver, apply_operations, patch_hash


def _resolver(args: dict) -> Resolver:
    from services.lib.glossary_store import GlossaryStore
    store = GlossaryStore(os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"), pk=args["pk"], region=os.environ.get("AWS_REGION", "ca-central-1"))
    by_id = {str(entry.get("id")): entry for entry in store.get_glossary_sync() if entry.get("id")}
    cache: dict[str, dict | None] = {}

    def resolve(name: str) -> dict | None:
        if name not in cache:
            entry_id = store.fuzzy_resolve_sync(name)
            cache[name] = by_id.get(str(entry_id)) if entry_id else None
        return cache[name]

    return resolve


async def _dispatch(args: dict) -> dict:
    sk = args["sk"]
    actor_pk = template_actor(args)
    operations = args.get("operations") or []
    store = _get_template_store()
    template = await store.get_template(sk, actor_pk=actor_pk)
    if not template:
        raise ValueError(f"Template not found: {sk}")
    resolve = await asyncio.to_thread(_resolver, args)
    patched, changes, unmatched = await asyncio.to_thread(apply_operations, template, operations, resolve)
    applied = bool(args.get("apply")) and bool(changes)
    if applied:
        await store.update_template(sk, patched, actor_pk=actor_pk)
    return {"sk": sk, "applied": applied, "preview_hash": patch_hash(sk, operations), "changes": changes, "unmatched": unmatched}


def template_patch(args: dict) -> dict:
    return asyncio.run(_dispatch(args))
