package pyval

import (
	"encoding/json"
	"testing"
)

func TestTruthinessFollowsPython(t *testing.T) {
	falsy := []any{nil, false, "", json.Number("0"), json.Number("0.0"), 0.0, 0, []any{}, map[string]any{}}
	truthy := []any{true, "x", json.Number("1"), 0.5, []any{nil}, map[string]any{"a": nil}}
	for _, value := range falsy {
		if Truthy(value) {
			t.Errorf("%#v should be falsy", value)
		}
	}
	for _, value := range truthy {
		if !Truthy(value) {
			t.Errorf("%#v should be truthy", value)
		}
	}
}

func TestStrMatchesPythonStr(t *testing.T) {
	cases := map[string]any{
		"None": nil, "True": true, "160": json.Number("160"), "157.5": json.Number("157.5"), "70.0": json.Number("70.0"),
		"100.0": json.Number("1e2"), "1.0": 1.0, "2.5": 2.5, "7": 7, "abc": "abc",
	}
	for want, input := range cases {
		if got := Str(input); got != want {
			t.Errorf("%#v: got %q want %q", input, got, want)
		}
	}
}

func TestOrReturnsTheFirstTruthyValue(t *testing.T) {
	if Or(nil, "", "x", "y") != "x" || Or(nil, "") != "" || Or() != nil {
		t.Fatal("Or does not behave like Python's or chain")
	}
}

func TestEqualComparesNumbersAcrossRepresentations(t *testing.T) {
	if !Equal(json.Number("1"), 1.0) || !Equal(1.0, json.Number("1.0")) || Equal(json.Number("1"), "1") || !Equal("a", "a") || Equal("a", "b") || !Equal(nil, nil) {
		t.Fatal("Equal")
	}
}

func TestCopyIsDeep(t *testing.T) {
	original := map[string]any{"a": []any{map[string]any{"b": 1}}}
	copied := Copy(original).(map[string]any)
	copied["a"].([]any)[0].(map[string]any)["b"] = 2
	if original["a"].([]any)[0].(map[string]any)["b"] != 1 {
		t.Fatal("copy shares state")
	}
}

func TestNumberKeepsIntegersIntegral(t *testing.T) {
	if Number(20) != json.Number("20") || Number(2.5) != 2.5 {
		t.Fatal("Number")
	}
}
