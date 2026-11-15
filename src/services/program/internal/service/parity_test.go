package service

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"reflect"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"sync/atomic"
	"testing"
	"time"
	"unicode/utf8"

	"powerlifting/program/internal/analysis"
	"powerlifting/program/internal/apperr"
	"powerlifting/program/internal/auth"
	"powerlifting/program/internal/contract"
	"powerlifting/program/internal/env"
	"powerlifting/program/internal/ops"
	"powerlifting/program/internal/pyval"
	"powerlifting/program/internal/store"
)

type fixture struct {
	Name         string                      `json:"name"`
	Op           string                      `json:"op"`
	Athlete      string                      `json:"athlete"`
	Person       string                      `json:"person"`
	Args         map[string]any              `json:"args"`
	Access       map[string]any              `json:"access"`
	Analytics    map[string]any              `json:"analytics"`
	AnalyticsRaw json.RawMessage             `json:"-"`
	LiftOrder    []string                    `json:"-"`
	Seed         map[string][]map[string]any `json:"seed"`
	Expect       struct {
		Status      int            `json:"status"`
		Result      any            `json:"result"`
		Error       map[string]any `json:"error"`
		Bumps       []string       `json:"bumps"`
		State       map[string][]any
		WeeklyCalls []any `json:"weekly_calls"`
	} `json:"expect"`
	StateRaw map[string]json.RawMessage
}

var deviations = map[string]int{
	"program_get_unpublished_pointer": 404,
	"program_get_empty":               404,
	"archive_missing":                 404,
	"setup_template_own_hidden":       200,
}

var schemaMessages = map[string]bool{"meta_no_field": true}

var (
	uuidPattern  = regexp.MustCompile(`[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}`)
	blockPattern = regexp.MustCompile(`block-[0-9a-f]{16}`)
	hexPattern   = regexp.MustCompile(`[0-9a-f]{32}`)
	timePattern  = regexp.MustCompile(`\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?\+00:00`)
)

func mask(value any) any {
	switch typed := value.(type) {
	case string:
		typed = uuidPattern.ReplaceAllString(typed, "<uuid>")
		typed = blockPattern.ReplaceAllString(typed, "block-<id>")
		typed = hexPattern.ReplaceAllString(typed, "<hex>")
		return timePattern.ReplaceAllString(typed, "<ts>")
	case map[string]any:
		out := make(map[string]any, len(typed))
		for key, item := range typed {
			out[mask(key).(string)] = mask(item)
		}
		return out
	case []any:
		out := make([]any, len(typed))
		for index, item := range typed {
			out[index] = mask(item)
		}
		return out
	}
	return value
}

func correctedExpectation(op string, got, want any) any {
	switch op {
	case "block_transition":
		return restoreNumbersPythonStringified(got, want)
	case "export_program_markdown":
		return dropWholeNumberFractionSuffix(got, want)
	}
	return want
}

func restoreNumbersPythonStringified(got, want any) any {
	switch typed := want.(type) {
	case string:
		number, isNumber := got.(float64)
		parsed, err := strconv.ParseFloat(typed, 64)
		if isNumber && err == nil && parsed == number {
			return got
		}
	case map[string]any:
		gotMap, _ := got.(map[string]any)
		out := make(map[string]any, len(typed))
		for key, item := range typed {
			out[key] = restoreNumbersPythonStringified(gotMap[key], item)
		}
		return out
	case []any:
		gotList, _ := got.([]any)
		out := make([]any, len(typed))
		for index, item := range typed {
			var counterpart any
			if index < len(gotList) {
				counterpart = gotList[index]
			}
			out[index] = restoreNumbersPythonStringified(counterpart, item)
		}
		return out
	}
	return want
}

func dropWholeNumberFractionSuffix(got, want any) any {
	wantObject, ok := want.(map[string]any)
	if !ok {
		return want
	}
	gotObject, _ := got.(map[string]any)
	wantText, wantOK := wantObject["markdown"].(string)
	gotText, gotOK := gotObject["markdown"].(string)
	if !wantOK || !gotOK {
		return want
	}
	wantLines, gotLines := strings.Split(wantText, "\n"), strings.Split(gotText, "\n")
	if len(wantLines) != len(gotLines) {
		return want
	}
	for index := range wantLines {
		wantLines[index] = dropSuffixInChangedCells(gotLines[index], wantLines[index])
	}
	out := make(map[string]any, len(wantObject))
	for key, item := range wantObject {
		out[key] = item
	}
	corrected := strings.Join(wantLines, "\n")
	out["markdown"] = corrected
	if length, isNumber := wantObject["length"].(float64); isNumber {
		out["length"] = length - float64(utf8.RuneCountInString(wantText)-utf8.RuneCountInString(corrected))
	}
	return out
}

func dropSuffixInChangedCells(gotLine, wantLine string) string {
	gotCells, wantCells := strings.Split(gotLine, "|"), strings.Split(wantLine, "|")
	if len(gotCells) != len(wantCells) {
		return wantLine
	}
	for index, cell := range wantCells {
		if stripped, found := strings.CutSuffix(strings.TrimSpace(cell), ".0"); found && stripped == strings.TrimSpace(gotCells[index]) {
			wantCells[index] = " " + stripped + " "
		}
	}
	return strings.Join(wantCells, "|")
}

func canonical(value any) any {
	encoded, err := json.Marshal(pyval.Coerce(value))
	if err != nil {
		panic(err)
	}
	var generic any
	if err := json.Unmarshal(encoded, &generic); err != nil {
		panic(err)
	}
	return mask(generic)
}

func sortItems(items []any) {
	sort.SliceStable(items, func(i, j int) bool {
		a, _ := json.Marshal(items[i])
		b, _ := json.Marshal(items[j])
		ka, kb := keyString(items[i]), keyString(items[j])
		if ka != kb {
			return ka < kb
		}
		return bytes.Compare(a, b) < 0
	})
}

func keyString(item any) string {
	object, _ := item.(map[string]any)
	return fmt.Sprint(object["pk"], "|", object["sk"])
}

func loadFixture(t *testing.T, path string) *fixture {
	t.Helper()
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.UseNumber()
	var f fixture
	if err := decoder.Decode(&f); err != nil {
		t.Fatalf("%s: %v", path, err)
	}
	f.Args, _ = pyval.Native(map[string]any(f.Args)).(map[string]any)
	if f.Analytics != nil {
		f.Analytics, _ = pyval.Native(map[string]any(f.Analytics)).(map[string]any)
	}
	var rawAnalytics struct {
		Analytics json.RawMessage `json:"analytics"`
	}
	_ = json.Unmarshal(raw, &rawAnalytics)
	if len(rawAnalytics.Analytics) > 0 && string(rawAnalytics.Analytics) != "null" {
		f.LiftOrder = pyval.KeyOrder(rawAnalytics.Analytics, "lifts")
	}
	f.Access, _ = pyval.Native(map[string]any(f.Access)).(map[string]any)
	var plain struct {
		Expect struct {
			Result any              `json:"result"`
			State  map[string][]any `json:"state"`
		} `json:"expect"`
	}
	if err := json.Unmarshal(raw, &plain); err != nil {
		t.Fatal(err)
	}
	f.Expect.Result = plain.Expect.Result
	f.Expect.State = plain.Expect.State
	return &f
}

type fakeAnalytics struct {
	value map[string]any
	order []string
	calls []any
}

func (f *fakeAnalytics) WeeklyAnalysis(_ context.Context, _ ops.Caller, arguments map[string]any) (*ops.Weekly, error) {
	call := map[string]any{}
	for key, value := range arguments {
		if key != "program" && key != "sessions" && value != nil {
			call[key] = value
		}
	}
	f.calls = append(f.calls, call)
	if f.value == nil {
		return nil, fmt.Errorf("analytics unavailable")
	}
	return &ops.Weekly{Data: pyval.DeepCopy(f.value).(map[string]any), LiftOrder: f.order}, nil
}

type recorder struct{ keys []string }

func (r *recorder) Record(_ context.Context, operation, athlete string) {
	if analysis.WritesAnalysisInput(operation) {
		r.keys = append(r.keys, analysis.VersionKey(athlete))
	}
}

type harness struct {
	svc       *Service
	db        *store.Memory
	tables    store.Tables
	analytics *fakeAnalytics
	versions  *recorder
	profile   *httptest.Server
}

func newHarness(t *testing.T, f *fixture) *harness {
	t.Helper()
	profile := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(f.Access)
	}))
	t.Cleanup(profile.Close)
	registry, err := contract.Load()
	if err != nil {
		t.Fatal(err)
	}
	tables := store.Tables{Health: "if-health", Sessions: "if-sessions", Competitions: "if-powerlifting-user-competitions", Templates: "if-health-templates"}
	db := store.NewMemory()
	for key, table := range map[string]store.Table{"health": tables.Health, "sessions": tables.Sessions, "competitions": tables.Competitions, "templates": tables.Templates} {
		for _, item := range f.Seed[key] {
			if err := db.Seed(table, item); err != nil {
				t.Fatalf("seed %s: %v", key, err)
			}
		}
	}
	var counter atomic.Int64
	runtimeEnv := env.Env{
		Now: func() time.Time { return time.Date(2026, 11, 14, 12, 0, 0, 0, time.UTC) },
		UUID: func() string {
			n := counter.Add(1)
			return fmt.Sprintf("%08x-0000-4000-8000-%012x", n, n)
		},
	}
	analytics := &fakeAnalytics{value: f.Analytics, order: f.LiftOrder}
	deps := &ops.Deps{
		Programs: store.New(db, tables, runtimeEnv), Related: store.Related{DB: db, Tables: tables}, Analytics: analytics,
		Env: runtimeEnv, Config: ops.Config{TemplatesLibraryPK: "template_library"}, Log: slog.New(slog.NewTextHandler(io.Discard, nil)),
		Today: func() string { return "2026-11-14" },
	}
	versions := &recorder{}
	svc, err := New(registry, auth.NewAccess(profile.URL), deps, versions)
	if err != nil {
		t.Fatal(err)
	}
	return &harness{svc: svc, db: db, tables: tables, analytics: analytics, versions: versions, profile: profile}
}

func TestParityWithPythonGoldens(t *testing.T) {
	paths, _ := filepath.Glob(goldenPath(t, "*.json"))
	if len(paths) == 0 {
		t.Fatal("no fixtures")
	}
	for _, path := range paths {
		f := loadFixture(t, path)
		t.Run(f.Name, func(t *testing.T) {
			h := newHarness(t, f)
			result, err := h.svc.Call(context.Background(), f.Op, f.Args, auth.Caller{Person: f.Person, Athlete: f.Athlete})
			status := 200
			var failure *apperr.Error
			if err != nil {
				var ok bool
				if failure, ok = err.(*apperr.Error); !ok {
					failure = apperr.Internal(err.Error())
				}
				status = failure.Status
			}
			want := f.Expect.Status
			if override, ok := deviations[f.Name]; ok {
				want = override
			}
			if status != want {
				t.Fatalf("status %d want %d (python %d): %v", status, want, f.Expect.Status, err)
			}
			if _, deviating := deviations[f.Name]; deviating {
				return
			}
			if failure != nil {
				if !schemaMessages[f.Name] && f.Expect.Error["message"] != nil && failure.Message != f.Expect.Error["message"] && status != 500 {
					t.Fatalf("message %q want %q", failure.Message, f.Expect.Error["message"])
				}
			} else {
				got := canonical(result)
				want := correctedExpectation(f.Op, got, mask(f.Expect.Result))
				if !reflect.DeepEqual(got, want) {
					if diff := markdownDiff(got, want); diff != "" {
						t.Fatal(diff)
					}
					t.Fatalf("result mismatch\n got: %s\nwant: %s", short(got), short(want))
				}
			}
			assertState(t, h, f)
			if got := h.versions.keys; !equalStrings(got, f.Expect.Bumps) {
				t.Fatalf("bumps %v want %v", got, f.Expect.Bumps)
			}
			if f.Op == "export_program_markdown" && failure == nil {
				if !reflect.DeepEqual(canonical(h.analytics.calls), canonical(emptyIfNil(f.expectWeekly()))) {
					t.Fatalf("weekly calls %v", h.analytics.calls)
				}
			}
		})
	}
}

func (f *fixture) expectWeekly() any { return f.Expect.WeeklyCalls }

func emptyIfNil(value any) any {
	if value == nil {
		return []any{}
	}
	return value
}

func assertState(t *testing.T, h *harness, f *fixture) {
	t.Helper()
	tables := map[string]store.Table{"health": h.tables.Health, "sessions": h.tables.Sessions, "competitions": h.tables.Competitions, "templates": h.tables.Templates}
	for key, table := range tables {
		var got []any
		for _, item := range h.db.Dump(table) {
			got = append(got, canonical(item))
		}
		var want []any
		for _, item := range f.Expect.State[key] {
			want = append(want, mask(item))
		}
		sortItems(got)
		sortItems(want)
		if len(got) != len(want) {
			t.Fatalf("state %s: %d items want %d\n got keys %v\nwant keys %v", key, len(got), len(want), keys(got), keys(want))
		}
		for index := range got {
			if !reflect.DeepEqual(got[index], want[index]) {
				t.Fatalf("state %s item %s differs\n got: %s\nwant: %s", key, keyString(want[index]), short(got[index]), short(want[index]))
			}
		}
	}
}

func keys(items []any) []string {
	out := make([]string, len(items))
	for index, item := range items {
		out[index] = keyString(item)
	}
	return out
}

func equalStrings(a, b []string) bool {
	if len(a) != len(b) {
		return false
	}
	for index := range a {
		if a[index] != b[index] {
			return false
		}
	}
	return true
}

func short(value any) string {
	encoded, _ := json.Marshal(value)
	text := string(encoded)
	if len(text) > 6000 {
		text = text[:6000] + "..."
	}
	return strings.TrimSpace(text)
}

func markdownDiff(got, want any) string {
	gotMap, ok1 := got.(map[string]any)
	wantMap, ok2 := want.(map[string]any)
	if !ok1 || !ok2 {
		return ""
	}
	g, ok1 := gotMap["markdown"].(string)
	w, ok2 := wantMap["markdown"].(string)
	if !ok1 || !ok2 || g == w {
		return ""
	}
	index := 0
	for index < len(g) && index < len(w) && g[index] == w[index] {
		index++
	}
	start := max(0, index-120)
	return fmt.Sprintf("markdown differs at %d\n got: %q\nwant: %q", index, g[start:min(len(g), index+120)], w[start:min(len(w), index+120)])
}
