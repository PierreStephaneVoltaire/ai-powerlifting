import asyncio
import os
import sys

from .discord_api import Discord


async def register(guild_id: str) -> None:
    discord = Discord(os.environ["DISCORD_TOKEN"])
    application = await discord.application()
    for command in await discord.register_commands(application.application_id, guild_id):
        print(f"registered /{command['name']} ({command['id']})", flush=True)


if __name__ == "__main__":
    asyncio.run(register(sys.argv[1] if len(sys.argv) > 1 else ""))
