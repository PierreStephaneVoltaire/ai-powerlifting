package service

import (
	"context"
	"encoding/json"
	"net/http"
	"testing"

	"powerlifting/program/internal/apperr"
	"powerlifting/program/internal/auth"
)

func TestPercentageTemplateAppliesWithPlateRounding(t *testing.T) {
	f := loadFixture(t, goldenPath(t, "setup_template_own_hidden.json"))
	h := newHarness(t, f)
	result, err := h.svc.Call(context.Background(), f.Op, f.Args, auth.Caller{Person: f.Person, Athlete: f.Athlete})
	if err != nil {
		t.Fatal(err)
	}
	if count := result.(map[string]any)["sessionCount"]; count != int64(1) {
		t.Fatalf("result %v", result)
	}
	var found bool
	for _, item := range h.db.Dump(h.tables.Sessions) {
		planned := item["planned_exercises"].([]any)
		exercise := planned[0].(map[string]any)
		if exercise["kg"] != json.Number("125") || exercise["load_source"] != "percentage" {
			t.Fatalf("exercise %v", exercise)
		}
		found = true
	}
	if !found {
		t.Fatal("no session written")
	}
}

func TestMissingProgramIsNotFound(t *testing.T) {
	f := loadFixture(t, goldenPath(t, "program_get_empty.json"))
	h := newHarness(t, f)
	_, err := h.svc.Call(context.Background(), f.Op, f.Args, auth.Caller{Person: f.Person, Athlete: f.Athlete})
	failure, ok := err.(*apperr.Error)
	if !ok || failure.Status != http.StatusNotFound || failure.Code != "not_found" {
		t.Fatalf("err %v", err)
	}
}
