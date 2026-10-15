import json
import math
from pathlib import Path

_DATA = json.loads((Path(__file__).resolve().parents[1] / "calculation_constants.json").read_text())
RPE_PERCENT = _DATA["rpe_percent"]
CONSERVATIVE_PERCENT = _DATA["conservative_percent"]
DOTS_COEFFICIENTS = _DATA["dots_coefficients"]


def estimate_1rm_value(weight_kg, reps, rpe=None):
    weight = float(weight_kg)
    pct = None
    if math.isfinite(weight) and weight > 0 and float(reps).is_integer():
        if rpe is not None and 1 <= reps <= 6 and 6 <= float(rpe) <= 10:
            pct = RPE_PERCENT.get(f"{int(reps)}-{int(rpe)}")
        elif rpe is None and 1 <= reps <= 5:
            pct = CONSERVATIVE_PERCENT.get(str(int(reps)))
    return weight / pct if pct else None


def estimate_1rm(weight_kg, reps, rpe=None):
    weight = float(weight_kg)
    value = estimate_1rm_value(weight, reps, rpe)
    method = "rpe_table" if value is not None and rpe is not None else "conservative" if value is not None else None
    rounded = round(value, 1) if value is not None else None
    return {"e1rm": rounded, "method": method, "input_weight_kg": round(weight, 1), "epley": None, "brzycki": None, "rpe_based": rounded if method == "rpe_table" else None}


def calculate_dots(total_kg, bodyweight_kg, sex):
    if sex.lower() not in DOTS_COEFFICIENTS:
        raise ValueError("Expected male or female")
    total, weight = float(total_kg), float(bodyweight_kg)
    if not math.isfinite(total) or not math.isfinite(weight) or total < 0 or weight <= 0:
        raise ValueError("Expected nonnegative total and positive bodyweight")
    coefficients = DOTS_COEFFICIENTS[sex.lower()]
    denominator = sum(coefficients[key] * weight ** power for power, key in enumerate("abcde"))
    return round(500 * total / denominator, 2) if abs(denominator) >= 1e-12 else 0.0
