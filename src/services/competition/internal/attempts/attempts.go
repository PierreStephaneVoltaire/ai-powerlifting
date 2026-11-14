package attempts

import (
	"encoding/json"
	"math"

	"powerlifting/competition/internal/pyval"
)

type Request struct {
	Lift       string
	Opener     any
	J1Override any
	J2Override any
	LastFelt   string
}

type Preferences struct {
	Jumps map[string]any
	Maxes map[string]any
}

func PreferencesFrom(program map[string]any) Preferences {
	prefs, _ := program["operator_prefs"].(map[string]any)
	jumps, _ := prefs["attempt_jumps"].(map[string]any)
	maxes, _ := program["current_maxes"].(map[string]any)
	return Preferences{Jumps: jumps, Maxes: maxes}
}

func toPlate(value float64) float64 { return math.RoundToEven(value/2.5) * 2.5 }

func asNumber(value any, fallback float64) (any, float64) {
	if parsed, ok := pyval.Float(value); ok {
		return pyval.Number(parsed), parsed
	}
	return pyval.Number(fallback), fallback
}

func Calculate(request Request, prefs Preferences) map[string]any {
	liftJumps, _ := prefs.Jumps[request.Lift].(map[string]any)
	j1Raw, j1 := jump(request.J1Override, liftJumps, "j1")
	j2Raw, j2 := jump(request.J2Override, liftJumps, "j2")
	if request.LastFelt == "hard" {
		j2 = toPlate(j2 / 2)
		j2Raw = j2
	}
	opener, _ := pyval.Float(request.Opener)
	second := toPlate(opener + j1)
	third := toPlate(second + j2)

	warnings := []any{}
	if raw, present := prefs.Maxes[request.Lift]; present && pyval.Truthy(raw) {
		currentMax, _ := pyval.Float(raw)
		currentText := pyval.Str(pyval.Number(currentMax))
		minOpener := currentMax * 0.7
		if opener < minOpener {
			warnings = append(warnings, "Opener "+pyval.Str(request.Opener)+"kg is below 70% of current max ("+currentText+"kg). Consider an opener of at least "+pyval.Str(toPlate(minOpener))+"kg.")
		}
		if third > currentMax {
			warnings = append(warnings, "Attempt 3 ("+pyval.Str(third)+"kg) exceeds current max of "+currentText+"kg — confirm this is a target PR.")
		}
	}
	return map[string]any{
		"lift":         request.Lift,
		"attempt_1_kg": request.Opener,
		"attempt_2_kg": second,
		"attempt_3_kg": third,
		"jumps_used":   map[string]any{"j1": j1Raw, "j2": j2Raw},
		"warnings":     warnings,
	}
}

func jump(override any, stored map[string]any, name string) (any, float64) {
	if override != nil {
		parsed, _ := pyval.Float(override)
		return override, parsed
	}
	if value, present := stored[name]; present {
		return asNumber(value, 10)
	}
	return json.Number("10"), 10
}
