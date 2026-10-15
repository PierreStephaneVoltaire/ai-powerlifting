try:
    from .._weight_store import get_store, resolve
except ImportError:
    from services.handlers.weight_log._weight_store import get_store, resolve


async def weight_get_log(args: dict) -> dict:
    pk, version = resolve(args)
    return await get_store().get_log(pk, version, args.get("block_id"))
