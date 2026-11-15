package pyval

import (
	"encoding/json"
	"testing"
)

func TestSanitizeKeepsNegativeFractions(t *testing.T) {
	value := map[string]any{
		"neg": json.Number("-2.5"), "small": json.Number("-0.25"), "whole": json.Number("-3"), "wholeFloat": json.Number("-3.0"),
		"pos": json.Number("2.5"), "list": []any{json.Number("-7.75")},
	}
	got := Sanitize(value).(map[string]any)
	if got["neg"] != -2.5 || got["small"] != -0.25 || got["whole"] != int64(-3) || got["wholeFloat"] != int64(-3) || got["pos"] != 2.5 {
		t.Fatalf("%v", got)
	}
	if got["list"].([]any)[0] != -7.75 {
		t.Fatalf("%v", got["list"])
	}
}

func TestCoerceRendersStoredNumbersAsNumbersNotStrings(t *testing.T) {
	got := Coerce(map[string]any{"squat": json.Number("180"), "bench": json.Number("117.5")}).(map[string]any)
	encoded, _ := json.Marshal(got)
	if string(encoded) != `{"bench":117.5,"squat":180}` {
		t.Fatalf("%s", encoded)
	}
}
