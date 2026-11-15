package exercise

import (
	"reflect"
	"strings"
)

type Item = map[string]any

const (
	GenericPending = "pending"
	GenericReady   = "ready"
	GenericFailed  = "failed"
)

var (
	textFields       = []string{"description", "how_to_perform", "why_do_it"}
	muscleFields     = []string{"primary_muscles", "secondary_muscles", "tertiary_muscles"}
	definitionFields = []string{"name", "category", "fatigue_category", "equipment", "video_url", "lift_transfer"}
	personalFields   = []string{"fatigue_profile", "fatigue_profile_source", "fatigue_profile_reasoning", "e1rm_estimate", "archived"}
)

func NameKey(name string) string {
	return strings.Join(strings.Fields(strings.ToLower(name)), " ")
}

func Text(item Item, key string) string {
	value, _ := item[key].(string)
	return value
}

func Strings(item Item, key string) []string {
	values, _ := item[key].([]any)
	out := make([]string, 0, len(values))
	for _, value := range values {
		if text, ok := value.(string); ok {
			out = append(out, text)
		}
	}
	return out
}

func isEmpty(value any) bool {
	switch typed := value.(type) {
	case nil:
		return true
	case string:
		return typed == ""
	case []any:
		return len(typed) == 0
	case map[string]any:
		return len(typed) == 0
	}
	return false
}

func Clean(payload Item) Item {
	cleaned := Item{}
	for _, key := range textFields {
		if value, present := payload[key]; present {
			text, _ := value.(string)
			cleaned[key] = strings.TrimSpace(text)
		}
	}
	for _, key := range muscleFields {
		if value, present := payload[key]; present {
			muscles, isList := value.([]any)
			if !isList {
				muscles = []any{}
			}
			cleaned[key] = muscles
		}
	}
	for _, key := range definitionFields {
		value, present := payload[key]
		if !present {
			continue
		}
		if text, isText := value.(string); isText {
			value = strings.TrimSpace(text)
		}
		if !isEmpty(value) || key == "name" {
			cleaned[key] = value
		}
	}
	for _, key := range personalFields {
		if value, present := payload[key]; present && value != nil {
			cleaned[key] = value
		}
	}
	return cleaned
}

func Diff(effective, cleaned Item, skipEmpty bool) Item {
	changed := Item{}
	for key, value := range cleaned {
		if skipEmpty && isEmpty(value) {
			continue
		}
		current, present := effective[key]
		if !present && isEmpty(value) {
			continue
		}
		if !reflect.DeepEqual(current, value) {
			changed[key] = value
		}
	}
	return changed
}

func Definition(effective Item) Item {
	definition := Item{"id": effective["id"], "name_key": NameKey(Text(effective, "name"))}
	for _, key := range append(append([]string{}, definitionFields...), append(textFields, muscleFields...)...) {
		if value, present := effective[key]; present {
			definition[key] = value
		}
	}
	return definition
}

func Merge(catalog, overlay Item) Item {
	effective := Item{}
	fields := append(append(append([]string{}, definitionFields...), textFields...), muscleFields...)
	for _, key := range fields {
		for _, source := range []Item{catalog, overlay} {
			if value, present := source[key]; present {
				effective[key] = value
			}
		}
	}
	for _, key := range personalFields {
		if value, present := overlay[key]; present {
			effective[key] = value
		}
	}
	if id, present := overlay["id"]; present {
		effective["id"] = id
	} else if id, present := catalog["id"]; present {
		effective["id"] = id
	}
	if value, present := overlay["custom"]; present {
		effective["custom"] = value
	}
	if catalog != nil {
		if status, present := catalog["generic_status"]; present {
			effective["generic_status"] = status
		}
		if generic, present := catalog["fatigue_profile"]; present {
			effective["generic_fatigue_profile"] = generic
			if _, personal := overlay["fatigue_profile"]; !personal {
				effective["fatigue_profile"] = generic
				for _, key := range []string{"fatigue_profile_source", "fatigue_profile_reasoning"} {
					if value, present := catalog[key]; present {
						effective[key] = value
					}
				}
			}
		}
	}
	_, personal := overlay["fatigue_profile"]
	effective["fatigue_profile_personalized"] = personal
	return effective
}
