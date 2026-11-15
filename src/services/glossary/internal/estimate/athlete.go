package estimate

import (
	_ "embed"
	"encoding/json"
	"fmt"
	"strings"
)

//go:embed lift_profile_options.json
var optionsJSON []byte

var options map[string][]struct {
	Key     string `json:"key"`
	Label   string `json:"label"`
	Options []struct {
		Value string `json:"value"`
		Label string `json:"label"`
	} `json:"options"`
}

func init() {
	if err := json.Unmarshal(optionsJSON, &options); err != nil {
		panic(err)
	}
}

var bodyFatLabels = map[string]string{
	"under_10": "Under 10%", "10_15": "10 to 15%", "15_20": "15 to 20%",
	"20_25": "20 to 25%", "25_30": "25 to 30%", "over_30": "Over 30%",
}

type Athlete struct {
	Meta         map[string]any
	LiftProfiles []map[string]any
}

func (a Athlete) metricLines() []string {
	bodyFat, _ := a.Meta["body_fat_range"].(string)
	fields := []struct {
		label string
		value any
	}{
		{"bodyweight_kg", a.Meta["current_body_weight_kg"]},
		{"height_cm", a.Meta["height_cm"]},
		{"arm_wingspan_cm", a.Meta["arm_wingspan_cm"]},
		{"leg_length_cm", a.Meta["leg_length_cm"]},
		{"body_fat_range", bodyFatLabels[bodyFat]},
		{"sex", a.Meta["sex"]},
	}
	lines := []string{}
	for _, field := range fields {
		if value, ok := field.value.(float64); ok && value == 0 {
			continue
		}
		if field.value == nil || field.value == "" {
			continue
		}
		lines = append(lines, fmt.Sprintf("  %s: %v", field.label, field.value))
	}
	if len(lines) == 0 {
		return nil
	}
	return append([]string{"Athlete metrics:"}, lines...)
}

func lift(profile map[string]any) string {
	text, _ := profile["lift"].(string)
	return strings.ToLower(strings.TrimSpace(text))
}

func techniqueLines(profile map[string]any) []string {
	selected, _ := profile["options"].(map[string]any)
	var lines []string
	for _, field := range options[lift(profile)] {
		value, _ := selected[field.Key].(string)
		for _, option := range field.Options {
			if option.Value == value {
				lines = append(lines, field.Label+": "+option.Label)
			}
		}
	}
	tolerance, _ := profile["volume_tolerance"].(string)
	if tolerance == "" {
		tolerance = "moderate"
	}
	lines = append(lines, "Volume tolerance: "+tolerance)
	if notes, _ := profile["notes"].(string); notes != "" {
		lines = append(lines, "Notes: "+notes)
	}
	return lines
}

func profileLines(profile map[string]any) []string {
	label, _ := profile["lift"].(string)
	if label == "" {
		label = "?"
	}
	lines := []string{"Lift profile (" + label + "):"}
	for _, line := range techniqueLines(profile) {
		lines = append(lines, "  "+line)
	}
	return lines
}

func (a Athlete) lines() []string {
	lines := a.metricLines()
	for _, profile := range a.LiftProfiles {
		if len(lines) > 0 {
			lines = append(lines, "")
		}
		lines = append(lines, profileLines(profile)...)
	}
	return lines
}
