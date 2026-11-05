import asyncio
from pathlib import Path

from openai_codex import AsyncCodex

from .config import load
from .model import CodexModel


async def login() -> None:
    settings = load()
    model = CodexModel(settings.state_dir / "scratch", settings.providers)
    cwd = Path(settings.state_dir / "scratch")
    cwd.mkdir(parents=True, exist_ok=True)
    async with AsyncCodex(model._config(cwd)) as codex:
        handle = await codex.login_chatgpt_device_code()
        print(handle.verification_url, flush=True)
        print(handle.user_code, flush=True)
        result = await handle.wait()
        if not result.success:
            raise RuntimeError(result.error or "Subscription login failed")
        await model._check_subscription(codex)
        available = {entry.model for entry in (await codex.models()).data}
        wanted = {ai.model for ai in (settings.conversation_ai, *settings.operation_ai.values()) if settings.providers[ai.provider].subscription}
        if wanted - available:
            raise RuntimeError(f"Not available on this subscription: {', '.join(sorted(wanted - available))}")
    print(f"ChatGPT subscription verified; {', '.join(sorted(wanted))} available", flush=True)


if __name__ == "__main__":
    asyncio.run(login())
