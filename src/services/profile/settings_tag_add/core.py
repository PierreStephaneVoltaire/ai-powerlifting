import asyncio
from services.runtime.tag_catalog import select


async def settings_tag_add(args: dict) -> dict:
    return await asyncio.to_thread(lambda: select(args))
