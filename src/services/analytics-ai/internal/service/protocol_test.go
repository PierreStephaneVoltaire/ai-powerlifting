package service

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"strings"
	"testing"
	"time"

	"powerlifting/analytics-ai/internal/apperr"
	"powerlifting/analytics-ai/internal/auth"
	"powerlifting/analytics-ai/internal/execution"
	"powerlifting/analytics-ai/internal/generation"
)

var correlationAnswer = map[string]any{
	"findings": []any{map[string]any{"exercise": "Leg Press", "lift": "squat", "correlation_direction": "positive", "strength": "moderate", "reasoning": "Quads.", "caveat": ""}},
	"summary":  "Leg press tracks squat.",
}

func statusOf(t *testing.T, err error) int {
	t.Helper()
	var failure *apperr.Error
	if !errors.As(err, &failure) {
		t.Fatalf("expected apperr, got %v", err)
	}
	return failure.Status
}

func submitBlockCorrelation(t *testing.T, h *harness, extra map[string]any) (Response, map[string]any) {
	t.Helper()
	arguments := map[string]any{"pk": "athlete_1", "block_key": "block_1"}
	for key, value := range extra {
		arguments[key] = value
	}
	response, err := h.call(t, "block_correlation_analysis", arguments, person())
	if err != nil {
		t.Fatal(err)
	}
	return response, asMap(t, response.Body)
}

func submittedArguments(t *testing.T, h *harness, index int) map[string]any {
	t.Helper()
	payload := asMap(t, h.coach.submitted[index].Body["payload"])
	return asMap(t, payload["arguments"])
}

func TestSubmitSendsOnlyIdentityHeadersAndExecutionPayload(t *testing.T) {
	h := newHarness(t)
	response, body := submitBlockCorrelation(t, h, nil)
	if response.Status != http.StatusAccepted || body["job_id"] != "job_1" || body["status"] != "running" {
		t.Fatalf("unexpected response %+v", response)
	}
	generationID, _ := body["generation_id"].(string)
	if len(generationID) != 64 {
		t.Fatalf("generation id must be a sha256 hex digest: %q", generationID)
	}
	sent := h.coach.submitted[0]
	for name := range sent.Header {
		lower := strings.ToLower(name)
		if strings.HasPrefix(lower, "x-") && lower != "x-person-pk" && lower != "x-athlete-pk" {
			t.Errorf("coach must only receive identity headers, got %s", name)
		}
	}
	if sent.Header.Get("X-Person-Pk") != "person_1" || sent.Header.Get("X-Athlete-Pk") != "athlete_1" || sent.Header.Get("Authorization") != "" {
		t.Fatalf("unexpected headers %v", sent.Header)
	}
	if sent.Body["conversation_id"] != "powerlifting:athlete_1:"+generationID+":1" || sent.Body["kind"] != "domain" {
		t.Fatalf("unexpected job envelope %v", sent.Body)
	}
	payload := asMap(t, sent.Body["payload"])
	if payload["domain"] != "analytics-ai" || payload["operation"] != "block_correlation_analysis" || payload["athlete"] != "athlete_1" ||
		payload["generation_id"] != generationID || payload["generation_attempt"] != float64(1) {
		t.Fatalf("unexpected payload %v", payload)
	}
	arguments := submittedArguments(t, h, 0)
	if arguments["refresh"] != true || arguments["cache_only"] != false || arguments["block_key"] != "block_1" {
		t.Fatalf("unexpected arguments %v", arguments)
	}
	for _, reserved := range []string{"_access", "_person_pk", "_if_job_id"} {
		if _, present := arguments[reserved]; present {
			t.Errorf("%s must not reach the coach", reserved)
		}
	}
	source := asMap(t, arguments["_report_source"])
	if _, present := source["access_requirements"]; !present {
		t.Fatalf("report source must carry access requirements: %v", source)
	}
	record, _ := h.svc.store("athlete_1").Get(context.Background(), generationID)
	if record.Status != "starting" || record.JobID != "job_1" || record.Attempt != 1 || record.Owner != "person_1" {
		t.Fatalf("unexpected record %+v", record)
	}
}

func TestResubmitReturnsTheRunningGeneration(t *testing.T) {
	h := newHarness(t)
	_, first := submitBlockCorrelation(t, h, nil)
	response, second := submitBlockCorrelation(t, h, nil)
	if h.coach.count() != 1 || second["generation_id"] != first["generation_id"] || second["job_id"] != "job_1" || response.Status != http.StatusAccepted {
		t.Fatalf("a running generation must not be resubmitted: %v", second)
	}
	miss, body := submitBlockCorrelation(t, h, map[string]any{"cache_only": true})
	if body["cache_miss"] != true || body["cached"] != false || body["status"] != "starting" || miss.Status != http.StatusAccepted {
		t.Fatalf("cache_only must report the pending generation: %v", body)
	}
}

func TestCoachRejectionFailsTheGeneration(t *testing.T) {
	h := newHarness(t)
	h.coach.reject = http.StatusTooManyRequests
	_, err := h.call(t, "block_correlation_analysis", map[string]any{"pk": "athlete_1", "block_key": "block_1"}, person())
	if statusOf(t, err) != http.StatusTooManyRequests {
		t.Fatalf("got %v", err)
	}
	h.coach.reject = 0
	response, body := submitBlockCorrelation(t, h, nil)
	record, _ := h.svc.store("athlete_1").Get(context.Background(), body["generation_id"].(string))
	if record.Status != "failed" || response.Status != http.StatusAccepted && record.Attempt != 1 {
		t.Fatalf("a failed generation needs an explicit refresh: %+v %v", record, body)
	}
	_, refreshed := submitBlockCorrelation(t, h, map[string]any{"refresh": true})
	if refreshed["job_id"] != "job_1" || h.coach.count() != 1 {
		t.Fatalf("refresh must resubmit: %v", refreshed)
	}
}

func callbackArguments(t *testing.T, h *harness) (map[string]any, string, int) {
	t.Helper()
	_, body := submitBlockCorrelation(t, h, nil)
	arguments := submittedArguments(t, h, 0)
	return arguments, body["generation_id"].(string), 1
}

func startCallback(t *testing.T, h *harness) (map[string]any, string) {
	t.Helper()
	arguments, generationID, attempt := callbackArguments(t, h)
	response, err := h.call(t, "block_correlation_analysis", arguments, inCoachJob(person(), generationID, attempt))
	if err != nil {
		t.Fatal(err)
	}
	return asMap(t, response.Body), generationID
}

func TestFullProtocolSubmitChallengeResumeComplete(t *testing.T) {
	h := newHarness(t)
	challenge, generationID := startCallback(t, h)
	if challenge["status"] != "needs_inference" || challenge["instruction"] != execution.Instruction {
		t.Fatalf("expected a native delegation challenge: %v", challenge)
	}
	messages := challenge["messages"].([]any)
	tools := challenge["tools"].([]any)
	function := asMap(t, asMap(t, tools[0])["function"])
	if len(messages) != 2 || function["name"] != "report_correlation_findings" || challenge["response_format"] != nil {
		t.Fatalf("unexpected challenge %v", challenge)
	}
	if !strings.Contains(asMap(t, messages[1])["content"].(string), "## Weekly e1RM Estimates (kg)") {
		t.Fatal("user message must carry the rendered correlation data")
	}

	executionID := challenge["execution_id"].(string)
	resume := map[string]any{"challenge_id": challenge["challenge_id"], "content": correlationAnswer}
	response, err := h.svc.Resume(context.Background(), executionID, resume, inCoachJob(person(), generationID, 1))
	if err != nil {
		t.Fatal(err)
	}
	done := asMap(t, response.Body)
	result := asMap(t, done["result"])
	if done["status"] != "succeeded" || result["summary"] != "Leg press tracks squat." || result["cached"] != false || fmt.Sprint(result["weeks"]) != "8" || result["window_start"] != "2026-01-05" {
		t.Fatalf("unexpected completion %v", done)
	}

	record, _ := h.svc.store("athlete_1").Get(context.Background(), generationID)
	if record.Status != generation.StatusDone || record.Shards != 1 {
		t.Fatalf("generation must be persisted: %+v", record)
	}
	cachedResponse, body := submitBlockCorrelation(t, h, map[string]any{"cache_only": true})
	if cachedResponse.Status != http.StatusOK || body["cached"] != true || body["summary"] != "Leg press tracks squat." {
		t.Fatalf("cache_only must serve the saved report: %v", body)
	}
	status, err := h.svc.GenerationStatus(context.Background(), generationID, person())
	if err != nil || status["status"] != "succeeded" || asMap(t, status["result"])["summary"] != "Leg press tracks squat." {
		t.Fatalf("status: %v %v", status, err)
	}

	again, err := h.call(t, "block_correlation_analysis", map[string]any{"pk": "athlete_1", "block_key": "block_1", "refresh": true}, person())
	if err != nil || h.coach.count() != 2 || asMap(t, again.Body)["job_id"] == nil {
		t.Fatalf("refresh must start a new attempt: %v %v", again, err)
	}
	if submitted := h.coach.submitted[1].Body["payload"].(map[string]any); submitted["generation_attempt"] != float64(2) {
		t.Fatalf("attempt must increase: %v", submitted)
	}
	prompt := inCoachJob(person(), generationID, 2)
	second, err := h.call(t, "block_correlation_analysis", submittedArguments(t, h, 1), prompt)
	if err != nil {
		t.Fatal(err)
	}
	if body := asMap(t, second.Body); body["status"] != "succeeded" {
		t.Fatalf("identical prompts must be answered from the exact cache without a challenge: %v", body)
	}
}

func TestBadAnswerIsRejectedAndChallengeStaysOpen(t *testing.T) {
	h := newHarness(t)
	challenge, generationID := startCallback(t, h)
	caller := inCoachJob(person(), generationID, 1)
	executionID, challengeID := challenge["execution_id"].(string), challenge["challenge_id"].(string)

	_, err := h.svc.Resume(context.Background(), executionID, map[string]any{"challenge_id": challengeID, "content": map[string]any{"findings": "nope"}}, caller)
	if statusOf(t, err) != http.StatusUnprocessableEntity {
		t.Fatalf("schema violations must be rejected: %v", err)
	}
	_, err = h.svc.Resume(context.Background(), executionID, map[string]any{"challenge_id": challengeID, "content": "not json"}, caller)
	if statusOf(t, err) != http.StatusUnprocessableEntity {
		t.Fatalf("malformed JSON must be rejected: %v", err)
	}
	_, err = h.svc.Resume(context.Background(), executionID, map[string]any{"challenge_id": "stale", "content": correlationAnswer}, caller)
	if statusOf(t, err) != http.StatusConflict {
		t.Fatalf("a stale challenge must conflict: %v", err)
	}
	text, _ := json.Marshal(correlationAnswer)
	response, err := h.svc.Resume(context.Background(), executionID, map[string]any{"challenge_id": challengeID, "content": string(text)}, caller)
	if err != nil || asMap(t, response.Body)["status"] != "succeeded" {
		t.Fatalf("the original challenge must still be answerable: %v %v", response, err)
	}
}

func TestResumeIsBoundToTheExecutionOwner(t *testing.T) {
	h := newHarness(t)
	challenge, generationID := startCallback(t, h)
	executionID := challenge["execution_id"].(string)
	body := map[string]any{"challenge_id": challenge["challenge_id"], "content": correlationAnswer}

	stranger := inCoachJob(person(), generationID, 1)
	stranger.Person = "person_2"
	if _, err := h.svc.Resume(context.Background(), executionID, body, stranger); statusOf(t, err) != http.StatusForbidden {
		t.Fatalf("another person must be refused: %v", err)
	}
	otherJob := inCoachJob(person(), generationID, 1)
	otherJob.TurnID = "turn_other"
	if _, err := h.svc.Resume(context.Background(), executionID, body, otherJob); statusOf(t, err) != http.StatusConflict {
		t.Fatalf("another job must conflict: %v", err)
	}
	if _, err := h.svc.Resume(context.Background(), "missing", body, inCoachJob(person(), generationID, 1)); statusOf(t, err) != http.StatusConflict {
		t.Fatalf("unknown executions must conflict: %v", err)
	}
	if got := h.access.calls[len(h.access.calls)-1]; got != "domain_resume" {
		t.Fatalf("resume must be authorized as domain_resume, got %s", got)
	}
}

func TestDeadlineExpiryMarksTheGenerationFailed(t *testing.T) {
	h := newHarness(t)
	h.svc.Executions.Deadline = 80 * time.Millisecond
	challenge, generationID := startCallback(t, h)
	time.Sleep(250 * time.Millisecond)
	_, err := h.svc.Resume(context.Background(), challenge["execution_id"].(string), map[string]any{}, inCoachJob(person(), generationID, 1))
	if statusOf(t, err) != http.StatusConflict || !strings.Contains(err.Error(), "timed out") {
		t.Fatalf("an expired execution must report uncertainty: %v", err)
	}
	record, _ := h.svc.store("athlete_1").Get(context.Background(), generationID)
	if record.Status != "failed" || !strings.Contains(record.Error.(string), "timed out") {
		t.Fatalf("generation must be failed: %+v", record)
	}
	if _, err := h.svc.Resume(context.Background(), challenge["execution_id"].(string), map[string]any{}, inCoachJob(person(), generationID, 1)); statusOf(t, err) != http.StatusConflict {
		t.Fatalf("a finished execution cannot be resumed again: %v", err)
	}
}

func TestPollWithoutAnswerKeepsReportingTheChallenge(t *testing.T) {
	h := newHarness(t)
	challenge, generationID := startCallback(t, h)
	again, err := h.svc.Resume(context.Background(), challenge["execution_id"].(string), map[string]any{}, inCoachJob(person(), generationID, 1))
	if err != nil || asMap(t, again.Body)["challenge_id"] != challenge["challenge_id"] {
		t.Fatalf("polling must return the pending challenge: %v %v", again, err)
	}
}

func TestInsufficientBlocksNeverReachTheCoach(t *testing.T) {
	h := newHarness(t)
	for name, check := range map[string]string{"analytics.correlation": "Insufficient data for correlation analysis.", "analytics.block_evaluation": "At least 4 completed weeks"} {
		response, err := h.call(t, name, map[string]any{"pk": "athlete_1", "blockKey": "block_short"}, person())
		if err != nil {
			t.Fatal(err)
		}
		body := asMap(t, response.Body)
		if body["insufficient_data"] != true || response.Status != http.StatusOK || !strings.Contains(body["summary"].(string)+body["insufficient_data_reason"].(string), check) {
			t.Fatalf("%s: %v", name, body)
		}
	}
	if h.coach.count() != 0 {
		t.Fatal("insufficient data needs no inference")
	}
	if _, err := h.call(t, "analytics.correlation", map[string]any{"pk": "athlete_1", "blockKey": "nope"}, person()); statusOf(t, err) != http.StatusNotFound {
		t.Fatalf("unknown blocks must 404: %v", err)
	}
}

func TestBlockWrappersDelegateToTheGenerationFlow(t *testing.T) {
	h := newHarness(t)
	response, err := h.call(t, "analytics.block_evaluation", map[string]any{"pk": "athlete_1", "blockKey": "block_1"}, person())
	if err != nil || response.Status != http.StatusAccepted || asMap(t, response.Body)["generation_id"] == nil {
		t.Fatalf("got %+v %v", response, err)
	}
	payload := asMap(t, h.coach.submitted[0].Body["payload"])
	if payload["operation"] != "block_program_evaluation" || asMap(t, payload["arguments"])["block_key"] != "block_1" {
		t.Fatalf("the wrapper must submit the underlying operation: %v", payload)
	}
	miss, err := h.call(t, "analytics.correlation", map[string]any{"pk": "athlete_1", "blockKey": "block_1", "cacheOnly": true}, person())
	if err != nil || asMap(t, miss.Body)["cache_miss"] != true || h.coach.count() != 1 {
		t.Fatalf("cacheOnly must not submit: %v %v", miss, err)
	}
}

func TestCompareAIReturnsTheDeterministicBodyAndAGenerationStub(t *testing.T) {
	h := newHarness(t)
	response, err := h.call(t, "analytics.compare_ai", map[string]any{"pk": "athlete_1"}, person())
	if err != nil || response.Status != http.StatusOK {
		t.Fatalf("got %+v %v", response, err)
	}
	body := asMap(t, response.Body)
	report := asMap(t, body["report"])
	if fmt.Sprint(body["schemaVersion"]) != "6" || report["generation_id"] == nil || len(body["sourceFingerprint"].(string)) != 64 || len(body["selectedBlockKeys"].([]any)) != 2 {
		t.Fatalf("unexpected comparison %v", body)
	}
	payload := asMap(t, h.coach.submitted[0].Body["payload"])
	if payload["operation"] != "multi_block_comparison_analysis" {
		t.Fatalf("got %v", payload)
	}
	readOnly, err := h.call(t, "analytics.compare_ai", map[string]any{"pk": "athlete_1", "read_only": true, "refresh": true}, person())
	if err != nil || asMap(t, asMap(t, readOnly.Body)["report"])["generation_id"] == nil || h.coach.count() != 1 {
		t.Fatalf("read_only must not submit or refresh: %v %v", readOnly, err)
	}
}

var comparisonAnswer = map[string]any{
	"overall_summary": "Blocks compared.", "similarities": []any{}, "differences": []any{}, "what_works": []any{}, "what_does_not_work": []any{},
	"lift_specific_insights": []any{}, "multi_block_exercise_roi": []any{}, "cross_block_correlations": []any{}, "pattern_detections": []any{},
	"volume_dose_response": []any{}, "bodyweight_relationships": []any{}, "training_day_frequency": []any{}, "best_value_blocks": []any{},
	"projection_accuracy": []any{}, "progress_dropoff_points": []any{}, "fatigue_patterns": []any{}, "data_limits": []any{},
}

func runComparison(t *testing.T, h *harness, blockKeys []any) {
	t.Helper()
	arguments := map[string]any{"pk": "athlete_1", "block_keys": blockKeys}
	response, err := h.call(t, "multi_block_comparison_analysis", arguments, person())
	if err != nil {
		t.Fatal(err)
	}
	generationID := asMap(t, response.Body)["generation_id"].(string)
	index := h.coach.count() - 1
	challenge, err := h.call(t, "multi_block_comparison_analysis", submittedArguments(t, h, index), inCoachJob(person(), generationID, 1))
	if err != nil {
		t.Fatal(err)
	}
	body := asMap(t, challenge.Body)
	user := asMap(t, body["messages"].([]any)[1])["content"].(string)
	if !strings.Contains(user, `"selected_block_keys"`) || strings.Contains(user, "generated_at") {
		t.Fatalf("payload must list the selected blocks without runtime markers: %s", user)
	}
	_, err = h.svc.Resume(context.Background(), body["execution_id"].(string), map[string]any{"challenge_id": body["challenge_id"], "content": comparisonAnswer}, inCoachJob(person(), generationID, 1))
	if err != nil {
		t.Fatal(err)
	}
}

func TestAllBlocksNarrativeIsSavedThroughExport(t *testing.T) {
	h := newHarness(t)
	runComparison(t, h, []any{})
	if len(h.exporter.reports) != 1 {
		t.Fatalf("expected one export, got %d", len(h.exporter.reports))
	}
	saved := h.exporter.reports[0]
	if saved.Narrative["overall_summary"] != "Blocks compared." || saved.Report["athlete"] != "athlete_1" || len(saved.BlockKeys) != 2 || saved.GeneratedAt == "" {
		t.Fatalf("unexpected export %+v", saved)
	}
}

func TestExplicitBlockSelectionIsNotExported(t *testing.T) {
	h := newHarness(t)
	runComparison(t, h, []any{"block_1"})
	if len(h.exporter.reports) != 0 {
		t.Fatal("only the all-blocks narrative feeds the lifetime report")
	}
}

func TestGenerationStatusReconcilesWithTheCoachJob(t *testing.T) {
	h := newHarness(t)
	_, body := submitBlockCorrelation(t, h, nil)
	generationID := body["generation_id"].(string)
	running, err := h.svc.GenerationStatus(context.Background(), generationID, person())
	if err != nil || running["status"] != "starting" || running["job_id"] != "job_1" {
		t.Fatalf("got %v %v", running, err)
	}
	h.coach.jobStatus = "succeeded"
	reconciled, err := h.svc.GenerationStatus(context.Background(), generationID, person())
	if err != nil || reconciled["status"] != "uncertain" || asMap(t, reconciled["error"])["message"] == nil {
		t.Fatalf("a finished job without a saved result is uncertain: %v %v", reconciled, err)
	}
	if _, err := h.svc.GenerationStatus(context.Background(), "unknown", person()); statusOf(t, err) != http.StatusNotFound {
		t.Fatalf("got %v", err)
	}
	if _, err := h.svc.GenerationStatus(context.Background(), generationID, auth.Caller{Person: "person_1"}); statusOf(t, err) != http.StatusForbidden {
		t.Fatalf("an athlete is required: %v", err)
	}
}

func TestStartingGenerationWithoutJobBecomesUncertain(t *testing.T) {
	h := newHarness(t)
	store := h.svc.store("athlete_1")
	if _, _, err := store.Reserve(context.Background(), "orphan", "block_correlation_analysis", "person_1", false, map[string]any{"permissions": []any{}, "competition_ids": []any{}}); err != nil {
		t.Fatal(err)
	}
	*h.clock = h.clock.Add(2 * time.Minute)
	status, err := h.svc.GenerationStatus(context.Background(), "orphan", person())
	if err != nil || status["status"] != "uncertain" {
		t.Fatalf("got %v %v", status, err)
	}
}

func TestSavedReportsRequireCurrentAccess(t *testing.T) {
	h := newHarness(t)
	store := h.svc.store("athlete_1")
	if _, _, err := store.Reserve(context.Background(), "legacy", "block_correlation_analysis", "person_1", false, nil); err != nil {
		t.Fatal(err)
	}
	h.access.access = auth.Access{"is_self": false}
	if _, err := h.svc.GenerationStatus(context.Background(), "legacy", person()); statusOf(t, err) != http.StatusForbidden {
		t.Fatalf("records without requirements need regeneration for non-owners: %v", err)
	}
}

func TestRegenerateRefreshesBothReports(t *testing.T) {
	h := newHarness(t)
	correlation, evaluation := h.svc.Regenerate(context.Background(), person(), "block_1")
	if !correlation || !evaluation || h.coach.count() != 2 {
		t.Fatalf("got %v %v with %d jobs", correlation, evaluation, h.coach.count())
	}
	operations := []any{asMap(t, h.coach.submitted[0].Body["payload"])["operation"], asMap(t, h.coach.submitted[1].Body["payload"])["operation"]}
	if operations[0] != "block_correlation_analysis" || operations[1] != "block_program_evaluation" {
		t.Fatalf("got %v", operations)
	}
	h.access.deny = http.StatusForbidden
	correlation, evaluation = h.svc.Regenerate(context.Background(), person(), "block_1")
	if correlation || evaluation {
		t.Fatal("denied access must be reported through the flags")
	}
}

func TestBlockEvaluationBuildsItsPayloadFromTheBlockData(t *testing.T) {
	h := newHarness(t)
	response, err := h.call(t, "analytics.block_evaluation", map[string]any{"pk": "athlete_1", "blockKey": "block_1"}, person())
	if err != nil {
		t.Fatal(err)
	}
	generationID := asMap(t, response.Body)["generation_id"].(string)
	started, err := h.call(t, "block_program_evaluation", submittedArguments(t, h, 0), inCoachJob(person(), generationID, 1))
	if err != nil {
		t.Fatal(err)
	}
	challenge := asMap(t, started.Body)
	user := asMap(t, challenge["messages"].([]any)[1])["content"].(string)
	var payload map[string]any
	if err := json.Unmarshal([]byte(user), &payload); err != nil {
		t.Fatalf("the evaluation message is JSON: %v", err)
	}
	summary := asMap(t, payload["full_block_summary"])
	if summary["completed_sessions"] != float64(5) || len(payload["completed_sessions"].([]any)) != 5 || asMap(t, payload["weekly_analysis"])["fatigue_index"] != 1.5 {
		t.Fatalf("unexpected payload %v", payload)
	}
	answer := map[string]any{
		"stance": "continue", "summary": "Steady.", "what_is_working": []any{}, "what_is_not_working": []any{}, "competition_alignment": []any{},
		"goal_status": []any{}, "competition_strategy": []any{}, "small_changes": []any{}, "external_factors": []any{}, "monitoring_focus": []any{},
		"weight_class_strategy": map[string]any{"recommendation": "stay", "recommended_weight_class_kg": nil, "viable_options": []any{}}, "conclusion": "Carry on.",
	}
	done, err := h.svc.Resume(context.Background(), challenge["execution_id"].(string), map[string]any{"challenge_id": challenge["challenge_id"], "content": answer}, inCoachJob(person(), generationID, 1))
	if err != nil {
		t.Fatal(err)
	}
	result := asMap(t, asMap(t, done.Body)["result"])
	if result["stance"] != "continue" || result["window_start"] != "2026-01-05" || fmt.Sprint(result["weeks"]) != "5" {
		t.Fatalf("unexpected result %v", result)
	}
	cached, err := h.call(t, "analytics.block_evaluation", map[string]any{"pk": "athlete_1", "blockKey": "block_1", "cacheOnly": true}, person())
	if err != nil || asMap(t, cached.Body)["stance"] != "continue" || cached.Status != http.StatusOK {
		t.Fatalf("the wrapper must serve the saved evaluation: %v %v", cached, err)
	}
}
