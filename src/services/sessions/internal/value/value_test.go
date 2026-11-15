package value

import (
	"encoding/json"
	"testing"

	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
)

func TestFloatMatchesPythonRepr(t *testing.T) {
	cases := map[float64]string{100: "100.0", 100.5: "100.5", 1e-7: "1e-07", 1e22: "1e+22", 0.0001: "0.0001", 123456789012345678: "1.2345678901234568e+17", 0: "0.0", -2.5: "-2.5"}
	for in, want := range cases {
		if got := Float(in); got != want {
			t.Errorf("%v: got %s want %s", in, got, want)
		}
	}
}

func TestSanitizedFollowsPythonDecimalRule(t *testing.T) {
	cases := map[string]string{"100": "100", "100.0": "100", "1E+2": "100", "102.5": "102.5", "1E-7": "1e-07", "0": "0", "-3": "-3"}
	for in, want := range cases {
		if got := Sanitized(Decimal(in)); string(got) != want {
			t.Errorf("%s: got %s want %s", in, got, want)
		}
	}
}

func TestStoredMatchesDecimalOfPythonStr(t *testing.T) {
	cases := map[string]string{"100": "100", "100.0": "100.0", "100.50": "100.5", "1e2": "100.0", "1e-07": "1E-7", "1E22": "1E+22", "7": "7"}
	for in, want := range cases {
		if got := Stored(json.Number(in)); string(got) != want {
			t.Errorf("%s: got %s want %s", in, got, want)
		}
	}
}

func TestIntOfSeparatesDynamoDecimalsFromJSONFloats(t *testing.T) {
	if IntOf(Decimal("3.9"), 0) != 3 || IntOf(json.Number("3"), 0) != 3 || IntOf(json.Number("3.0"), 9) != 9 {
		t.Fatal("numeric coercion")
	}
	if IntOf(" 12 ", 0) != 12 || IntOf("x", 7) != 7 || IntOf(nil, 5) != 5 || IntOf(true, 5) != 5 {
		t.Fatal("string and fallback coercion")
	}
}

func TestTruthyAndStr(t *testing.T) {
	for _, falsy := range []any{nil, false, "", Decimal("0"), json.Number("0"), json.Number("0.0"), []any{}, map[string]any{}} {
		if Truthy(falsy) {
			t.Errorf("%#v should be falsy", falsy)
		}
	}
	if !Truthy(json.Number("0.5")) || !Truthy("x") || !Truthy([]any{1}) {
		t.Fatal("truthy values")
	}
	if Str(nil) != "None" || Str(true) != "True" || Str(Decimal("2.0")) != "2" || Str(json.Number("2.0")) != "2.0" {
		t.Fatal("Str")
	}
}

func TestAttributeRoundTripKeepsNumbersAsNumbers(t *testing.T) {
	item := Item{
		"kg": json.Number("100.5"), "reps": json.Number("5"), "float_int": json.Number("100.0"), "tiny": json.Number("1e-07"),
		"ok": true, "none": nil, "name": "x", "list": []any{json.Number("1"), "a"}, "map": map[string]any{"n": json.Number("2")},
	}
	encoded := ToAV(item)
	for _, key := range []string{"kg", "reps", "float_int", "tiny"} {
		if _, isNumber := encoded[key].(*types.AttributeValueMemberN); !isNumber {
			t.Fatalf("%s not stored as N", key)
		}
	}
	if encoded["float_int"].(*types.AttributeValueMemberN).Value != "100.0" || encoded["tiny"].(*types.AttributeValueMemberN).Value != "1E-7" {
		t.Fatalf("number text %v %v", encoded["float_int"], encoded["tiny"])
	}
	decoded := FromAV(encoded)
	if decoded["kg"] != Decimal("100.5") || decoded["none"] != nil || decoded["ok"] != true {
		t.Fatalf("decoded %v", decoded)
	}
}

func TestRenderCanonicalisesNumbers(t *testing.T) {
	out, _ := json.Marshal(Render(map[string]any{"a": json.Number("100.50"), "b": Decimal("7.0"), "c": []any{json.Number("1e2")}}))
	if string(out) != `{"a":100.5,"b":7,"c":[100.0]}` {
		t.Fatalf("got %s", out)
	}
}

func TestDecodeKeepsNumberText(t *testing.T) {
	decoded, err := Decode([]byte(`{"a":100.0,"b":1}`))
	if err != nil || decoded.(map[string]any)["a"] != json.Number("100.0") {
		t.Fatalf("decoded %v err %v", decoded, err)
	}
	if _, err := Decode([]byte(`{} {}`)); err == nil {
		t.Fatal("trailing data accepted")
	}
}

func TestNegativeFractionsKeepTheirFraction(t *testing.T) {
	for in, want := range map[string]string{"-2.5": "-2.5", "-0.25": "-0.25", "-3.0": "-3", "-3": "-3", "2.5": "2.5"} {
		if got := Sanitized(Decimal(in)); string(got) != want {
			t.Errorf("Sanitized(%s): got %s want %s", in, got, want)
		}
	}
	item := Item{"rpe_delta": Decimal("-2.5"), "sets": []any{map[string]any{"kg": Decimal("-0.75")}}}
	out, _ := json.Marshal(Sanitize(item))
	if string(out) != `{"rpe_delta":-2.5,"sets":[{"kg":-0.75}]}` {
		t.Fatalf("Sanitize: %s", out)
	}
	rendered, _ := json.Marshal(Render(Item{"a": Decimal("-2.5"), "b": json.Number("-2.5")}))
	if string(rendered) != `{"a":-2.5,"b":-2.5}` {
		t.Fatalf("Render: %s", rendered)
	}
	if Str(Decimal("-2.5")) != "-2.5" || !Truthy(Decimal("-0.5")) {
		t.Fatal("Str or Truthy truncated a negative fraction")
	}
}
