package service

import (
	"bytes"
	"encoding/json"
	"errors"
	"io"
	"math/big"
	"sort"
	"testing"

	"powerlifting/sessions/internal/apperr"
	"powerlifting/sessions/internal/value"
)

func bytesReader(raw []byte) io.Reader { return bytes.NewReader(raw) }

func exact(v any) string {
	encoded, err := json.Marshal(value.Render(v))
	if err != nil {
		return "marshal error: " + err.Error()
	}
	return string(encoded)
}

func numeric(v any) any {
	switch typed := v.(type) {
	case json.Number:
		return numericText(string(typed))
	case value.Decimal:
		return numericText(string(typed))
	case map[string]any:
		out := make(map[string]any, len(typed))
		for key, child := range typed {
			out[key] = numeric(child)
		}
		return out
	case []any:
		out := make([]any, len(typed))
		for i, child := range typed {
			out[i] = numeric(child)
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
	encoded, _ := json.Marshal(numeric(v))
	return string(encoded)
}

func TestPythonParity(t *testing.T) {
	scenarios := loadScenarios(t)
	if len(scenarios) < 90 {
		t.Fatalf("expected the captured Python scenarios, got %d", len(scenarios))
	}
	for _, sc := range scenarios {
		t.Run(sc.Name, func(t *testing.T) {
			h := newHarness(t, sc.Access)
			for _, item := range sc.Seed.Sessions {
				h.memory.SeedSession(item)
			}
			for _, item := range sc.Seed.Health {
				h.memory.SeedHealth(item)
			}
			result, err := h.call(sc.Op, sc.Args)
			if sc.Expect.OK {
				if err != nil {
					t.Fatalf("unexpected error: %v", err)
				}
				if got, want := exact(result), exact(sc.Expect.Result); got != want {
					t.Fatalf("result mismatch\n got: %s\nwant: %s", got, want)
				}
			} else {
				var failure *apperr.Error
				if !errors.As(err, &failure) {
					t.Fatalf("expected error %d %s, got result %v err %v", sc.Expect.Status, sc.Expect.Message, result, err)
				}
				if failure.Status != sc.Expect.Status || failure.Code != sc.Expect.Code || failure.Message != sc.Expect.Message {
					t.Fatalf("error mismatch: got %d %s %q want %d %s %q", failure.Status, failure.Code, failure.Message, sc.Expect.Status, sc.Expect.Code, sc.Expect.Message)
				}
			}
			after := make([]any, 0, len(h.memory.Sessions))
			keys := make([]string, 0, len(h.memory.Sessions))
			for key := range h.memory.Sessions {
				keys = append(keys, key)
			}
			sort.Strings(keys)
			for _, key := range keys {
				after = append(after, h.memory.Sessions[key])
			}
			want := make([]any, len(sc.Expect.SessionsAfter))
			for i, item := range sc.Expect.SessionsAfter {
				want[i] = item
			}
			if got, expected := byValue(after), byValue(want); got != expected {
				t.Fatalf("stored sessions mismatch\n got: %s\nwant: %s", got, expected)
			}
			if got, expected := byValue(h.versions.keys), byValue(append([]string{}, sc.Expect.Increments...)); got != expected && !(len(h.versions.keys) == 0 && len(sc.Expect.Increments) == 0) {
				t.Fatalf("analysis version bumps: got %v want %v", h.versions.keys, sc.Expect.Increments)
			}
		})
	}
}
