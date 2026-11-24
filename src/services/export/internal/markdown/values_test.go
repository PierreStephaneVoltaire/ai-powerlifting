package markdown

import (
	"encoding/json"
	"testing"
)

func TestNumbersFormatTheSameWhateverTheirSource(t *testing.T) {
	cases := []struct {
		name  string
		value any
		want  string
	}{
		{"stored_whole", json.Number("220"), "220"},
		{"stored_whole_with_fraction_digits", json.Number("220.0"), "220"},
		{"stored_fraction", json.Number("117.5"), "117.5"},
		{"stored_negative_fraction", json.Number("-2.5"), "-2.5"},
		{"session_whole", int64(220), "220"},
		{"session_fraction", 117.5, "117.5"},
		{"weight_log_negative_fraction", -0.5, "-0.5"},
	}
	for _, c := range cases {
		if got := tcell(c.value); got != c.want {
			t.Errorf("%s: tcell %q want %q", c.name, got, c.want)
		}
		if got := txt(c.value); got != c.want {
			t.Errorf("%s: txt %q want %q", c.name, got, c.want)
		}
	}
}
