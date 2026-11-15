package pyval

import (
	"encoding/json"
	"testing"
)

func TestDecimalStr(t *testing.T) {
	cases := map[string]string{"180": "180", "182.5": "182.5", "0.0000001": "1E-7", "0.000001": "0.000001", "100000": "100000", "-2.50": "-2.50", "1E+2": "1E+2"}
	for in, want := range cases {
		if got := DecimalStr(json.Number(in)); got != want {
			t.Errorf("%s: got %s want %s", in, got, want)
		}
	}
}

func TestFloatRepr(t *testing.T) {
	cases := map[float64]string{180: "180.0", 82.5: "82.5", 1e-5: "1e-05", 1e22: "1e+22", 0.1: "0.1", 123456789012345678: "1.2345678901234568e+17"}
	for in, want := range cases {
		if got := FloatRepr(in); got != want {
			t.Errorf("%v: got %s want %s", in, got, want)
		}
	}
}

func TestSanitizeAndCoerce(t *testing.T) {
	value := map[string]any{"a": json.Number("100"), "b": json.Number("2.5"), "c": json.Number("-2.5")}
	sanitized := Sanitize(value).(map[string]any)
	if sanitized["a"] != int64(100) || sanitized["b"] != 2.5 || sanitized["c"] != -2.5 {
		t.Fatalf("%v", sanitized)
	}
	coerced := Coerce(value).(map[string]any)
	if coerced["c"] != -2.5 {
		t.Fatalf("%v", coerced)
	}
}

func TestNormalize(t *testing.T) {
	if Normalize("100.0") != "100" || Normalize("0.10") != "0.1" || Normalize("1E+2") != "100" {
		t.Fatal("normalize")
	}
}
