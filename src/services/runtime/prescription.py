import math
from decimal import Decimal


def is_timed(exercise):
    return exercise.get("rep_unit") in ("minutes", "seconds") or exercise.get("duration_minutes") is not None


def normalize_prescription(exercise):
    mode = exercise.get("rep_mode")
    unit = exercise.get("rep_unit")
    legacy = exercise.get("duration_minutes")
    if mode not in (None, "amrap"):
        raise ValueError("Unknown template rep mode")
    if unit not in (None, "reps", "minutes", "seconds"):
        raise ValueError("Unknown prescription unit")
    if legacy is not None:
        if isinstance(legacy, str):
            try:
                legacy = float(legacy)
            except ValueError:
                legacy = None
        if isinstance(legacy, bool) or not isinstance(legacy, (int, float, Decimal)) or not math.isfinite(legacy) or legacy <= 0:
            raise ValueError("Duration must be a positive number")
        quantity = exercise.get("reps")
        if unit in (None, "reps"):
            if quantity is not None:
                raise ValueError("A legacy timed prescription cannot also prescribe reps")
            exercise["reps"] = legacy
            exercise["rep_unit"] = unit = "minutes"
        elif quantity is None or not math.isclose(float(quantity) / (60 if unit == "seconds" else 1), float(legacy)):
            raise ValueError("Timed prescription units disagree")
        exercise.pop("duration_minutes", None)
    if mode and (is_timed(exercise) or exercise.get("reps") is not None):
        raise ValueError("AMRAP requires an open rep count")
    if is_timed(exercise):
        value = exercise.get("reps")
        if isinstance(value, str):
            try:
                value = float(value)
            except ValueError:
                value = None
        if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)) or not math.isfinite(value) or value <= 0:
            raise ValueError("Duration must be a positive number")
        exercise["reps"] = value
        if exercise.get("load_type") in (None, "", "unresolvable"):
            rpe = exercise.get("rpe_target")
            if rpe is not None:
                exercise["load_type"] = "rpe"
                exercise["load_value"] = rpe
            else:
                exercise["load_type"] = "duration"
    elif exercise.get("load_type") == "duration":
        raise ValueError("Duration load type requires a timed unit")
    return exercise
