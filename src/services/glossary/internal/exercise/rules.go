package exercise

import (
	_ "embed"
	"encoding/json"
	"regexp"
	"strconv"
	"strings"
)

//go:embed lift_transfer_rules.json
var rulesJSON []byte

var nameLift = regexp.MustCompile(`\b(squat|bench|deadlift)\b`)

type nameRule struct {
	ID      string  `json:"id"`
	Pattern string  `json:"pattern"`
	Lift    string  `json:"lift"`
	Value   float64 `json:"value"`
	matcher *regexp.Regexp
}

var rules struct {
	NameRules         []*nameRule        `json:"name_rules"`
	CategoryVariation map[string]float64 `json:"category_variation"`
	Isolation         struct {
		PrimaryValue   float64             `json:"primary_value"`
		SecondaryValue float64             `json:"secondary_value"`
		MuscleLifts    map[string][]string `json:"muscle_lifts"`
	} `json:"isolation"`
}

func init() {
	if err := json.Unmarshal(rulesJSON, &rules); err != nil {
		panic(err)
	}
	for _, rule := range rules.NameRules {
		rule.matcher = regexp.MustCompile(rule.Pattern)
	}
}

func number(value float64) string {
	text := strconv.FormatFloat(value, 'f', -1, 64)
	if !strings.Contains(text, ".") {
		text += ".0"
	}
	return text
}

func transfer(values map[string]float64, reasoning string) Item {
	return Item{"squat": values["squat"], "bench": values["bench"], "deadlift": values["deadlift"], "source": "rule", "reasoning": reasoning}
}

func RuleLiftTransfer(exercise Item) Item {
	name := NameKey(Text(exercise, "name"))
	inName := nameLift.FindString(name)
	for _, rule := range rules.NameRules {
		if !rule.matcher.MatchString(name) {
			continue
		}
		lift := rule.Lift
		if lift == "$name" {
			lift = inName
		}
		if lift == "" {
			continue
		}
		return transfer(map[string]float64{lift: rule.Value}, "Rule "+rule.ID+": "+lift+" "+number(rule.Value))
	}
	category := strings.ToLower(Text(exercise, "category"))
	if value, ok := rules.CategoryVariation[category]; ok {
		return transfer(map[string]float64{category: value}, "Rule category_variation: "+category+" "+number(value))
	}
	values := map[string]float64{}
	for _, tier := range []struct {
		field string
		value float64
	}{{"secondary_muscles", rules.Isolation.SecondaryValue}, {"primary_muscles", rules.Isolation.PrimaryValue}} {
		for _, muscle := range Strings(exercise, tier.field) {
			for _, lift := range rules.Isolation.MuscleLifts[muscle] {
				values[lift] = max(values[lift], tier.value)
			}
		}
	}
	return transfer(values, "Rule isolation: muscle-based default capped at "+number(rules.Isolation.PrimaryValue))
}
