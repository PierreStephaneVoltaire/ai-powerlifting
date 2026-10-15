from __future__ import annotations
import logging
from datetime import datetime
from typing import Any, Optional
from services.lib.block_scope import current_block_id
logger = logging.getLogger(__name__)
_store: Optional["ProgramStore"] = None  # type: ignore[name-defined]
def _get_store():
    """Lazily create and return the ProgramStore singleton."""
    import os
    from services.lib.program_store import ProgramStore as _PS
    _store = _PS(
        table_name=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"),
        pk=os.environ.get("HEALTH_PROGRAM_PK", "operator"),
        region=os.environ.get("AWS_REGION", "ca-central-1"),
    )
    logger.info("[HealthTools] ProgramStore initialised from env vars")
    return _store


def _store_for(pk: str | None):
    """Return the ProgramStore singleton, retargeted to pk when provided."""
    store = _get_store()
    if pk:
        store.pk = pk
    return store


def _string_ids(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    deduped: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in deduped:
            deduped.append(text)
    return deduped


async def health_create_competition(args: dict | None = None, competition: dict | None = None) -> dict:
    """Create a new competition entry.

    Args:
        competition: Dict with required fields: name, date (YYYY-MM-DD), federation.
            Optional: federation_id, counts_toward_federation_ids, status
            (default "confirmed"), weight_class_kg, location, targets
            {squat_kg, bench_kg, deadlift_kg, total_kg}, notes.

    Returns:
        The created competition dict

    Raises:
        ValueError: If competition already exists on that date or missing required fields
    """
    import copy
    if competition is None:
        competition = args.get("competition") if isinstance(args, dict) else None
    if not isinstance(competition, dict):
        raise ValueError("competition must be an object")
    pk = args.get("pk") if isinstance(args, dict) else None
    expected_revision = args.get("expected_revision") if isinstance(args, dict) else None
    idempotency_key = args.get("idempotency_key") if isinstance(args, dict) else None
    for field in ("name", "date", "federation"):
        if not competition.get(field):
            raise ValueError(f"competition.{field} is required")

    try:
        datetime.strptime(competition["date"], "%Y-%m-%d")
    except (TypeError, ValueError) as exc:
        raise ValueError("competition.date must be YYYY-MM-DD") from exc

    new_comp = {
        "name": competition["name"],
        "date": competition["date"],
        "federation": competition["federation"],
        "federation_id": competition.get("federation_id"),
        "counts_toward_federation_ids": _string_ids(competition.get("counts_toward_federation_ids")),
        "status": competition.get("status", "confirmed"),
        "weight_class_kg": competition.get("weight_class_kg"),
        "location": competition.get("location"),
        "targets": competition.get("targets", {}),
        "notes": competition.get("notes", ""),
    }
    store = _store_for(pk)

    def mutate(program: dict) -> dict:
        competitions = program.setdefault("competitions", [])
        if any(c.get("date") == new_comp["date"] for c in competitions):
            raise ValueError(f"Competition already exists on {new_comp['date']}")
        new_comp["block_id"] = current_block_id(program)
        competitions.append(copy.deepcopy(new_comp))
        competitions.sort(key=lambda c: c.get("date", ""))
        return copy.deepcopy(new_comp)

    return await store.mutate_source(
        "competition_create",
        {"competition": new_comp},
        expected_revision,
        idempotency_key,
        mutate,
    )
