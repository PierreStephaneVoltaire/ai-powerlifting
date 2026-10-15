import asyncio
from services.tag_catalog import select


async def settings_tag_propose(args: dict) -> dict:
    return await asyncio.to_thread(lambda: select(args))
