try:
    from .._weight_store import get_store, resolve
except ImportError:
    from _weight_store import get_store, resolve


async def weight_log_get(args: dict) -> dict:
    pk, version = resolve(args)
    return await get_store().get_log(pk, version)
