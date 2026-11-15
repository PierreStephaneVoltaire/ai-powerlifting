package tools

import (
	"slices"
	"testing"
)

func TestScopeIntersectsSurfaceWithPermissions(t *testing.T) {
	surface, _ := LookupSurface(SurfaceSessionDesign)
	scope := Scope(surface, []string{"sessions:read"})
	if slices.Contains(scope, "session_patch") || !slices.Contains(scope, "session_get") {
		t.Fatalf("scope: %v", scope)
	}
	if len(Scope(surface, nil)) != 0 {
		t.Fatal("no permissions must give empty scope")
	}
	full := Scope(surface, []string{"sessions:read", "sessions:write", "program:read", "performance:read", "glossary:read", "calculations:read"})
	if !slices.Contains(full, "session_delete") || slices.Contains(full, "template_patch") {
		t.Fatalf("full scope: %v", full)
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

func TestGeneralHasNoWritesAndDelegation(t *testing.T) {
	general := General()
	if len(general.Writes) != 0 || !general.CanDelegate(SurfaceGoals) {
		t.Fatal("general surface wrong")
	}
	goals, _ := LookupSurface(SurfaceGoals)
	if goals.CanDelegate(SurfaceBiometrics) || !goals.CanDelegate(SurfaceResearch) {
		t.Fatal("delegation rules wrong")
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
