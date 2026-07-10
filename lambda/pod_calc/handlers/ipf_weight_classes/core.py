from __future__ import annotations

from typing import Optional

_store: Optional[object] = None


def ipf_weight_classes(sex: str) -> dict:
    """Get IPF weight classes for the given sex.

    Static data - no network calls.

    Args:
        sex: "M" or "F"

    Returns:
        {
            "sex": "M",
            "classes_kg": [59, 66, 74, 83, 93, 105, 120, "120+"],
            "operator_class_kg": 83  # From program or null
        }

    Raises:
        ValueError: If sex not in ["M", "F"]
    """
    if sex not in ["M", "F"]:
        raise ValueError(f"Invalid sex: {sex}. Must be 'M' or 'F'.")

    CLASSES = {
        "M": [59, 66, 74, 83, 93, 105, 120, "120+"],
        "F": [47, 52, 57, 63, 69, 76, 84, "84+"],
    }

    operator_class_kg = None
    if _store is not None:
        try:
            import asyncio
            loop = asyncio.get_running_loop()
            future = asyncio.ensure_future(_store.get_program())
            try:
                program = loop.run_until_complete(future)
                operator_class_kg = program.get("meta", {}).get("weight_class_kg")
            except:
                pass
        except RuntimeError:
            if _store._cache is not None:
                operator_class_kg = _store._cache.get("meta", {}).get("weight_class_kg")

    return {
        "sex": sex,
        "classes_kg": CLASSES[sex],
        "operator_class_kg": operator_class_kg,
    }
