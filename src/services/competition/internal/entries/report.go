package entries

import (
	"errors"

	"powerlifting/competition/internal/pyval"
)

var lifts = map[string]bool{"squat": true, "bench": true, "deadlift": true}

type position struct {
	lift   string
	number float64
}

type attempts struct {
	order []string
	byID  map[string]map[string]any
}

func newAttempts() *attempts { return &attempts{byID: map[string]map[string]any{}} }

func (a *attempts) put(id string, item map[string]any) {
	if _, exists := a.byID[id]; !exists {
		a.order = append(a.order, id)
	}
	a.byID[id] = item
}

func (a *attempts) list() []any {
	out := make([]any, len(a.order))
	for index, id := range a.order {
		out[index] = a.byID[id]
	}
	return out
}

func attemptID(masterID, lift string, number any) string {
	return masterID + ":" + lift + ":" + pyval.Str(number)
}

func attemptPosition(raw map[string]any) (position, bool) {
	lift, isText := raw["lift"].(string)
	number, isNumber := pyval.Float(raw["attempt_number"])
	if !isText || !isNumber || !lifts[lift] || (number != 1 && number != 2 && number != 3) {
		return position{}, false
	}
	return position{lift: lift, number: number}, true
}

var (
	errInvalidAttempt = errors.New("attempt lift and attempt_number are invalid")
	errImmutable      = errors.New("attempt identity is immutable")
)

func normaliseReport(masterID string, incoming, existing any) (map[string]any, error) {
	report, ok := incoming.(map[string]any)
	if !ok {
		return nil, errors.New("post_meet_report must be an object")
	}
	previous, _ := existing.(map[string]any)
	previousAttempts, _ := previous["attempts"].([]any)
	known := newAttempts()
	byPosition := map[position]string{}
	for _, raw := range previousAttempts {
		object, ok := raw.(map[string]any)
		if !ok {
			continue
		}
		at, valid := attemptPosition(object)
		if !valid {
			continue
		}
		item := pyval.Copy(object).(map[string]any)
		id := pyval.Str(pyval.Or(item["attempt_id"], attemptID(masterID, at.lift, object["attempt_number"])))
		item["attempt_id"] = id
		known.put(id, item)
		byPosition[at] = id
	}

	var incomingAttempts []any
	supplied := report["attempts"] != nil
	if supplied {
		list, ok := report["attempts"].([]any)
		if !ok {
			return nil, errors.New("post_meet_report.attempts must be an array")
		}
		incomingAttempts = list
	}
	seen := map[position]bool{}
	for _, raw := range incomingAttempts {
		object, ok := raw.(map[string]any)
		if !ok {
			return nil, errors.New("post_meet_report.attempts entries must be objects")
		}
		at, valid := attemptPosition(object)
		if !valid {
			return nil, errInvalidAttempt
		}
		if seen[at] {
			return nil, errors.New("duplicate attempt identity")
		}
		seen[at] = true
		existingID := byPosition[at]
		suppliedID := ""
		if pyval.Truthy(object["attempt_id"]) {
			suppliedID = pyval.Str(object["attempt_id"])
		}
		if existingID != "" && suppliedID != "" && suppliedID != existingID {
			return nil, errImmutable
		}
		id := existingID
		if id == "" {
			id = suppliedID
		}
		if id == "" {
			id = attemptID(masterID, at.lift, object["attempt_number"])
		}
		prior := known.byID[id]
		if prior != nil && (!pyval.Equal(prior["lift"], at.lift) || !pyval.Equal(prior["attempt_number"], object["attempt_number"])) {
			return nil, errImmutable
		}
		item := map[string]any{}
		for key, value := range prior {
			item[key] = value
		}
		for key, value := range object {
			item[key] = pyval.Copy(value)
		}
		item["attempt_id"] = id
		known.put(id, item)
		byPosition[at] = id
	}

	merged := pyval.Copy(previous).(map[string]any)
	if merged == nil {
		merged = map[string]any{}
	}
	for key, value := range report {
		merged[key] = pyval.Copy(value)
	}
	if supplied || len(previousAttempts) > 0 {
		merged["attempts"] = known.list()
	}
	return merged, nil
}
