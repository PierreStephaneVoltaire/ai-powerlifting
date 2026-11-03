from __future__ import annotations

import asyncio
import os
from decimal import Decimal

from .._shared.settings_normalize import derive_onboarding_status
from ..settings_get.core import settings_get


def existing_basics(settings: dict) -> dict:
    athlete = settings.get('mapped_pk') or settings.get('pk')
    if not athlete:
        return {}
    from services.access_store import database
    table = database().Table(os.getenv('IF_HEALTH_TABLE_NAME', 'if-health'))
    pointer = table.get_item(Key={'pk': athlete, 'sk': 'program#current'}, ConsistentRead=True).get('Item') or {}
    if not pointer.get('ref_sk'):
        return {}
    program = table.get_item(Key={'pk': athlete, 'sk': pointer['ref_sk']}, ConsistentRead=True).get('Item') or {}
    meta = program.get('meta') or {}
    maxes = meta.get('manual_maxes') or program.get('current_maxes') or {}
    result = {'training_maxes': {f'{lift}_kg': float(maxes[lift]) for lift in ('squat', 'bench', 'deadlift') if isinstance(maxes.get(lift), (int, float, Decimal)) and not isinstance(maxes[lift], bool) and maxes[lift] > 0}}
    bodyweight = meta.get('current_body_weight_kg')
    if isinstance(bodyweight, (int, float, Decimal)) and bodyweight > 0:
        result['bodyweight_kg'] = float(bodyweight)
    return result


async def onboarding_status(args: dict) -> dict:
    settings = await settings_get(args)
    status = derive_onboarding_status(settings)
    if not status['has_athlete_basics']:
        status['prefill'] = await asyncio.to_thread(existing_basics, settings)
    return status
