package liftprofile

import (
	_ "embed"
	"encoding/json"
	"strings"
)

//go:embed lift_profile_options.json
var optionsJSON []byte

type option struct {
	Value string `json:"value"`
	Label string `json:"label"`
}

type field struct {
	Key     string   `json:"key"`
	Label   string   `json:"label"`
	Options []option `json:"options"`
}

var definitions map[string][]field

func init() {
	if err := json.Unmarshal(optionsJSON, &definitions); err != nil {
		panic(err)
	}
}

func TechniqueText(lift string, options map[string]any) string {
	var parts []string
	for _, definition := range definitions[lift] {
		value, _ := options[definition.Key].(string)
		for _, candidate := range definition.Options {
			if candidate.Value == value && options[definition.Key] != nil {
				parts = append(parts, definition.Label+": "+candidate.Label)
				break
			}
		}
	}
	return strings.Join(parts, "; ")
}
