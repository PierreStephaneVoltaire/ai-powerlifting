package render

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/xuri/excelize/v2"
)

const goldenDir = "../../../../../fixtures/operator/golden"

type manifestCall struct {
	File      string         `json:"file"`
	Operation string         `json:"operation"`
	Inputs    map[string]any `json:"inputs"`
}

func readJSON(t *testing.T, path string, into any) {
	t.Helper()
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	if err := json.Unmarshal(raw, into); err != nil {
		t.Fatal(err)
	}
}

func goldenBundle(t *testing.T) (map[string]any, string) {
	t.Helper()
	var manifest struct {
		Calls []manifestCall `json:"calls"`
	}
	readJSON(t, filepath.Join(goldenDir, "manifest.json"), &manifest)
	var exportCall *manifestCall
	for index, call := range manifest.Calls {
		if call.Operation == "analytics.export" && call.Inputs["format"] == "markdown" {
			exportCall = &manifest.Calls[index]
			break
		}
	}
	if exportCall == nil {
		t.Fatal("manifest has no markdown export")
	}
	var bundleFile string
	for _, call := range manifest.Calls {
		if call.Operation == "analytics.blocks_get" && call.Inputs["blockKey"] == exportCall.Inputs["blockKey"] {
			bundleFile = call.File
		}
	}
	var bundle struct {
		Body map[string]any `json:"body"`
	}
	readJSON(t, filepath.Join(goldenDir, bundleFile), &bundle)
	golden, err := os.ReadFile(filepath.Join(goldenDir, strings.TrimSuffix(exportCall.File, ".json")+".md"))
	if err != nil {
		t.Fatal(err)
	}
	return bundle.Body, string(golden)
}

func TestBlockMarkdownMatchesGolden(t *testing.T) {
	bundle, golden := goldenBundle(t)
	generated := time.Date(2026, 11, 12, 19, 3, 21, 174_000_000, time.UTC)
	got := BlockMarkdown(bundle, generated)
	if got != golden {
		t.Fatalf("markdown differs from golden\n--- got ---\n%s\n--- want ---\n%s", got, golden)
	}
}

func TestBlockFilename(t *testing.T) {
	bundle, _ := goldenBundle(t)
	if got := BlockFilename(bundle, "markdown"); got != "block-analysis-2023-05-10.md" {
		t.Fatalf("markdown filename %q", got)
	}
	if got := BlockFilename(bundle, "xlsx"); got != "block-analysis-2023-05-10.xlsx" {
		t.Fatalf("xlsx filename %q", got)
	}
}

func TestBlockWorkbookSheetsAndCells(t *testing.T) {
	bundle, _ := goldenBundle(t)
	content, err := BlockWorkbook(bundle)
	if err != nil {
		t.Fatal(err)
	}
	file, err := excelize.OpenReader(strings.NewReader(string(content)))
	if err != nil {
		t.Fatal(err)
	}
	defer file.Close()
	want := []string{"Summary", "Start Maxes", "Strength", "Competition", "Data Quality", "Weekly Analysis", "Lift Metrics", "ACWR", "Specificity", "Fatigue Dimensions", "Exercise Stats", "Program Analysis", "ROI Correlation"}
	got := file.GetSheetList()
	if strings.Join(got, ",") != strings.Join(want, ",") {
		t.Fatalf("sheets %v, want %v", got, want)
	}
	cells := map[string]string{"Summary!A2": "Block", "Summary!B2": "2023-05-10", "Summary!B4": "1", "Lift Metrics!A2": "Squat", "Exercise Stats!C2": "0.0 kg"}
	for address, expected := range cells {
		sheet, cell, _ := strings.Cut(address, "!")
		value, err := file.GetCellValue(sheet, cell)
		if err != nil || value != expected {
			t.Fatalf("%s = %q (%v), want %q", address, value, err, expected)
		}
	}
}

func TestFixedRoundsHalfAwayFromZero(t *testing.T) {
	cases := map[float64]string{2.5: "3", 0.125: "0.13", -0.125: "-0.13", 1.005: "1.00", 100: "100", 0.05: "0.1"}
	for value, want := range cases {
		digits := 0
		if strings.Contains(want, ".") {
			digits = len(want) - strings.Index(want, ".") - 1
		}
		if got := fixed(value, digits); got != want {
			t.Errorf("fixed(%v,%d) = %q, want %q", value, digits, got, want)
		}
	}
}

func TestSheetNamesAreUniqueAndSafe(t *testing.T) {
	used := map[string]bool{}
	first := sheetName("A/B:C", used)
	second := sheetName("A/B:C", used)
	if first == second || strings.ContainsAny(first, `/:`) {
		t.Fatalf("names %q %q", first, second)
	}
	if long := sheetName(strings.Repeat("x", 60), used); len([]rune(long)) > sheetNameLimit {
		t.Fatalf("name too long %q", long)
	}
}

func TestLifetimeRendersTablesAndNarrative(t *testing.T) {
	report := map[string]any{
		"block_count": 2.0,
		"blocks": []any{map[string]any{
			"label": "B1", "start_date": "2024-01-01", "end_date": "2024-02-01", "week_count": 4.0,
			"classification": map[string]any{"overall": map[string]any{"label": "improved"}},
			"outcome":        map[string]any{"e1rm": map[string]any{"squat": map[string]any{"delta": 5.0}}, "dots": map[string]any{"delta": 1.25}},
		}},
		"worked":      []any{map[string]any{"variable": "volume", "statement": "more is better | maybe", "n": 3.0}},
		"data_limits": []any{"few blocks"},
	}
	lifetime := Lifetime{Athlete: "a1", GeneratedAt: "2026-01-01T00:00:00Z", BlockKeys: []string{"k1", "k2"}, Report: report, Narrative: map[string]any{"summary": "all good", "next_steps": []any{"rest", "lift"}}}
	markdown := lifetime.Markdown()
	for _, expected := range []string{"# Lifetime Analysis a1", "## Blocks", "| B1 | 2024-01-01 | 2024-02-01 | 4 | improved | 5.0 | -- | -- | 1.3 |", `more is better \| maybe`, "| Next Steps | rest |", "| Summary | all good |", "## Data Limits"} {
		if !strings.Contains(markdown, expected) {
			t.Errorf("markdown lacks %q:\n%s", expected, markdown)
		}
	}
	content, err := lifetime.Workbook()
	if err != nil {
		t.Fatal(err)
	}
	file, err := excelize.OpenReader(strings.NewReader(string(content)))
	if err != nil {
		t.Fatal(err)
	}
	defer file.Close()
	if value, _ := file.GetCellValue("Blocks", "A2"); value != "B1" {
		t.Fatalf("Blocks!A2 = %q", value)
	}
	if value, _ := file.GetCellValue("Narrative", "B2"); value == "" {
		t.Fatal("narrative sheet empty")
	}
}
