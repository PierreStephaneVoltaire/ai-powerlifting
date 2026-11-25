package service

import (
	"context"
	"testing"

	"powerlifting/liftprofiles/internal/apperr"
	"powerlifting/liftprofiles/internal/auth"
	"powerlifting/liftprofiles/internal/cache"
	"powerlifting/liftprofiles/internal/contract"
	"powerlifting/liftprofiles/internal/execution"
	"powerlifting/liftprofiles/internal/profile"
)

type allowAccess struct{}

func (allowAccess) Fetch(_ context.Context, _ string, _ map[string]any, caller auth.Caller) error {
	if caller.Person == "" || caller.Athlete == "" {
		return apperr.Forbidden("scope required")
	}
	return nil
}

type noCache struct{}

func (noCache) Lookup(context.Context, string, string, cache.Request) (map[string]any, string, bool) {
	return nil, "", false
}
func (noCache) Remember(context.Context, string, string, cache.Request, map[string]any) {}

func TestAIExecutionIsBoundToPersonAndAthlete(t *testing.T) {
	registry, err := contract.Load()
	if err != nil {
		t.Fatal(err)
	}
	defs, err := profile.Defaults()
	if err != nil {
		t.Fatal(err)
	}
	svc := Service{Registry: registry, Access: allowAccess{}, Executions: execution.New(noCache{}), Handlers: map[string]func(context.Context, map[string]any, execution.Inferer) (any, error){"lift_profile_suggest": Suggest(defs)}}
	caller := auth.Caller{Person: "person", Athlete: "athlete", TurnID: "job"}
	response, err := svc.Call(context.Background(), "lift_profile_suggest", map[string]any{"lift": "bench", "description": "wide"}, caller)
	if err != nil {
		t.Fatal(err)
	}
	body := response.Body.(map[string]any)
	if body["status"] != "needs_inference" {
		t.Fatalf("got %#v", body)
	}
	id := body["execution_id"].(string)
	_, err = svc.Resume(context.Background(), id, map[string]any{}, auth.Caller{Person: "other", Athlete: "athlete", TurnID: "job"})
	if err == nil {
		t.Fatal("different person resumed execution")
	}
	answer := map[string]any{}
	for _, field := range defs["bench"] {
		answer[field.Key] = nil
	}
	answer["grip_width"] = "wide"
	answer["volume_tolerance"] = nil
	response, err = svc.Resume(context.Background(), id, map[string]any{"challenge_id": body["challenge_id"], "content": answer}, caller)
	if err != nil {
		t.Fatal(err)
	}
	completed := response.Body.(map[string]any)
	if completed["status"] != "succeeded" || completed["result"].(map[string]any)["options"].(map[string]any)["grip_width"] != "wide" {
		t.Fatalf("got %#v", completed)
	}
}
