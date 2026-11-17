package service

import (
	"testing"

	"powerlifting/profile/internal/value"
)

func TestAnonymousBlockAnalysisAccess(t *testing.T) {
	for _, tc := range []struct {
		name       string
		visibility string
		domains    []any
		operation  string
		arguments  map[string]any
		allowed    bool
	}{
		{"published cold read", "public", []any{"analytics"}, "analytics.blocks_get", map[string]any{"cacheOnly": false}, true},
		{"published default read", "public", []any{"analytics"}, "analytics.blocks_get", map[string]any{}, true},
		{"published cached read", "public", []any{"analytics"}, "analytics.blocks_get", map[string]any{"cacheOnly": true}, true},
		{"private profile", "private", []any{"analytics"}, "analytics.blocks_get", map[string]any{}, false},
		{"unpublished analysis", "public", []any{"program", "sessions"}, "analytics.blocks_get", map[string]any{}, false},
		{"forced refresh", "public", []any{"analytics"}, "analytics.blocks_get", map[string]any{"refresh": true}, false},
		{"cached forced refresh", "public", []any{"analytics"}, "analytics.blocks_get", map[string]any{"cacheOnly": true, "refresh": true}, false},
		{"AI generation", "public", []any{"analytics"}, "analytics.block_evaluation", map[string]any{}, false},
		{"AI cached read", "public", []any{"analytics"}, "analytics.block_evaluation", map[string]any{"cacheOnly": true}, true},
	} {
		t.Run(tc.name, func(t *testing.T) {
			h := newHarness(t, options{})
			h.seed("user", value.Item{
				"pk": "athlete", "mapped_pk": "athlete", "username": "athlete", "roles": []any{"athlete"},
				"profile_visibility": tc.visibility, "publication": map[string]any{"domains": tc.domains},
			})
			_, err := h.call("access_context", map[string]any{"operation": tc.operation, "arguments": tc.arguments}, caller("", "athlete"))
			if (err == nil) != tc.allowed {
				t.Fatalf("allowed = %v, error = %v", tc.allowed, err)
			}
		})
	}
}
