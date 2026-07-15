def lb_to_kg(lb: float) -> dict:
    """Convert pounds to kilograms.

    Args:
        lb: Weight in pounds

    Returns:
        {"lb": lb, "kg": rounded_kg}

    Raises:
        ValueError: If lb <= 0
    """
    if lb <= 0:
        raise ValueError("lb must be positive")

    kg = round(lb / 2.20462, 2)
    return {"lb": lb, "kg": kg}
