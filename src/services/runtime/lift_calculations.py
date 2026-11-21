import json
import math
from pathlib import Path

_DATA = json.loads((Path(__file__).resolve().parent / "calculation_constants.json").read_text())
RPE_PERCENT = _DATA["rpe_percent"]
DOTS_COEFFICIENTS = _DATA["dots_coefficients"]
IPF_GL_COEFFICIENTS = _DATA["ipf_gl_coefficients"]


def estimate_set_e1rm(weight_kg, reps, rpe=None):
    if not isinstance(weight_kg, (int, float)) or not math.isfinite(weight_kg) or weight_kg <= 0:
        return None
    if not isinstance(reps, (int, float)) or not 1 <= reps <= 10 or int(reps) != reps:
        return None
    if rpe is not None and (not isinstance(rpe, (int, float)) or not 6 <= rpe <= 10):
        return None
    percent = RPE_PERCENT.get(f"{int(reps)}-{10 if rpe is None else int(rpe)}")
    return round(weight_kg / percent, 1) if percent else None


def calculate_ipf_gl(total_kg, bodyweight_kg, sex, mode):
    coefficients = IPF_GL_COEFFICIENTS.get(mode, {}).get(sex)
    if not coefficients or total_kg <= 0 or bodyweight_kg <= 0:
        return None
    denominator = coefficients["a"] - coefficients["b"] * math.exp(-coefficients["c"] * bodyweight_kg)
    return round(100 * total_kg / denominator, 2) if abs(denominator) >= 1e-12 else None


def calculate_dots(total_kg, bodyweight_kg, sex):
    if sex.lower() not in DOTS_COEFFICIENTS:
        raise ValueError("Expected male or female")
    total, weight = float(total_kg), float(bodyweight_kg)
    if not math.isfinite(total) or not math.isfinite(weight) or total < 0 or weight <= 0:
        raise ValueError("Expected nonnegative total and positive bodyweight")
    coefficients = DOTS_COEFFICIENTS[sex.lower()]
    denominator = sum(coefficients[key] * weight ** power for power, key in enumerate("abcde"))
    return round(500 * total / denominator, 2) if abs(denominator) >= 1e-12 else 0.0
