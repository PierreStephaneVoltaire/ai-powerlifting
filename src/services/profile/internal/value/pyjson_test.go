package value

import (
	"encoding/json"
	"testing"
)

func TestDumpMatchesPythonCompactJSON(t *testing.T) {
	got := Dump(map[string]any{"b": []any{json.Number("1.0"), json.Number("2.5"), nil, true}, "a": "é\U0001F3CB"})
	if want := `{"a":"\u00e9\ud83c\udfcb","b":[1.0,2.5,null,true]}`; got != want {
		t.Fatalf("got %s want %s", got, want)
	}
}

func TestDumpSpacedMatchesPythonDefaultSeparators(t *testing.T) {
	got := DumpSpaced(map[string]any{"b": float64(100), "a": []any{"x", "y"}})
	if want := `{"a": ["x", "y"], "b": 100.0}`; got != want {
		t.Fatalf("got %s want %s", got, want)
	}
}

func TestDumpEscapesControlCharactersLikePython(t *testing.T) {
	if got, want := Dump("a\"b\\c\n\t\x01\x7f"), `"a\"b\\c\n\t\u0001`+"\x7f"+`"`; got != want {
		t.Fatalf("got %q want %q", got, want)
	}
}

func TestIntOfAcceptsGoIntegers(t *testing.T) {
	if IntOf(7, 0) != 7 || IntOf(int64(8), 0) != 8 || IntOf(Decimal("9"), 0) != 9 {
		t.Fatal("integer conversion")
	}
}
