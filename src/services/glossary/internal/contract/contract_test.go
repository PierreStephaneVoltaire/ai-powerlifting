package contract

import "testing"

func TestEveryOperationLoadsWithDeclaredExecution(t *testing.T) {
	registry, err := Load()
	if err != nil {
		t.Fatal(err)
	}
	ai := map[string]bool{"glossary_estimate_batch": true, "glossary_generic_estimate": true}
	operations := registry.All()
	if len(operations) != 8 {
		t.Fatalf("%d operations", len(operations))
	}
	for _, operation := range operations {
		if (operation.Execution == ExecutionAI) != ai[operation.Name] {
			t.Errorf("%s execution %s", operation.Name, operation.Execution)
		}
		if operation.InputSchema["properties"].(map[string]any)["pk"] == nil {
			t.Errorf("%s has no pk input", operation.Name)
		}
	}
}

func TestResultSchemaCarriesPersonalAndGenericFatigue(t *testing.T) {
	registry, _ := Load()
	operation, _ := registry.Get("exercise_get_glossary")
	result := map[string]any{"pk": "a", "updated_at": "t", "exercises": []any{map[string]any{
		"id": "e", "name": "Squat", "fatigue_profile_personalized": true, "generic_status": "ready", "generic_fatigue_profile": map[string]any{"axial": 0.5},
	}}}
	if err := operation.ValidateResult(result); err != nil {
		t.Fatal(err)
	}
	result["exercises"].([]any)[0].(map[string]any)["generic_status"] = "bogus"
	if operation.ValidateResult(result) == nil {
		t.Fatal("bad generic_status accepted")
	}
}
