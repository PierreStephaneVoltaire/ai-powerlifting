from __future__ import annotations




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

    return {
        "sex": sex,
        "classes_kg": CLASSES[sex],
        "operator_class_kg": operator_class_kg,
    }
