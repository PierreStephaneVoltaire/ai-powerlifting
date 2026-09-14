from __future__ import annotations

from .._shared.settings_normalize import derive_onboarding_status
from ..settings_get.core import settings_get


async def onboarding_status(args: dict) -> dict:
    return derive_onboarding_status(await settings_get(args))
