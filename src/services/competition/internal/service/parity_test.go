package service

import (
	"context"
	"errors"
	"io"
	"log/slog"
	"os"
	"testing"
	"time"

	"powerlifting/competition/internal/apperr"
	"powerlifting/competition/internal/auth"
	"powerlifting/competition/internal/contract"
	"powerlifting/competition/internal/pyjson"
	"powerlifting/competition/internal/pyval"
	"powerlifting/competition/internal/store"
)

const person, athlete = "person-1", "athlete-1"

type fakeAccess struct{ extra map[string]any }

func (f *fakeAccess) Fetch(_ context.Context, _ string, _ map[string]any, caller auth.Caller) (map[string]any, error) {
	access := map[string]any{"settings_pk": person, "athlete_pk": caller.Athlete}
	for key, value := range f.extra {
		access[key] = value
	}
	return access, nil
}

type corpus struct {
	Clock     time.Time
	Today     time.Time
	Tables    map[string][]store.Item
	CalcProgs map[string]any
	Cases     []map[string]any
}

func loadCorpus(t *testing.T) corpus {
	t.Helper()
	raw, err := os.ReadFile(goldenPath(t, "parity.json"))
	if err != nil {
		t.Fatal(err)
	}
	decoded, err := pyjson.Decode(raw)
	if err != nil {
		t.Fatal(err)
	}
	root := decoded.(map[string]any)
	clock, err := time.Parse(time.RFC3339Nano, root["clock"].(string))
	if err != nil {
		t.Fatal(err)
	}
	today, err := time.Parse("2006-01-02", root["today"].(string))
	if err != nil {
		t.Fatal(err)
	}
	loaded := corpus{Clock: clock, Today: today, Tables: map[string][]store.Item{}, CalcProgs: root["calc_programs"].(map[string]any)}
	for name, items := range root["tables"].(map[string]any) {
		for _, item := range items.([]any) {
			loaded.Tables[name] = append(loaded.Tables[name], item.(map[string]any))
		}
	}
	for _, entry := range root["cases"].([]any) {
		loaded.Cases = append(loaded.Cases, entry.(map[string]any))
	}
	return loaded
}

func (c corpus) memory(remove []any, program any) *store.Memory {
	memory := store.NewMemory()
	removed := map[string]bool{}
	for _, sk := range remove {
		removed[sk.(string)] = true
	}
	for name, items := range c.Tables {
		var kept []store.Item
		for _, item := range items {
			if name == "entries" && removed[item["sk"].(string)] {
				continue
			}
			kept = append(kept, item)
		}
		memory.Load(name, kept)
	}
	if program != nil {
		body := map[string]any{"pk": athlete, "sk": "program#vcalc"}
		for key, value := range pyval.Copy(c.CalcProgs[program.(string)]).(map[string]any) {
			body[key] = value
		}
		memory.Load("health", []store.Item{
			{"pk": athlete, "sk": "program#current", "ref_sk": "program#vcalc"},
			body,
		})
	}
	return memory
}

func (c corpus) service(t *testing.T, memory *store.Memory, access *fakeAccess) *Service {
	t.Helper()
	registry, err := contract.Load()
	if err != nil {
		t.Fatal(err)
	}
	svc, err := New(registry, access, memory, memory, memory, func() time.Time { return c.Clock }, slog.New(slog.NewTextHandler(io.Discard, nil)))
	if err != nil {
		t.Fatal(err)
	}
	svc.Today = func() time.Time { return c.Today }
	return svc
}

func encode(t *testing.T, value any) string {
	t.Helper()
	encoded, err := pyjson.Encode(value)
	if err != nil {
		t.Fatal(err)
	}
	return string(encoded)
}

var bumpsCorrectedForListOpMutations = map[string]map[string]int{
	"update_via_list_op_inferred":             {store.AnalysisVersionPK + athlete: 1},
	"complete_via_list_op_inferred":           {store.AnalysisVersionPK + athlete: 1},
	"complete_via_list_op_explicit_no_weight": {store.AnalysisVersionPK + athlete: 1},
}

func TestOperationsMatchThePythonGoldens(t *testing.T) {
	data := loadCorpus(t)
	if len(data.Cases) < 50 {
		t.Fatalf("expected the checked-in golden corpus, got %d cases", len(data.Cases))
	}
	exercised := map[string]bool{}
	for _, entry := range data.Cases {
		t.Run(entry["name"].(string), func(t *testing.T) {
			memory := data.memory(entry["remove_entries"].([]any), entry["program"])
			access := &fakeAccess{}
			svc := data.service(t, memory, access)
			for index, raw := range entry["steps"].([]any) {
				step := raw.(map[string]any)
				operation := step["op"].(string)
				exercised[operation] = true
				access.extra = nil
				if extra, ok := step["access"].(map[string]any); ok {
					access.extra = extra
				}
				arguments := pyval.Copy(step["args"]).(map[string]any)
				arguments["pk"] = athlete
				result, err := svc.Call(context.Background(), operation, arguments, auth.Caller{Person: person, Athlete: athlete})
				expect := step["expect"].(map[string]any)
				if failure, failed := expect["error"].(map[string]any); failed {
					assertFailure(t, index, err, failure)
					continue
				}
				if err != nil {
					t.Fatalf("step %d: unexpected error %v", index, err)
				}
				if got, want := encode(t, result), encode(t, expect["result"]); got != want {
					t.Fatalf("step %d result differs\n got %s\nwant %s", index, got, want)
				}
			}
			if got, want := encode(t, anySlice(memory.Dump("entries"))), encode(t, entry["entries_after"]); got != want {
				t.Fatalf("entries table differs\n got %s\nwant %s", got, want)
			}
			wantBumps := map[string]int{}
			for key, value := range entry["valkey"].(map[string]any) {
				number, _ := pyval.Float(value)
				wantBumps[key] = int(number)
			}
			if corrected, ok := bumpsCorrectedForListOpMutations[entry["name"].(string)]; ok {
				wantBumps = corrected
			}
			if len(wantBumps) != len(memory.Bumps) {
				t.Fatalf("analysis version bumps %v, want %v", memory.Bumps, wantBumps)
			}
			for key, count := range wantBumps {
				if memory.Bumps[key] != count {
					t.Fatalf("analysis version bumps %v, want %v", memory.Bumps, wantBumps)
				}
			}
		})
	}
	registry, _ := contract.Load()
	for _, operation := range registry.All() {
		if !exercised[operation.Name] {
			t.Errorf("operation %s has no golden case", operation.Name)
		}
	}
}

func anySlice(items []store.Item) []any {
	out := make([]any, len(items))
	for index, item := range items {
		out[index] = map[string]any(item)
	}
	return out
}

func assertFailure(t *testing.T, step int, err error, want map[string]any) {
	t.Helper()
	var failure *apperr.Error
	if !errors.As(err, &failure) {
		t.Fatalf("step %d: want an application error, got %v", step, err)
	}
	status, _ := pyval.Float(want["status"])
	if failure.Status != int(status) {
		t.Fatalf("step %d: status %d, want %v", step, failure.Status, want["status"])
	}
	if want["schema"] == true {
		if failure.Code != "validation" {
			t.Fatalf("step %d: code %q, want validation", step, failure.Code)
		}
		return
	}
	if failure.Message != want["message"] {
		t.Fatalf("step %d: message %q, want %q", step, failure.Message, want["message"])
	}
}
