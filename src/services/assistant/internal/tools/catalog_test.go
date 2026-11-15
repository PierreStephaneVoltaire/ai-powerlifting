package tools

import (
	"slices"
	"testing"
)

func TestScopeIsDerivedFromPermissionsOverFullCatalog(t *testing.T) {
	scope := Scope([]string{"sessions:read", "goals:read", "analytics:read"})
	for _, want := range []string{"session_get", "goals_list", "analytics.lifetime"} {
		if !slices.Contains(scope, want) {
			t.Errorf("permitted cross-feature operation %q missing from scope", want)
		}
	}
	for _, denied := range []string{"session_patch", "goals_replace", "template_get", "weight_log_get"} {
		if slices.Contains(scope, denied) {
			t.Errorf("operation %q must be outside scope", denied)
		}
	}
	if len(Scope(nil)) != 0 {
		t.Fatal("no permissions must give empty scope")
	}
}

func TestScopeIgnoresProfile(t *testing.T) {
	permissions := []string{"sessions:read", "sessions:write", "templates:read", "templates:write"}
	scope := Scope(permissions)
	for _, want := range []string{"session_delete", "template_patch", "template_get"} {
		if !slices.Contains(scope, want) {
			t.Errorf("%q missing", want)
		}
	}
	writes := Writes(scope)
	if !slices.Contains(writes, "template_patch") || slices.Contains(writes, "session_get") {
		t.Fatalf("writes: %v", writes)
	}
}

func TestMutationClassificationFailsClosed(t *testing.T) {
	if !IsMutating("session_patch") || IsMutating("session_get") || !IsMutating("unknown_op") {
		t.Fatal("mutation classification wrong")
	}
	if !IsDestructive("session_delete") || IsDestructive("session_patch") {
		t.Fatal("destructive classification wrong")
	}
}

func TestProfilesAreHintsWithDefaultDelegate(t *testing.T) {
	general, ok := LookupProfile("")
	if !ok || general.Name != SurfaceGeneral || general.DefaultDelegate == "" {
		t.Fatalf("general profile: %+v", general)
	}
	goals, ok := LookupProfile(SurfaceGoals)
	if !ok || goals.Hint == "" || goals.DefaultDelegate != SurfaceGoals {
		t.Fatalf("goals profile: %+v", goals)
	}
	if _, ok := LookupProfile("nope"); ok {
		t.Fatal("unknown profile must not resolve")
	}
	if slices.Contains(SubagentKinds(), SurfaceGeneral) {
		t.Fatal("general is not a delegate kind")
	}
}

func TestVersion(t *testing.T) {
	if Version(`{"version":7,"x":1}`) != "7" {
		t.Fatal("explicit version ignored")
	}
	if Version(`{"x":1}`) != Version(`{"x":1}`) || Version(`{"x":1}`) == Version(`{"x":2}`) {
		t.Fatal("hash fallback unstable")
	}
}
