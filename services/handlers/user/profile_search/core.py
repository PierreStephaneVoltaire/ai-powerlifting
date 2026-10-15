import asyncio


async def profile_search(args: dict) -> dict:
    from services.profile_views import search
    return await asyncio.to_thread(search, args)
