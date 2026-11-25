package cache

import "testing"

func TestCachedReportAuthorizationTracksPermissionsAndCompetitionScope(t *testing.T) {
	access := map[string]any{"permissions": []any{"program:read", "analytics:read", "competition:read"}, "competition_scope": map[string]any{"read": []any{"COMP#meet-a"}}}
	req := Requirements(access)
	if !Authorize(req, access) {
		t.Fatal("original access denied")
	}
	access["competition_scope"] = map[string]any{"read": []any{"meet-b"}}
	if Authorize(req, access) {
		t.Fatal("changed meet permitted")
	}
	access["competition_scope"] = map[string]any{"read": nil}
	if !Authorize(req, access) {
		t.Fatal("unrestricted competition access denied")
	}
	access["permissions"] = []any{"program:read"}
	if Authorize(req, access) {
		t.Fatal("revoked permission permitted")
	}
	if Authorize(nil, access) {
		t.Fatal("unscoped record allowed to non-owner")
	}
}

func TestScopeKeyIgnoresPermissionOrdering(t *testing.T) {
	a := map[string]any{"permissions": []any{"program:read", "competition:read"}, "competition_scope": map[string]any{"read": []any{"b", "a"}}}
	b := map[string]any{"permissions": []any{"competition:read", "program:read"}, "competition_scope": map[string]any{"read": []any{"a", "b"}}}
	x, err := ScopeKey(a)
	if err != nil {
		t.Fatal(err)
	}
	y, err := ScopeKey(b)
	if err != nil {
		t.Fatal(err)
	}
	if x != "scope#aa3a9171f3e8df6c9277ecab55a9208510f41625b8364d348de8eaac08caa081" {
		t.Fatalf("Python-compatible hash mismatch: %s", x)
	}
	if x != y {
		t.Fatalf("%s != %s", x, y)
	}
}
