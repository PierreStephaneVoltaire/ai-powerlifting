package relations

import (
	"slices"
	"testing"
	"time"

	"powerlifting/profile/internal/value"
)

func TestHashesMatchThePythonImplementation(t *testing.T) {
	if got, want := actionHash("rid1", "rejected", "person_bob", map[string]any{"action": "rejected"}), "d7517fa42a6c72878e7eb86ad7e653ff0015ab17013da045d07d1d1a8fb7e9d4"; got != want {
		t.Errorf("action hash %s", got)
	}
	request := value.Item{"requester_person_pk": "person_alice", "recipient_person_pk": "person_bob", "athlete_person_pk": "person_alice", "athlete_mapped_pk": "person_alice", "relationship_type": "coach"}
	args := map[string]any{"scope": "write", "permissions": []any{"b:read", "a:read"}, "tied_competition_ids": []any{"m2", "m1"}, "replace_current_relationship_id": ""}
	if got, want := approvalHash("rid1", "person_bob", args, request), "86369a81a320b6319fc7625741243aa7b8b8ce073906ccff98ecec552a29bbd4"; got != want {
		t.Errorf("approval hash %s", got)
	}
	payload := map[string]any{"athlete_mapped_pk": "person_alice", "recipient_person_pk": "person_bob", "relationship_type": "coach", "tied_competition_ids": []any{"mé"}, "note": "café \U0001F3CB"}
	if got, want := requestPayloadHash(payload), "e029f11b9a29fe8c0c99b85c75138fe4f3ae391a1bd18cd4ac98526b9411108d"; got != want {
		t.Errorf("payload hash %s", got)
	}
}

func TestKeysMatchThePythonImplementation(t *testing.T) {
	if key := pendingKey("person_alice", "person_alice", "person_bob", "coach"); key["pk"] != "RelationshipPending#8fdda3b93b05d4cc2d7fa1fe4948f42a3f130169e7ed28883d5ed83809b2ca52" || key["sk"] != "Record" {
		t.Errorf("%v", key)
	}
	if key := idempotencyItemKey("person_alice", "k1"); key["sk"] != "Request#6ab9f1eb8f7d3388f4f9d586f66e99fd54080df2c446f0e58668b09c08a16dd0" {
		t.Errorf("%v", key)
	}
}

func TestExpiryUsesTheLatestTieAndKeepsItsUTCOffsetDate(t *testing.T) {
	got, err := expiry("coach", []string{"a", "b"}, map[string]string{"a": "2026-11-01", "b": "2026-12-01T10:00:00+05:00"})
	if err != nil || got != "2026-12-08T23:59:59.999999+00:00" {
		t.Fatalf("%s %v", got, err)
	}
	if peer, _ := expiry("peer", nil, nil); peer != "" {
		t.Fatalf("peers never expire: %q", peer)
	}
	if _, err := expiry("coach", []string{"x"}, map[string]string{}); err == nil {
		t.Fatal("unknown tie accepted")
	}
	_ = time.Now
}

func TestPermissionsRules(t *testing.T) {
	if _, err := Permissions("peer", []any{"sessions:write"}, "write"); err == nil {
		t.Fatal("peer write accepted")
	}
	got, err := Permissions("coach", []any{"sessions:write", "sessions:read", "bogus:read"}, "read")
	if err != nil || len(got) != 1 || got[0] != "sessions:read" {
		t.Fatalf("%v %v", got, err)
	}
	if all, _ := Permissions("handler", nil, "write"); !slices.Equal(all, []string{
		"calculations:read", "competition:read", "competition:write", "lift-profiles:read", "performance:read",
		"profile:read", "program:read", "sessions:read", "videos:read",
	}) {
		t.Fatalf("handler defaults: %v", all)
	}
}
