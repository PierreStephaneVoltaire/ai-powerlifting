




from __future__ import annotations

import contextvars
from typing import Any, Dict, Optional

_platform_ctx: contextvars.ContextVar[Optional[Dict[str, Any]]] = contextvars.ContextVar(
    "platform_ctx", default=None
)

def set_platform_context(platform: str, channel_ref: Any, discord_loop: Any) -> None:
    _platform_ctx.set({"platform": platform, "channel_ref": channel_ref, "discord_loop": discord_loop})

def get_platform_context() -> Optional[Dict[str, Any]]:
    return _platform_ctx.get()

def clear_platform_context() -> None:
    _platform_ctx.set(None)
