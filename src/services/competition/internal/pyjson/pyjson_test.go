package pyjson

import (
	"encoding/json"
	"testing"
)

func TestFloatMatchesPythonRepr(t *testing.T) {
	cases := map[float64]string{
		1: "1.0", 0.1: "0.1", 100: "100.0", 1e16: "1e+16", 1e15: "1000000000000000.0", 1e-5: "1e-05",
		0.0001: "0.0001", 2.5e20: "2.5e+20", 123456789.125: "123456789.125", 1500: "1500.0", 3.14159265358979: "3.14159265358979",
		1.2345678901234568e17: "1.2345678901234568e+17", -2.5: "-2.5",
	}
	for input, want := range cases {
		if got := Float(input); got != want {
			t.Errorf("Float(%v) = %s, want %s", input, got, want)
		}
	}
}

func TestEncodeMatchesPythonDumps(t *testing.T) {
	input := "{\"b\": [1, 1.0, -0, \"\xc3\xa9\xe2\x98\x83\xf0\x9f\x98\x80\x7f\"], \"a\": {\"z\": null, \"y\": true}, \"n\": 1E3}"
	value, err := Decode([]byte(input))
	if err != nil {
		t.Fatal(err)
	}
	got, err := Encode(value)
	if err != nil {
		t.Fatal(err)
	}
	want := "{\"a\": {\"y\": true, \"z\": null}, \"b\": [1, 1.0, 0, \"\\u00e9\\u2603\\ud83d\\ude00\\u007f\"], \"n\": 1000.0}"
	if string(got) != want {
		t.Fatalf("got %s want %s", got, want)
	}
}

func TestDecodeRejectsTrailingData(t *testing.T) {
	if _, err := Decode([]byte(`{} {}`)); err == nil {
		t.Fatal("expected error")
	}
}

func TestCompactStyleMatchesStarletteResponses(t *testing.T) {
	encoded, err := EncodeCompact(map[string]any{"b": []any{1.0, "é", json.Number("2")}, "a": nil, "c": "line\u007f\n"})
	if err != nil {
		t.Fatal(err)
	}
	if want := "{\"a\":null,\"b\":[1.0,\"é\",2],\"c\":\"line\u007f\\n\"}"; string(encoded) != want {
		t.Fatalf("got %s want %s", encoded, want)
	}
	spaced, err := Encode(map[string]any{"a": []any{"é\u007f"}})
	if err != nil {
		t.Fatal(err)
	}
	if want := `{"a": ["\u00e9\u007f"]}`; string(spaced) != want {
		t.Fatalf("got %s want %s", spaced, want)
	}
}
