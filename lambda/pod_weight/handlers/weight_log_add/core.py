try:
    from .._weight_store import entry_from, get_store, resolve
except ImportError:
    from _weight_store import entry_from, get_store, resolve


async def weight_log_add(args: dict) -> dict:
    pk, version = resolve(args)
    return await get_store().add_entry(pk, version, entry_from(args))
