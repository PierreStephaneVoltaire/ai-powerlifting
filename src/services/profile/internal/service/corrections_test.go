package service

import (
	"context"
	"strings"
	"testing"

	"powerlifting/profile/internal/access"
	"powerlifting/profile/internal/value"
)

var operationsRemovedAsDead = map[string]bool{"settings_create": true, "master_copy_seed_user": true}

var argsAfterSettingsCreateRemoval = map[string]map[string]any{
	"access_nested_internal_only_non_backend": {"operation": "identity_resolve"},
	"access_nested_internal_only_backend":     {"operation": "identity_resolve"},
}

func grantTypesOf(t *testing.T, listed any) []string {
	t.Helper()
	entries, _ := listed.([]any)
	types := make([]string, len(entries))
	for i, entry := range entries {
		types[i], _ = entry.(map[string]any)["grant_type"].(string)
	}
	return types
}

func requireTypes(t *testing.T, label string, got []string, want ...string) {
	t.Helper()
	if len(got) != len(want) {
		t.Fatalf("%s: got %v want %v", label, got, want)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("%s: got %v want %v", label, got, want)
		}
	}
}

var resultAfterPeerGrantSchemaFix = map[string]func(*testing.T, map[string]any){
	"relations_grant_list_by_athlete": func(t *testing.T, result map[string]any) {
		requireTypes(t, "active", grantTypesOf(t, result["active"]), "coach", "handler", "peer")
		requireTypes(t, "inactive", grantTypesOf(t, result["inactive"]))
	},
	"relations_grant_list_by_athlete_with_inactive": func(t *testing.T, result map[string]any) {
		requireTypes(t, "active", grantTypesOf(t, result["active"]), "coach", "handler", "peer")
	},
}

func handlerContextFixture(t *testing.T, permissions ...string) (map[string]any, error) {
	t.Helper()
	h := newHarness(t, options{Now: "2026-11-16T12:00:00+00:00"})
	h.seed("user", value.Item{"pk": "person_a", "mapped_pk": "person_a", "username": "person_a", "nickname": "a", "display_name": "A", "roles": []any{"athlete"}, "profile_visibility": "private"})
	h.seed("health", value.Item{
		"pk": "person_a", "sk": "program#v001", "published": true,
		"meta": map[string]any{"program_start": "2026-11-02"},
		"phases": []any{
			map[string]any{"name": "Hypertrophy", "intent": "", "start_week": 1, "end_week": 2, "block": "current"},
			map[string]any{"name": "Peak", "intent": "", "start_week": 3, "end_week": 4, "block": "current"},
		},
	})
	h.seed("sessions", value.Item{"pk": "person_a", "sk": "session#program#v001#1", "date": "2026-11-03", "week_number": 1, "block": "current"})
	granted := &access.Context{PersonPK: "person_a", AthletePK: "person_a", OwnAthletePK: "person_a", IsSelf: true, Permissions: permissions, ReadScope: access.Scope{Unrestricted: true}}
	result, err := h.svc.handlers["handler_context"](context.Background(), &Request{Name: "handler_context", Args: map[string]any{"pk": "person_a"}, Caller: caller("person_a", "person_a"), Access: granted})
	if err != nil {
		return nil, err
	}
	return normalizeRender(result).(map[string]any), nil
}

func phaseName(result map[string]any) any {
	phase, _ := result["phase"].(map[string]any)
	return phase["name"]
}

func TestHandlerContextPhaseWithoutSessionsReadComesFromPhasesAndTodayNotSessions(t *testing.T) {
	result, err := handlerContextFixture(t, "profile:read", "program:read")
	if err != nil {
		t.Fatal(err)
	}
	if phaseName(result) != "Peak" {
		t.Fatalf("%v", result["phase"])
	}
}

func TestHandlerContextPhaseWithSessionsReadStaysSessionDerived(t *testing.T) {
	result, err := handlerContextFixture(t, "profile:read", "program:read", "sessions:read")
	if err != nil {
		t.Fatal(err)
	}
	if phaseName(result) != "Hypertrophy" {
		t.Fatalf("%v", result["phase"])
	}
}

func TestHandlerContextPhaseIsAbsentWithoutProgramRead(t *testing.T) {
	result, err := handlerContextFixture(t, "profile:read")
	if err != nil {
		t.Fatal(err)
	}
	if result["phase"] != nil || result["block"] != nil {
		t.Fatalf("%v", result)
	}
}

func TestGrantListReturnsPeerGrantsThroughTheResultSchema(t *testing.T) {
	h := newHarness(t, options{Now: "2026-11-16T12:00:00+00:00"})
	h.seed("user", value.Item{"pk": "person_a", "mapped_pk": "person_a", "username": "person_a", "nickname": "a", "roles": []any{"athlete"}})
	h.seed("requests", value.Item{
		"pk": "Grant#person_a", "sk": "Relationship#p1", "entity": "grant", "relationship_id": "p1", "state": "approved",
		"athlete_mapped_pk": "person_a", "grantee_mapped_pk": "person_p", "grant_type": "peer", "scope": "read",
		"permissions": []any{"sessions:read"}, "expires_at": "2027-01-01T00:00:00+00:00", "revoked_at": nil,
	})
	result, err := h.call("grant_list", map[string]any{"athlete_mapped_pk": "person_a"}, caller("person_a", "person_a"))
	if err != nil {
		t.Fatal(err)
	}
	requireTypes(t, "active", grantTypesOf(t, normalizeRender(result).(map[string]any)["active"]), "peer")
}

func TestGrantListByGranteeQueriesRosterIndexAndNeverScans(t *testing.T) {
	h := newHarness(t, options{Now: "2026-11-16T12:00:00+00:00"})
	grant := func(athlete, id, grantee, kind string) value.Item {
		return value.Item{
			"pk": "Grant#" + athlete, "sk": "Relationship#" + id, "entity": "grant", "relationship_id": id, "state": "approved",
			"athlete_mapped_pk": athlete, "grantee_mapped_pk": grantee, "grant_type": kind, "scope": "read",
			"expires_at": "2027-01-01T00:00:00+00:00", "revoked_at": nil,
		}
	}
	request := func(athlete, id, delegate, kind string) value.Item {
		return value.Item{
			"pk": "Relationship#" + id, "sk": "Record", "entity": "relationship_request", "relationship_id": id,
			"athlete_mapped_pk": athlete, "roster_pk": "Roster#" + delegate, "roster_sk": kind + "#" + athlete + "#" + id,
		}
	}
	h.seed("requests",
		grant("person_z", "r2", "person_b", "handler"), request("person_z", "r2", "person_b", "handler"),
		grant("person_a", "r1", "person_b", "coach"), request("person_a", "r1", "person_b", "coach"),
		grant("person_a", "r3", "person_c", "coach"), request("person_a", "r3", "person_c", "coach"),
		grant("person_m", "r4", "person_b", "peer"), request("person_m", "r4", "person_b", "peer"),
		value.Item{"pk": "Relationship#r5", "sk": "Record", "entity": "relationship_request", "relationship_id": "r5", "athlete_mapped_pk": "person_q", "roster_pk": "Roster#person_b", "roster_sk": "coach#person_q#r5"},
	)
	result, err := h.svc.grantList(context.Background(), &Request{Name: "grant_list", Args: map[string]any{"grantee_mapped_pk": "person_b"}})
	if err != nil {
		t.Fatal(err)
	}
	active := normalizeRender(result).(map[string]any)["active"].([]any)
	var keys []string
	for _, entry := range active {
		grant := entry.(map[string]any)
		keys = append(keys, grant["pk"].(string)+"/"+grant["sk"].(string)+"/"+grant["grant_type"].(string))
	}
	want := []string{"Grant#person_a/Relationship#r1/coach", "Grant#person_m/Relationship#r4/peer", "Grant#person_z/Relationship#r2/handler"}
	if strings.Join(keys, ",") != strings.Join(want, ",") {
		t.Fatalf("got %v want %v", keys, want)
	}
	if h.db.Calls["Scan"] != 0 {
		t.Fatalf("scan used %d times", h.db.Calls["Scan"])
	}
}
