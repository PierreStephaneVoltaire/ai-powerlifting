from __future__ import annotations
import logging
from datetime import datetime
from typing import Any, Optional
logger = logging.getLogger(__name__)
_store: Optional["ProgramStore"] = None  # type: ignore[name-defined]
def _get_store():
    """Lazily create and return the ProgramStore singleton."""
    global _store
    if _store is None:
        import os
        from program_store import ProgramStore as _PS
        _store = _PS(
            table_name=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"),
            pk=os.environ.get("HEALTH_PROGRAM_PK", "operator"),
            region=os.environ.get("AWS_REGION", "ca-central-1"),
        )
        logger.info("[HealthTools] ProgramStore initialised from env vars")
    return _store


def _string_ids(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    deduped: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in deduped:
            deduped.append(text)
    return deduped


async def health_create_competition(competition: dict) -> dict:
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
    for field in ("name", "date", "federation"):
        if not competition.get(field):
            raise ValueError(f"competition.{field} is required")

    datetime.strptime(competition["date"], "%Y-%m-%d")

    store = _get_store()
    program = await store.get_program()
    new_program = copy.deepcopy(program)

    competitions = new_program.setdefault("competitions", [])
    if any(c.get("date") == competition["date"] for c in competitions):
        raise ValueError(f"Competition already exists on {competition['date']}")

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
    competitions.append(new_comp)
    competitions.sort(key=lambda c: c.get("date", ""))

    await store._write_new_version(new_program, minor=True)
    return new_comp