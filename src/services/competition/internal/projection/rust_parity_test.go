package projection

import (
	"encoding/json"
	"os"
	"testing"

	"powerlifting/competition/internal/pyjson"
)

type goldenCase struct {
	Name      string
	Program   map[string]any
	Target    string
	Reference string
	Today     string
	Answer    map[string]any
}

func loadGolden(t *testing.T) []goldenCase {
	t.Helper()
	raw, err := os.ReadFile(goldenPath(t, "projection_cases.json"))
	if err != nil {
		t.Fatal(err)
	}
	decoded, err := pyjson.Decode(raw)
	if err != nil {
		t.Fatal(err)
	}
	var cases []goldenCase
	for _, item := range decoded.([]any) {
		entry := item.(map[string]any)
		cases = append(cases, goldenCase{
			Name:      entry["name"].(string),
			Program:   entry["program"].(map[string]any),
			Target:    entry["target"].(string),
			Reference: entry["reference"].(string),
			Today:     entry["today"].(string),
			Answer:    entry["answer"].(map[string]any),
		})
	}
	return cases
}

func programFrom(t *testing.T, raw map[string]any) Program {
	t.Helper()
	var sessionItems, entries []map[string]any
	for _, item := range raw["sessions"].([]any) {
		sessionItems = append(sessionItems, item.(map[string]any))
	}
	for _, item := range raw["competitions"].([]any) {
		entries = append(entries, item.(map[string]any))
	}
	meta, _ := raw["meta"].(map[string]any)
	return Program{Meta: meta, Sessions: SessionsFromItems(sessionItems), Competitions: CompetitionsFromEntries(entries)}
}

func asMap(projected *Projection) map[string]any {
	lifts := map[string]any{}
	for key, lift := range projected.Lifts {
		lifts[key] = map[string]any{
			"current": lift.Current, "projected": lift.Projected, "slope_kg_per_week": lift.Slope,
			"confidence": lift.Confidence, "ceiling_clamped": lift.Clamped,
		}
	}
	calibration := map[string]any{"calibrated": projected.Calibration.Calibrated, "meets": json.Number(itoa(projected.Calibration.Meets))}
	if projected.Calibration.MedianPRR != nil {
		calibration["median_prr"] = *projected.Calibration.MedianPRR
	} else {
		calibration["median_prr"] = nil
	}
	if projected.Calibration.LambdaMultiplier != nil {
		calibration["lambda_multiplier"] = *projected.Calibration.LambdaMultiplier
	} else {
		calibration["lambda_multiplier"] = nil
	}
	return map[string]any{
		"total": projected.Total, "confidence": projected.Confidence, "weeks_to_comp": projected.WeeksToComp,
		"method": "session_estimated", "lifts": lifts, "projection_calibration": calibration,
	}
}

func itoa(value int) string {
	encoded, _ := json.Marshal(value)
	return string(encoded)
}

func canonical(t *testing.T, value any) string {
	t.Helper()
	encoded, err := pyjson.Encode(value)
	if err != nil {
		t.Fatal(err)
	}
	return string(encoded)
}

func TestMeetMatchesTheRustProjection(t *testing.T) {
	cases := loadGolden(t)
	if len(cases) < 50 {
		t.Fatalf("expected the checked-in golden corpus, got %d cases", len(cases))
	}
	ready := 0
	for _, golden := range cases {
		t.Run(golden.Name, func(t *testing.T) {
			reference, ok := ParseDay(golden.Reference)
			if !ok {
				t.Fatalf("bad reference %q", golden.Reference)
			}
			today, ok := ParseDay(golden.Today)
			if !ok {
				t.Fatalf("bad today %q", golden.Today)
			}
			projected, reason := Meet(programFrom(t, golden.Program), golden.Target, reference, today)
			if want, insufficient := golden.Answer["insufficient"]; insufficient {
				if projected != nil || reason != want {
					t.Fatalf("want insufficient %q, got %v %q", want, projected, reason)
				}
				return
			}
			if projected == nil {
				t.Fatalf("want a projection, got insufficient %q", reason)
			}
			ready++
			want := canonical(t, golden.Answer)
			if got := canonical(t, asMap(projected)); got != want {
				t.Fatalf("projection differs\n got %s\nwant %s", got, want)
			}
		})
	}
	if ready < 40 {
		t.Fatalf("only %d ready projections compared", ready)
	}
}
