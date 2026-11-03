import asyncio
from pathlib import Path

from openai_codex import AsyncCodex

from .config import load
from .model import CodexModel


async def login() -> None:
    settings = load()
    model = CodexModel(settings.model, settings.effort, settings.state_dir / "scratch")
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
        models = await codex.models()
        if settings.model not in {entry.model for entry in models.data}:
            raise RuntimeError(f"{settings.model} is not available on this subscription")
    print(f"ChatGPT subscription verified; {settings.model} available", flush=True)


if __name__ == "__main__":
    asyncio.run(login())
