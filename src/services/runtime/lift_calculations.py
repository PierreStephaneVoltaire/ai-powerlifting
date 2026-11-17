import json
import math
from pathlib import Path

_DATA = json.loads((Path(__file__).resolve().parent / "calculation_constants.json").read_text())
RPE_PERCENT = _DATA["rpe_percent"]
DOTS_COEFFICIENTS = _DATA["dots_coefficients"]


def calculate_dots(total_kg, bodyweight_kg, sex):
    if sex.lower() not in DOTS_COEFFICIENTS:
        raise ValueError("Expected male or female")
    total, weight = float(total_kg), float(bodyweight_kg)
    if not math.isfinite(total) or not math.isfinite(weight) or total < 0 or weight <= 0:
        raise ValueError("Expected nonnegative total and positive bodyweight")
    coefficients = DOTS_COEFFICIENTS[sex.lower()]
    denominator = sum(coefficients[key] * weight ** power for power, key in enumerate("abcde"))
    return round(500 * total / denominator, 2) if abs(denominator) >= 1e-12 else 0.0
