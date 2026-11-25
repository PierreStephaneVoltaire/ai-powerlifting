package service

import (
	"context"
	"testing"

	"powerlifting/templates/internal/auth"
	"powerlifting/templates/internal/library"
)

type blockSource struct{}

func (blockSource) ProgramContext(context.Context, string) (map[string]any, error) { return nil, nil }
func (blockSource) Glossary(context.Context, string) ([]map[string]any, error)     { return nil, nil }
func (blockSource) Program(context.Context, string) (map[string]any, error) {
	return map[string]any{"sk": "program#1", "current_maxes": map[string]any{"Squat": 100}, "sessions": []any{map[string]any{
		"date": "2026-11-23", "day": "Monday", "week_number": 1, "planned_exercises": []any{map[string]any{"name": "Squat", "glossary_id": "squat", "sets": 3, "reps": 5, "kg": 80}},
	}}}, nil
}

type templateBackend struct{ item map[string]any }

func (b *templateBackend) Get(context.Context, string, string) (map[string]any, error) {
	return b.item, nil
}
func (b *templateBackend) Commit(_ context.Context, item map[string]any, _ bool, _ *library.ImportClaim, _ map[string]any, _ string) error {
	b.item = item
	return nil
}

type applyingDomain struct {
	operation string
	args      map[string]any
}

func (d *applyingDomain) Call(_ context.Context, _ string, operation string, args map[string]any, _ auth.Caller) (map[string]any, error) {
	d.operation, d.args = operation, args
	return map[string]any{"status": "applied"}, nil
}

func TestApplyExistingBlockDelegatesSessionMutation(t *testing.T) {
	for _, target := range []string{"append", "replace_incomplete"} {
		t.Run(target, func(t *testing.T) {
			domain := &applyingDomain{}
			backend := &templateBackend{item: map[string]any{"sessions": []any{map[string]any{"week_number": 1, "day_of_week": "Monday", "exercises": []any{}}}}}
			s := &Service{Sources: blockSource{}, Domain: domain, Library: library.Library{Backend: backend}}
			result, err := s.confirmTemplate(context.Background(), map[string]any{"sk": "template#1", "target": target, "block_id": "block#1", "start_date": "2026-11-23"}, auth.Caller{Athlete: "athlete"}, nil)
			if err != nil {
				t.Fatal(err)
			}
			if domain.operation != "template_apply_sessions" || domain.args["target"] != target || domain.args["block_id"] != "block#1" || result.(map[string]any)["status"] != "applied" {
				t.Fatalf("operation %s args %#v result %#v", domain.operation, domain.args, result)
			}
			sessions, ok := domain.args["sessions"].([]map[string]any)
			if !ok || len(sessions) != 1 || sessions[0]["date"] != "2026-11-23" {
				t.Fatalf("sessions %#v", domain.args["sessions"])
			}
		})
	}
}

func TestCreateFromBlockPreparesResolutionMetadata(t *testing.T) {
	backend := &templateBackend{}
	s := &Service{Sources: blockSource{}, Library: library.Library{Backend: backend}}
	_, err := s.call(context.Background(), "template_create_from_block", map[string]any{"name": "Block"}, auth.Caller{Person: "alice", Athlete: "alice"}, []string{"alice"})
	if err != nil {
		t.Fatal(err)
	}
	maxes, ok := backend.item["required_maxes"].([]string)
	if !ok || len(maxes) != 1 || maxes[0] != "squat" {
		t.Fatalf("required maxes: %#v", backend.item["required_maxes"])
	}
	resolution, ok := backend.item["glossary_resolution"].(map[string]any)
	if !ok || resolution["resolution_status"] != "resolved" {
		t.Fatalf("resolution: %#v", backend.item["glossary_resolution"])
	}
}

func TestCreateBlankPreparesMetadataAndUsesAuthor(t *testing.T) {
	backend := &templateBackend{}
	s := &Service{Library: library.Library{Backend: backend}}
	_, err := s.call(context.Background(), "template_create_blank", map[string]any{"name": "Blank", "author": "Coach"}, auth.Caller{Person: "alice"}, []string{"alice"})
	if err != nil {
		t.Fatal(err)
	}
	meta := backend.item["meta"].(map[string]any)
	resolution := backend.item["glossary_resolution"].(map[string]any)
	if meta["author"] != "Coach" || resolution["resolution_status"] != "resolved" || len(backend.item["required_maxes"].([]string)) != 0 {
		t.Fatalf("template: %#v", backend.item)
	}
}
