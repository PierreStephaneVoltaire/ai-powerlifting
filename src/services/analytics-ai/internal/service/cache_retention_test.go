package service

import (
	"context"
	"net/http"
	"testing"

	"powerlifting/analytics-ai/internal/generation"
)

func TestSavedBlockReportSurvivesTrainingChanges(t *testing.T) {
	h := newHarness(t)
	challenge, generationID := startCallback(t, h)
	_, err := h.svc.Resume(context.Background(), challenge["execution_id"].(string), map[string]any{
		"challenge_id": challenge["challenge_id"], "content": correlationAnswer,
	}, inCoachJob(person(), generationID, 1))
	if err != nil {
		t.Fatal(err)
	}
	if err := h.redis.Set("pl:analysis-version:athlete_1", "1"); err != nil {
		t.Fatal(err)
	}
	response, body := submitBlockCorrelation(t, h, map[string]any{"cache_only": true})
	if response.Status != http.StatusOK || body["cached"] != true || body["summary"] != correlationAnswer["summary"] {
		t.Fatalf("returning to the block must serve the saved report after training changes: %v", body)
	}
	if h.coach.count() != 1 {
		t.Fatal("reading a saved report must not start another paid generation")
	}
}

func TestAnalysisReportsStaySavedUntilExplicitRefresh(t *testing.T) {
	for _, operation := range []string{
		"correlation_analysis", "block_correlation_analysis", "program_evaluation",
		"block_program_evaluation", "multi_block_comparison_analysis",
	} {
		t.Run(operation, func(t *testing.T) {
			h := newHarness(t)
			args := map[string]any{"pk": "athlete_1"}
			switch operation {
			case "correlation_analysis":
				args["block"], args["weeks"] = "current", 4
			case "block_correlation_analysis", "block_program_evaluation":
				args["block_key"] = "current"
			case "multi_block_comparison_analysis":
				args["block_keys"] = []any{"block_1", "current"}
			}
			first, err := h.call(t, operation, args, person())
			if err != nil {
				t.Fatal(err)
			}
			id := asMap(t, first.Body)["generation_id"].(string)
			if err := h.svc.store("athlete_1").Complete(context.Background(), id, map[string]any{"summary": "saved"}, 1); err != nil {
				t.Fatal(err)
			}
			for _, change := range []func(){
				func() { _ = h.redis.Set("pl:analysis-version:athlete_1", "12") },
				func() { *h.clock = h.clock.AddDate(0, 0, 30) },
			} {
				change()
				for _, cacheOnly := range []bool{true, false} {
					args["cache_only"] = cacheOnly
					response, err := h.call(t, operation, args, person())
					if err != nil {
						t.Fatal(err)
					}
					body := asMap(t, response.Body)
					if response.Status != http.StatusOK || body["cached"] != true || body["summary"] != "saved" || h.coach.count() != 1 {
						t.Fatalf("data changes and time must not invalidate an analysis: %v (%d jobs)", body, h.coach.count())
					}
				}
			}
			args["refresh"] = true
			refreshed, err := h.call(t, operation, args, person())
			if err != nil || asMap(t, refreshed.Body)["generation_id"] != id || h.coach.count() != 2 {
				t.Fatalf("explicit refresh must replace the saved report: %v %v", refreshed, err)
			}
			record, err := h.svc.store("athlete_1").Get(context.Background(), id)
			if err != nil || record.Attempt != 2 || record.Status == generation.StatusDone {
				t.Fatalf("explicit refresh must start another attempt: %+v %v", record, err)
			}
		})
	}
}

func TestTrainingChangesDoNotDuplicateRunningAnalysis(t *testing.T) {
	h := newHarness(t)
	_, first := submitBlockCorrelation(t, h, nil)
	_ = h.redis.Set("pl:analysis-version:athlete_1", "1")
	_, next := submitBlockCorrelation(t, h, nil)
	if next["generation_id"] != first["generation_id"] || next["job_id"] != first["job_id"] || h.coach.count() != 1 {
		t.Fatalf("a data update must not duplicate paid work already running: %v", next)
	}
}

func TestSavedAnalysisDoesNotLeakAcrossBlocksOrAccessScopes(t *testing.T) {
	for _, change := range []string{"new block", "reduced access", "revoked access", "different athlete"} {
		t.Run(change, func(t *testing.T) {
			h := newHarness(t)
			_, first := submitBlockCorrelation(t, h, map[string]any{"block_key": "current"})
			id := first["generation_id"].(string)
			if err := h.svc.store("athlete_1").Complete(context.Background(), id, map[string]any{"summary": "private"}, 1); err != nil {
				t.Fatal(err)
			}
			caller := person()
			switch change {
			case "new block":
				h.source.blocks[2]["startDate"] = "2026-12-01"
			case "reduced access":
				h.access.access = map[string]any{"permissions": []any{}}
			case "revoked access":
				h.access.deny = http.StatusForbidden
			case "different athlete":
				caller.Athlete = "athlete_2"
			}
			response, err := h.call(t, "block_correlation_analysis", map[string]any{
				"pk": caller.Athlete, "block_key": "current", "cache_only": true,
			}, caller)
			if change == "revoked access" {
				if statusOf(t, err) != http.StatusForbidden {
					t.Fatalf("revoked access must deny cached reads: %v", err)
				}
			} else if err != nil || asMap(t, response.Body)["cache_miss"] != true {
				t.Fatalf("must not return another scope's saved report: %v %v", response, err)
			}
			if h.coach.count() != 1 {
				t.Fatal("a cache-only miss must not generate a report")
			}
		})
	}
}
