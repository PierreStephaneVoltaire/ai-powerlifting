package render

import (
	"strings"
	"testing"
	"time"

	"github.com/xuri/excelize/v2"
)

func TestBlockPeakingExports(t *testing.T) {
	bundle := map[string]any{
		"block":        map[string]any{"label": "Example", "startDate": "2025-01-01", "endDate": "2025-01-31", "weekCount": 4.0},
		"historical":   map[string]any{"competitionOutcome": map[string]any{"bodyweightKg": 82.456}},
		"weightLog":    []any{map[string]any{"date": "2025-01-02", "kg": 80.126}},
		"dietNotes":    []any{map[string]any{"date": "2025-01-03", "avg_daily_calories": 2400.0, "avg_sleep_hours": 7.5}},
		"measurements": map[string]any{"height_cm": 180.0},
		"liftProfiles": []any{map[string]any{"lift": "squat", "volume_tolerance": "high"}},
		"weekly": map[string]any{
			"banister":         map[string]any{"series": []any{map[string]any{"date": "2024-12-31", "ctl": 1.0}, map[string]any{"date": "2025-01-02", "ctl": 12.5, "atl": 8.0, "tsb": 4.5}}},
			"peaking_timeline": map[string]any{"series": []any{map[string]any{"date": "2025-01-03", "projected_tsb": 9.0}}, "specificity_points": []any{map[string]any{"date": "2025-01-03", "narrow": 0.7}}},
			"decoupling":       map[string]any{"series": []any{map[string]any{"week_start": "2025-01-06", "decoupling": 1.25}}},
			"taper_quality":    map[string]any{"score": 80.0, "components": map[string]any{"volume_reduction": 0.5}},
			"volume_landmarks": map[string]any{"squat": map[string]any{"mv": 4.0, "mev": 6.0, "confidence": "high"}},
		},
		"correlation": map[string]any{"summary": "Report summary", "findings": []any{map[string]any{"driver": "Squat"}}},
	}
	markdown := BlockMarkdown(bundle, time.Time{})
	for _, want := range []string{"82.46 kg", "| 2025-01-02 | 12.5 | 8 | 4.5 |", "## Peaking Timeline", "## Peaking Specificity", "## Fatigue Decoupling", "## Taper Quality", "## Volume Landmarks", "Report summary"} {
		if !strings.Contains(markdown, want) {
			t.Errorf("markdown missing %q", want)
		}
	}
	if strings.Contains(markdown, "2024-12-31") {
		t.Error("Banister series includes a point outside the block")
	}
	content, err := BlockWorkbook(bundle)
	if err != nil {
		t.Fatal(err)
	}
	file, err := excelize.OpenReader(strings.NewReader(string(content)))
	if err != nil {
		t.Fatal(err)
	}
	defer file.Close()
	for address, want := range map[string]string{"Competition!B4": "82.46 kg", "Banister!B2": "12.5", "Peaking Timeline!C2": "9", "Volume Landmarks!C2": "6", "Body Weight!B2": "80.13 kg", "Nutrition and Sleep!B2": "2400", "Nutrition and Sleep!H2": "7.5", "Measurements!B2": "180", "Lift Profiles!B2": "high"} {
		sheet, cell, _ := strings.Cut(address, "!")
		got, err := file.GetCellValue(sheet, cell)
		if err != nil || got != want {
			t.Errorf("%s = %q (%v), want %q", address, got, err, want)
		}
	}
}
