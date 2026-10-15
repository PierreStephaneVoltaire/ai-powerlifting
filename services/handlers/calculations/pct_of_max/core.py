def pct_of_max(max_kg: float, pct: float) -> dict:
    """Calculate percentage of max weight.

    Args:
        max_kg: Maximum weight in kg
        pct: Percentage (0-150, not 0-1)

    Returns:
        {
            "max_kg": 185.0,
            "pct": 85.0,
            "raw_kg": 157.25,
            "rounded_2_5_kg": 157.5,
            "lb": 347.2
        }

    Raises:
        ValueError: If max_kg <= 0 or pct not in (0, 150]
    """
    if max_kg <= 0:
        raise ValueError("max_kg must be positive")
    if not (0 < pct <= 150):
        raise ValueError("pct must be in range (0, 150]")

    raw_kg = max_kg * (pct / 100)
    rounded_2_5_kg = round(raw_kg / 2.5) * 2.5
    lb = round(raw_kg * 2.20462, 1)

    return {
        "max_kg": max_kg,
        "pct": pct,
        "raw_kg": round(raw_kg, 2),
        "rounded_2_5_kg": rounded_2_5_kg,
        "lb": lb,
    }
