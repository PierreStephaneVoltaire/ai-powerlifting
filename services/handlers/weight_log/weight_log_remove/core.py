try:
    from .._weight_store import get_store, resolve
except ImportError:
    from services.handlers.weight_log._weight_store import get_store, resolve


async def weight_log_remove(args: dict) -> dict:
    pk, version = resolve(args)
    date = args.get("date") or ""
    if not date:
        raise ValueError("date is required (YYYY-MM-DD)")
    return await get_store().remove_entry(pk, version, date)
