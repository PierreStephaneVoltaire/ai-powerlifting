package profile

import (
	"encoding/json"
	"slices"
	"strings"
)

type Option struct {
	Value string `json:"value"`
	Label string `json:"label"`
}

type Field struct {
	Key     string             `json:"key"`
	Label   string             `json:"label"`
	Options []Option           `json:"options"`
	Legacy  map[string]*string `json:"legacy"`
	Locked  *struct {
		When  map[string]string `json:"when"`
		Value string            `json:"value"`
	} `json:"locked"`
}

type Definitions map[string][]Field

func Parse(data []byte) (Definitions, error) {
	var definitions Definitions
	err := json.Unmarshal(data, &definitions)
	return definitions, err
}

func (d Definitions) Options(lift string, input map[string]any) map[string]any {
	result := map[string]any{}
	for _, field := range d[lift] {
		value, _ := input[field.Key].(string)
		value = strings.TrimSpace(value)
		if migrated, ok := field.Legacy[value]; ok {
			value = ""
			if migrated != nil {
				value = *migrated
			}
		}
		for _, option := range field.Options {
			if value == option.Value {
				result[field.Key] = value
				break
			}
		}
	}
	for _, field := range d[lift] {
		if field.Locked == nil {
			continue
		}
		matches := true
		for key, value := range field.Locked.When {
			if result[key] != value {
				matches = false
				break
			}
		}
		if matches {
			result[field.Key] = field.Locked.Value
		}
	}
	return result
}

func (d Definitions) Clean(input map[string]any) map[string]any {
	lift, _ := input["lift"].(string)
	if lift != "squat" && lift != "bench" && lift != "deadlift" {
		return nil
	}
	result := make(map[string]any, len(input)+3)
	for key, value := range input {
		result[key] = value
	}
	options, _ := input["options"].(map[string]any)
	result["options"] = d.Options(lift, options)
	tolerance, _ := input["volume_tolerance"].(string)
	tolerance = strings.TrimSpace(tolerance)
	if tolerance != "low" && tolerance != "moderate" && tolerance != "high" {
		tolerance = "moderate"
	}
	result["volume_tolerance"] = tolerance
	notes, _ := input["notes"].(string)
	runes := []rune(strings.TrimSpace(notes))
	if len(runes) > 1000 {
		runes = runes[:1000]
	}
	result["notes"] = string(runes)
	return result
}

func (d Definitions) Missing(input map[string]any) []string {
	lift, _ := input["lift"].(string)
	options, _ := input["options"].(map[string]any)
	missing := []string{}
	for _, field := range d[lift] {
		if options[field.Key] == nil || options[field.Key] == "" {
			missing = append(missing, field.Label)
		}
	}
	return missing
}

func (d Definitions) Describe(input map[string]any) map[string]any {
	lift, _ := input["lift"].(string)
	options, _ := input["options"].(map[string]any)
	technique := map[string]any{}
	for _, field := range d[lift] {
		for _, option := range field.Options {
			if options[field.Key] == option.Value {
				technique[field.Label] = option.Label
				break
			}
		}
	}
	tolerance, _ := input["volume_tolerance"].(string)
	if tolerance == "" {
		tolerance = "moderate"
	}
	result := map[string]any{"lift": lift, "technique": technique, "volume_tolerance": tolerance}
	if notes, ok := input["notes"].(string); ok && notes != "" {
		result["notes"] = notes
	}
	return result
}

func (d Definitions) Suggest(lift string, current map[string]any, answer map[string]any) map[string]any {
	selected := d.Options(lift, current)
	merged := make(map[string]any, len(selected)+len(answer))
	for key, value := range selected {
		merged[key] = value
	}
	for key, value := range answer {
		if value, ok := value.(string); ok && value != "" {
			merged[key] = value
		}
	}
	suggested := d.Options(lift, merged)
	changed := []string{}
	for key, value := range suggested {
		if selected[key] != value {
			changed = append(changed, key)
		}
	}
	slices.Sort(changed)
	var tolerance any
	if value, ok := answer["volume_tolerance"].(string); ok && (value == "low" || value == "moderate" || value == "high") {
		tolerance = value
	}
	return map[string]any{"lift": lift, "options": suggested, "volume_tolerance": tolerance, "changed": changed}
}

func (d Definitions) SuggestSchema(lift string) map[string]any {
	properties := map[string]any{}
	required := []string{}
	for _, field := range d[lift] {
		values := make([]any, 0, len(field.Options)+1)
		for _, option := range field.Options {
			values = append(values, option.Value)
		}
		values = append(values, nil)
		properties[field.Key] = map[string]any{"type": []any{"string", "null"}, "enum": values, "description": field.Label}
		required = append(required, field.Key)
	}
	properties["volume_tolerance"] = map[string]any{"type": []any{"string", "null"}, "enum": []any{"low", "moderate", "high", nil}}
	required = append(required, "volume_tolerance")
	return map[string]any{"type": "function", "function": map[string]any{
		"name":        "select_lift_profile_options",
		"description": "Select the " + lift + " technique options that match the lifter's description. Use null when the description does not say.",
		"parameters":  map[string]any{"type": "object", "properties": properties, "required": required},
	}}
}

func (d Definitions) Normalize(profiles []any, existing []any) []any {
	videos := map[string]any{}
	for _, raw := range existing {
		item, ok := raw.(map[string]any)
		if !ok {
			continue
		}
		lift, _ := item["lift"].(string)
		if lift == "squat" || lift == "bench" || lift == "deadlift" {
			videos[lift] = item["form_videos"]
		}
	}
	result := make([]any, 0, len(profiles))
	for _, raw := range profiles {
		item, ok := raw.(map[string]any)
		if !ok {
			continue
		}
		clean := d.Clean(item)
		if clean == nil {
			continue
		}
		lift := clean["lift"].(string)
		if value, ok := videos[lift]; ok {
			clean["form_videos"] = value
		} else {
			delete(clean, "form_videos")
		}
		result = append(result, clean)
	}
	return result
}
