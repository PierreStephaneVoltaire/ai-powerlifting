package payload

import (
	"encoding/json"
	"errors"
	"math"
	"strconv"
)

func positiveNumber(value any) (float64, bool) {
	var n float64
	switch v := value.(type) {
	case float64:
		n = v
	case float32:
		n = float64(v)
	case int:
		n = float64(v)
	case int64:
		n = float64(v)
	case json.Number:
		var err error
		n, err = v.Float64()
		if err != nil {
			return 0, false
		}
	case string:
		var err error
		n, err = strconv.ParseFloat(v, 64)
		if err != nil {
			return 0, false
		}
	default:
		return 0, false
	}
	return n, n > 0 && !math.IsNaN(n) && !math.IsInf(n, 0)
}

func NormalizePrescription(exercise map[string]any) error {
	mode := text(exercise["rep_mode"])
	unit := text(exercise["rep_unit"])
	if mode != "" && mode != "amrap" {
		return errors.New("Unknown template rep mode")
	}
	if unit != "" && unit != "reps" && unit != "minutes" && unit != "seconds" {
		return errors.New("Unknown prescription unit")
	}
	if legacy := exercise["duration_minutes"]; legacy != nil {
		minutes, ok := positiveNumber(legacy)
		if !ok {
			return errors.New("Duration must be a positive number")
		}
		quantity := exercise["reps"]
		if unit == "" || unit == "reps" {
			if quantity != nil {
				return errors.New("A legacy timed prescription cannot also prescribe reps")
			}
			exercise["reps"] = minutes
			unit = "minutes"
			exercise["rep_unit"] = unit
		} else {
			duration, ok := positiveNumber(quantity)
			if !ok {
				return errors.New("Timed prescription units disagree")
			}
			if unit == "seconds" {
				duration /= 60
			}
			if math.Abs(duration-minutes) > 1e-9*math.Max(math.Abs(duration), math.Abs(minutes)) {
				return errors.New("Timed prescription units disagree")
			}
		}
		delete(exercise, "duration_minutes")
	}
	timed := unit == "minutes" || unit == "seconds"
	if mode == "amrap" && (timed || exercise["reps"] != nil) {
		return errors.New("AMRAP requires an open rep count")
	}
	if timed {
		quantity, ok := positiveNumber(exercise["reps"])
		if !ok {
			return errors.New("Duration must be a positive number")
		}
		exercise["reps"] = quantity
		loadType := text(exercise["load_type"])
		if loadType == "" || loadType == "unresolvable" {
			if rpe := exercise["rpe_target"]; rpe != nil {
				exercise["load_type"] = "rpe"
				exercise["load_value"] = rpe
			} else {
				exercise["load_type"] = "duration"
			}
		}
	} else if text(exercise["load_type"]) == "duration" {
		return errors.New("Duration load type requires a timed unit")
	}
	return nil
}
