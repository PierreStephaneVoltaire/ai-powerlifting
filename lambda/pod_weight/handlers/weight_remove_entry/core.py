try:
    from .._weight_store import get_store, resolve
except ImportError:
    from _weight_store import get_store, resolve


async def weight_remove_entry(args: dict) -> dict:
    pk, version = resolve(args)
    date = args.get("date") or ""
    if not date:
        raise ValueError("date is required (YYYY-MM-DD)")
    return await get_store().remove_entry(pk, version, date)
