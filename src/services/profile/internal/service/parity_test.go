package service

import (
	"bytes"
	"encoding/json"
	"errors"
	"math/big"
	"os"
	"sort"
	"testing"

	"powerlifting/profile/internal/apperr"
	"powerlifting/profile/internal/auth"
	"powerlifting/profile/internal/value"
)

type scenario struct {
	Name   string `json:"name"`
	Group  string `json:"group"`
	Op     string `json:"op"`
	Args   map[string]any
	Caller struct {
		Person  string `json:"person"`
		Athlete string `json:"athlete"`
		Source  string `json:"source"`
		Job     string `json:"job"`
		Nested  bool   `json:"nested"`
	} `json:"caller"`
	Now       string                      `json:"now"`
	IDs       []string                    `json:"ids"`
	Discord   map[string]string           `json:"discord"`
	Analytics map[string]any              `json:"analytics"`
	S3Seed    []string                    `json:"s3_seed"`
	Seed      map[string][]map[string]any `json:"seed"`
	Subset    bool                        `json:"subset"`
	Expect    struct {
		OK     bool            `json:"ok"`
		Result json.RawMessage `json:"result"`
		Status int             `json:"status"`
		Detail json.RawMessage `json:"detail"`
		Schema bool            `json:"schema"`
	} `json:"expect"`
	After   map[string][]map[string]any `json:"after"`
	S3After []map[string]any            `json:"s3_after"`
	Bumps   []string                    `json:"bumps"`
}

func (s *scenario) UnmarshalJSON(raw []byte) error {
	type alias scenario
	aux := struct {
		*alias
		Args json.RawMessage `json:"args"`
	}{alias: (*alias)(s)}
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.UseNumber()
	if err := decoder.Decode(&aux); err != nil {
		return err
	}
	if len(aux.Args) > 0 {
		decoded, err := value.Decode(aux.Args)
		if err != nil {
			return err
		}
		s.Args, _ = decoded.(map[string]any)
	}
	return nil
}

func loadScenarios(t *testing.T) []scenario {
	t.Helper()
	raw, err := os.ReadFile(goldenPath(t, "scenarios.json"))
	if err != nil {
		t.Fatal(err)
	}
	var scenarios []scenario
	if err := json.Unmarshal(raw, &scenarios); err != nil {
		t.Fatal(err)
	}
	return scenarios
}

func exactJSON(v any) string {
	encoded, _ := json.Marshal(value.Render(v))
	var buffer bytes.Buffer
	decoder := json.NewDecoder(bytes.NewReader(encoded))
	decoder.UseNumber()
	var generic any
	_ = decoder.Decode(&generic)
	out, _ := json.Marshal(generic)
	buffer.Write(out)
	return buffer.String()
}

func normalizeNumbers(v any) any {
	switch typed := v.(type) {
	case json.Number:
		return numericText(string(typed))
	case value.Decimal:
		return numericText(string(typed))
	case map[string]any:
		out := make(map[string]any, len(typed))
		for key, child := range typed {
			out[key] = normalizeNumbers(child)
		}
		return out
	case []any:
		out := make([]any, len(typed))
		for i, child := range typed {
			out[i] = normalizeNumbers(child)
		}
		return out
	}
	return v
}

func numericText(text string) string {
	rat, ok := new(big.Rat).SetString(text)
	if !ok {
		return text
	}
	if rat.IsInt() {
		return rat.Num().String()
	}
	f, _ := rat.Float64()
	return value.Float(f)
}

func byValue(v any) string {
	encoded, _ := json.Marshal(normalizeNumbers(value.Render(v)))
	return string(encoded)
}

func decodeAny(t *testing.T, raw json.RawMessage) any {
	t.Helper()
	if len(raw) == 0 {
		return nil
	}
	decoded, err := value.Decode(raw)
	if err != nil {
		t.Fatal(err)
	}
	return decoded
}

func subsetOf(want, got any) (bool, string) {
	switch typed := want.(type) {
	case map[string]any:
		other, ok := got.(map[string]any)
		if !ok {
			return false, "not an object"
		}
		for key, child := range typed {
			gotChild, present := other[key]
			if !present {
				return false, "missing " + key
			}
			if ok, why := subsetOf(child, gotChild); !ok {
				return false, key + ": " + why
			}
		}
		return true, ""
	}
	if exactJSON(want) != exactJSON(got) {
		return false, exactJSON(want) + " != " + exactJSON(got)
	}
	return true, ""
}

func dumpAll(h *harness) map[string]any {
	out := map[string]any{}
	for logical, name := range tableNames {
		items := h.db.Items(name)
		list := make([]any, len(items))
		for i, item := range items {
			list[i] = item
		}
		out[logical] = list
	}
	return out
}

func TestPythonParity(t *testing.T) {
	scenarios := loadScenarios(t)
	if len(scenarios) < 400 {
		t.Fatalf("expected the captured Python scenarios, got %d", len(scenarios))
	}
	for _, sc := range scenarios {
		t.Run(sc.Name, func(t *testing.T) {
			h := newHarness(t, options{Now: sc.Now, IDs: sc.IDs, Discord: sc.Discord, Analytics: sc.Analytics, S3Seed: sc.S3Seed})
			for logical, items := range sc.Seed {
				for _, item := range items {
					h.seed(logical, reviveSeed(item).(map[string]any))
				}
			}
			result, err := h.call(sc.Op, sc.Args, auth.Caller{Person: sc.Caller.Person, Athlete: sc.Caller.Athlete, Source: sc.Caller.Source, JobID: sc.Caller.Job, Nested: sc.Caller.Nested})
			if sc.Expect.OK {
				if err != nil {
					t.Fatalf("unexpected error: %v", err)
				}
				want := decodeAny(t, sc.Expect.Result)
				if sc.Subset {
					if ok, why := subsetOf(want, normalizeRender(result)); !ok {
						t.Fatalf("result is not a superset: %s", why)
					}
				} else if got, expected := exactJSON(result), exactJSON(want); got != expected {
					t.Fatalf("result mismatch\n got: %s\nwant: %s", got, expected)
				}
			} else {
				var failure *apperr.Error
				if !errors.As(err, &failure) {
					t.Fatalf("expected error %d %s, got result %v err %v", sc.Expect.Status, sc.Expect.Detail, result, err)
				}
				if failure.Status != sc.Expect.Status {
					t.Fatalf("status: got %d (%s) want %d %s", failure.Status, failure.Message, sc.Expect.Status, sc.Expect.Detail)
				}
				want, _ := decodeAny(t, sc.Expect.Detail).(map[string]any)
				if want != nil && want["code"] == "unhandled" {
					want = nil
					sc.Expect.Detail = nil
				}
				if want != nil {
					got, _ := decodeAny(t, mustJSON(failure.Detail())).(map[string]any)
					if got["code"] != want["code"] {
						t.Fatalf("code: got %v want %v (%v)", got["code"], want["code"], failure.Message)
					}
					if !sc.Expect.Schema && exactJSON(got) != exactJSON(want) {
						t.Fatalf("detail mismatch\n got: %s\nwant: %s", exactJSON(got), exactJSON(want))
					}
				} else if string(sc.Expect.Detail) != "" && failure.Message != string(sc.Expect.Detail) {
					var text string
					_ = json.Unmarshal(sc.Expect.Detail, &text)
					if text != failure.Message {
						t.Fatalf("message: got %q want %q", failure.Message, text)
					}
				}
			}
			after := dumpAll(h)
			for logical, wantItems := range sc.After {
				want := make([]any, len(wantItems))
				for i, item := range wantItems {
					want[i] = item
				}
				if got, expected := byValue(after[logical]), byValue(want); got != expected {
					t.Fatalf("table %s mismatch\n got: %s\nwant: %s", logical, got, expected)
				}
			}
			wantS3 := make([]any, len(sc.S3After))
			for i, entry := range sc.S3After {
				wantS3[i] = entry
			}
			if got, expected := byValue(h.bucket.listing()), byValue(wantS3); got != expected {
				t.Fatalf("s3 mismatch\n got: %s\nwant: %s", got, expected)
			}
			gotBumps := append([]string{}, h.bumps.keys...)
			wantBumps := append([]string{}, sc.Bumps...)
			sort.Strings(gotBumps)
			sort.Strings(wantBumps)
			if byValue(toAny(gotBumps)) != byValue(toAny(wantBumps)) {
				t.Fatalf("analysis bumps: got %v want %v", gotBumps, wantBumps)
			}
		})
	}
}

func toAny(values []string) any {
	out := make([]any, len(values))
	for i, v := range values {
		out[i] = v
	}
	return out
}

func mustJSON(v any) json.RawMessage {
	encoded, _ := json.Marshal(v)
	return encoded
}

func normalizeRender(v any) any {
	encoded, _ := json.Marshal(value.Render(v))
	decoded, _ := value.Decode(encoded)
	return decoded
}

func reviveSeed(v any) any {
	switch typed := v.(type) {
	case map[string]any:
		if set, ok := typed["__set__"].([]any); ok && len(typed) == 1 {
			out := make(value.StringSet, len(set))
			for i, entry := range set {
				out[i] = entry.(string)
			}
			return out
		}
		out := make(map[string]any, len(typed))
		for key, child := range typed {
			out[key] = reviveSeed(child)
		}
		return out
	case []any:
		out := make([]any, len(typed))
		for i, child := range typed {
			out[i] = reviveSeed(child)
		}
		return out
	}
	return v
}
