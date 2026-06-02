









from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple

from config import (
    TIER_UPGRADE_THRESHOLD,
    TIER_AIR_LIMIT,
    TIER_STANDARD_LIMIT,
    TIER_HEAVY_LIMIT,
    TIER_AIR_PRESET,
    TIER_STANDARD_PRESET,
    TIER_HEAVY_PRESET,
)

logger = logging.getLogger(__name__)

@dataclass
class PresetTier:








    name: str
    tier: int
    preset: str
    context_limit: int

TIERS: List[PresetTier] = [
    PresetTier(
        name="air",
        tier=0,
        preset=TIER_AIR_PRESET,
        context_limit=TIER_AIR_LIMIT,
    ),
    PresetTier(
        name="standard",
        tier=1,
        preset=TIER_STANDARD_PRESET,
        context_limit=TIER_STANDARD_LIMIT,
    ),
    PresetTier(
        name="heavy",
        tier=2,
        preset=TIER_HEAVY_PRESET,
        context_limit=TIER_HEAVY_LIMIT,
    ),
]

def estimate_context_tokens(
    system_prompt: str,
    messages: List[dict],
    tool_overhead: int = 0
) -> int:












    total_chars = len(system_prompt)

    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total_chars += len(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    total_chars += len(part.get("text", ""))

    text_tokens = total_chars // 4

    message_overhead = len(messages) * 4

    return text_tokens + message_overhead + tool_overhead

def check_tier(
    context_tokens: int,
    current_tier: int
) -> Tuple[bool, Optional[int]]:











    tier_config = get_tier(current_tier)
    if not tier_config:
        return False, None

    threshold_tokens = int(tier_config.context_limit * TIER_UPGRADE_THRESHOLD)

    if context_tokens >= tier_config.context_limit:
        return True, None

    if context_tokens >= threshold_tokens:
        next_tier = get_next_tier(current_tier)
        if next_tier:
            logger.info(
                f"[Tiering] Context at {context_tokens} tokens "
                f"({context_tokens/tier_config.context_limit:.1%} of {tier_config.name} limit), "
                f"suggesting upgrade to {next_tier.name}"
            )
            return False, next_tier.tier

    return False, None

def get_tier(tier: int) -> Optional[PresetTier]:








    for t in TIERS:
        if t.tier == tier:
            return t
    return None

def get_preset_for_tier(tier: int) -> str:








    tier_config = get_tier(tier)
    if tier_config:
        return tier_config.preset
    return TIER_AIR_PRESET

def get_next_tier(current: int) -> Optional[PresetTier]:








    for tier in TIERS:
        if tier.tier == current + 1:
            return tier
    return None

def get_tier_for_context(context_tokens: int) -> int:










    for tier in TIERS:
        if context_tokens <= tier.context_limit:
            return tier.tier

    return TIERS[-1].tier
