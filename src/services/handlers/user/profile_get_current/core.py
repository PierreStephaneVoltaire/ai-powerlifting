import asyncio


async def profile_get_current(args: dict) -> dict:
    from services.profile_views import get_current
    return await asyncio.to_thread(get_current, args)
