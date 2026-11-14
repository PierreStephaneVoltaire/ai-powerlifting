package views

import (
	"encoding/json"
	"testing"
)

func TestDotsMatchesPythonCalculateDots(t *testing.T) {
	if got, ok := dots(581, 84.5, "male"); !ok || got != 388.34 {
		t.Fatalf("%v %v", got, ok)
	}
	if _, ok := dots(0, 80, "male"); ok {
		t.Fatal("zero totals have no score")
	}
	if _, ok := dots(500, 80, "other"); ok {
		t.Fatal("unknown sex has no score")
	}
}

func session(date string, completed bool, status string, bodyweight any, exercises ...map[string]any) map[string]any {
	list := make([]any, len(exercises))
	for i, e := range exercises {
		list[i] = e
	}
	return map[string]any{"date": date, "completed": completed, "status": status, "body_weight_kg": bodyweight, "exercises": list}
}

func TestBestSessionLiftKeepsIntegersIntegral(t *testing.T) {
	sessions := []map[string]any{
		session("2026-11-01", true, "completed", json.Number("80"),
			map[string]any{"name": "Competition Squat", "kg": json.Number("200"), "sets": json.Number("1")},
			map[string]any{"name": "Squat", "kg": json.Number("210"), "sets": json.Number("2"), "set_statuses": []any{"failed", "failed"}}),
		session("2026-11-02", true, "skipped", json.Number("90"), map[string]any{"name": "Squat", "kg": json.Number("300"), "sets": json.Number("1")}),
	}
	best, ok := bestSessionLift(sessions, "squat")
	if !ok || best.JSON() != json.Number("200") {
		t.Fatalf("%+v %v", best, ok)
	}
	if _, ok := bestSessionLift(sessions, "bench"); ok {
		t.Fatal("no bench logged")
	}
	weight, ok := latestBodyweight(sessions)
	if !ok || weight.JSON() != json.Number("90") {
		t.Fatalf("%+v", weight)
	}
}

func TestSummaryTotalStaysIntegerOnlyWhenEveryLiftIsInteger(t *testing.T) {
	sessions := []map[string]any{session("2026-11-01", true, "completed", nil,
		map[string]any{"name": "Squat", "kg": json.Number("200"), "sets": json.Number("1")},
		map[string]any{"name": "Bench", "kg": json.Number("100"), "sets": json.Number("1")},
		map[string]any{"name": "Deadlift", "kg": json.Number("250"), "sets": json.Number("1")})}
	summary := buildSummary(map[string]any{}, map[string]any{}, sessions)
	if summary.Total.JSON() != json.Number("550") {
		t.Fatalf("%v", summary.Total.JSON())
	}
	program := map[string]any{"current_maxes": map[string]any{"squat": json.Number("200")}}
	mixed := buildSummary(map[string]any{}, program, sessions)
	if mixed.Total.JSON() != json.Number("550.0") {
		t.Fatalf("a float lift makes the total a float: %v", mixed.Total.JSON())
	}
}

func TestSetCompletionRoundsHalfToEven(t *testing.T) {
	exercise := map[string]any{"sets": json.Number("2.5"), "set_statuses": []any{"failed", "failed", "completed"}}
	if hasCompletedSet(exercise) {
		t.Fatal("2.5 rounds to 2 sets, both failed")
	}
	exercise["sets"] = json.Number("3.5")
	if !hasCompletedSet(exercise) {
		t.Fatal("3.5 rounds to 4 sets")
	}
}
