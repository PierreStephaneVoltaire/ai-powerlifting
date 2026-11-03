import asyncio
from services.tag_catalog import decide


async def settings_tag_approve(args: dict) -> dict:
    return await asyncio.to_thread(lambda: decide(args))
