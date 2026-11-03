def kg_to_lb(kg: float) -> dict:
    """Convert kilograms to pounds.

    Args:
        kg: Weight in kilograms

    Returns:
        {"kg": kg, "lb": rounded_pounds}

    Raises:
        ValueError: If kg <= 0
    """
    if kg <= 0:
        raise ValueError("kg must be positive")

    lb = round(kg * 2.20462, 1)
    return {"kg": kg, "lb": lb}
