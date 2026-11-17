package service

import (
	"encoding/base64"
	"fmt"
	"strings"
	"testing"

	"powerlifting/profile/internal/apperr"
	"powerlifting/profile/internal/value"
)

func TestIdentityResolveIsIdempotentAndCreatesPersonHexIDs(t *testing.T) {
	h := newHarness(t, options{IDs: ids("0123456789abcdef0123456789abcdef")})
	args := map[string]any{"issuer": "https://issuer", "provider": "authentik", "sub": "s1", "display_name": "Pat"}
	backend := caller("", "")
	backend.Source = "spiffe://cluster.local/ns/powerlifting/sa/powerlifting-app-backend"
	first, err := h.call("identity_resolve", args, backend)
	if err != nil {
		t.Fatal(err)
	}
	settings := first.(map[string]any)["settings"].(map[string]any)
	if settings["pk"] != "person_0123456789abcdef01234567" || first.(map[string]any)["created"] != true {
		t.Fatalf("%v", first)
	}
	second, err := h.call("identity_resolve", args, backend)
	if err != nil || second.(map[string]any)["created"] != false || second.(map[string]any)["settings"].(map[string]any)["pk"] != settings["pk"] {
		t.Fatalf("%v %v", second, err)
	}
	if rows := len(h.db.Items("if-user")); rows != 2 {
		t.Fatalf("one person and one pointer expected, got %d rows", rows)
	}
}

func TestIdentityResolveSyncsProAccess(t *testing.T) {
	h := newHarness(t, options{IDs: ids("0123456789abcdef0123456789abcdef")})
	backend := caller("", "")
	backend.Source = "spiffe://cluster.local/ns/powerlifting/sa/powerlifting-app-backend"
	args := map[string]any{"issuer": "https://issuer", "provider": "authentik", "sub": "s1", "ai_access": true, "ai_access_expires": 4102444800}
	result, err := h.call("identity_resolve", args, backend)
	if err != nil {
		t.Fatal(err)
	}
	pk := result.(map[string]any)["settings"].(map[string]any)["pk"].(string)
	for _, allowed := range []bool{true, false} {
		args["ai_access"] = allowed
		if _, err := h.call("identity_resolve", args, backend); err != nil {
			t.Fatal(err)
		}
		context, err := h.call("access_context", map[string]any{}, caller(pk, pk))
		if err != nil {
			t.Fatal(err)
		}
		permissions := context.(map[string]any)["permissions"].([]any)
		found := false
		for _, permission := range permissions {
			found = found || permission == "ai:use"
		}
		if found != allowed {
			t.Fatalf("ai access = %v, want %v", found, allowed)
		}
	}
}

func asTyped(err error, target **apperr.Error) bool {
	typed, ok := err.(*apperr.Error)
	*target = typed
	return ok
}

func seedCrowd(h *harness, count int) {
	for i := 0; i < count; i++ {
		pk := fmt.Sprintf("person_u%03d", i)
		h.seed("user", value.Item{"pk": pk, "mapped_pk": pk, "username": pk, "nickname": fmt.Sprintf("u%03d", i), "display_name": fmt.Sprintf("User %03d", i), "roles": []any{"athlete"}, "profile_visibility": "public"})
	}
}

func TestProfileSearchPagesThroughEveryPublicProfileOnce(t *testing.T) {
	h := newHarness(t, options{})
	seedCrowd(h, 45)
	seen := map[string]bool{}
	cursor := ""
	for page := 0; page < 5; page++ {
		args := map[string]any{}
		if cursor != "" {
			args["cursor"] = cursor
		}
		result, err := h.call("profile_search", args, caller("", ""))
		if err != nil {
			t.Fatal(err)
		}
		listed := result.(map[string]any)
		for _, entry := range listed["profiles"].([]any) {
			handle := entry.(map[string]any)["nickname"].(string)
			if seen[handle] {
				t.Fatalf("%s listed twice", handle)
			}
			seen[handle] = true
		}
		next, _ := listed["next_cursor"].(string)
		if next == "" {
			break
		}
		if strings.Contains(next, "=") {
			t.Fatalf("cursor must be unpadded: %s", next)
		}
		cursor = next
	}
	if len(seen) != 45 {
		t.Fatalf("expected 45 distinct profiles, saw %d", len(seen))
	}
}

func TestSearchCursorIsBoundToItsFilters(t *testing.T) {
	h := newHarness(t, options{})
	seedCrowd(h, 30)
	first, err := h.call("profile_search", map[string]any{}, caller("", ""))
	if err != nil {
		t.Fatal(err)
	}
	cursor := first.(map[string]any)["next_cursor"].(string)
	if _, err := h.call("profile_search", map[string]any{"query": "u", "cursor": cursor}, caller("", "")); err == nil {
		t.Fatal("a cursor from another query must be rejected")
	}
	decoded, _ := base64.RawURLEncoding.DecodeString(cursor)
	if !strings.HasPrefix(string(decoded), `{"filter": "`) || !strings.Contains(string(decoded), `"after": ["user 019", "u019"]`) {
		t.Fatalf("cursor payload must keep the Python layout: %s", decoded)
	}
}

func TestEveryOperationHasAHandler(t *testing.T) {
	h := newHarness(t, options{})
	for _, operation := range h.svc.Registry.All() {
		if h.svc.handlers[operation.Name] == nil {
			t.Errorf("%s has no handler", operation.Name)
		}
	}
}
