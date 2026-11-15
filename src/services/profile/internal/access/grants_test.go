package access

import (
	"slices"
	"testing"
	"time"

	"powerlifting/profile/internal/value"
)

var now = time.Date(2026, 11, 14, 12, 0, 0, 0, time.UTC)

func coach(extra map[string]any) Grant {
	item := value.Item{"sk": "Relationship#r", "state": "approved", "grant_type": "coach", "tied_competition_ids": []any{"m1"}, "relationship_id": "r"}
	for k, v := range extra {
		item[k] = v
	}
	return GrantOf(item)
}

func TestCoachGrantExpiresSevenDaysAfterTheLatestTiedCompetitionEndOfDay(t *testing.T) {
	dates := map[string]string{"m1": "2026-11-07"}
	if got := GrantPermissions(coach(nil), dates, time.Date(2026, 11, 14, 23, 59, 59, 0, time.UTC)); len(got) != len(CoachPermissions) {
		t.Fatalf("still valid on the final day: %d", len(got))
	}
	if got := GrantPermissions(coach(nil), dates, time.Date(2026, 11, 15, 0, 0, 0, 0, time.UTC)); got != nil {
		t.Fatalf("expired the next day: %v", got)
	}
	if GrantPermissions(coach(nil), map[string]string{}, now) != nil || GrantPermissions(coach(map[string]any{"tied_competition_ids": []any{}}), dates, now) != nil {
		t.Fatal("coach grants need dated ties")
	}
}

func TestPeerGrantsAreReadOnlyAndTimezoneAware(t *testing.T) {
	peer := func(expires string, permissions []any) Grant {
		return GrantOf(value.Item{"sk": "x", "grant_type": "peer", "expires_at": expires, "permissions": permissions})
	}
	got := GrantPermissions(peer("2027-01-01T00:00:00+00:00", []any{"sessions:read", "sessions:write", "bogus:read"}), nil, now)
	if !slices.Equal(got, []string{"sessions:read"}) {
		t.Fatalf("%v", got)
	}
	if GrantPermissions(peer("2027-01-01T00:00:00", []any{"sessions:read"}), nil, now) != nil {
		t.Fatal("naive expiry timestamps cannot be compared and deny")
	}
	if GrantPermissions(peer("2026-11-14T12:00:00+00:00", []any{"sessions:read"}), nil, now) != nil {
		t.Fatal("expiry is exclusive")
	}
}

func TestRoleSlotDecidesWhichCoachGrantIsActive(t *testing.T) {
	dates := map[string]string{"m1": "2026-12-01"}
	first, second := coach(nil), coach(map[string]any{"sk": "Relationship#s", "relationship_id": "s"})
	if got := ActiveGrants([]Grant{first, second}, dates, now); got != nil {
		t.Fatalf("two coach grants without a slot are ambiguous: %d", len(got))
	}
	slot := GrantOf(value.Item{"sk": "RelationshipSlot#coach", "entity": "relationship_slot", "grant_type": "coach", "state": "active", "relationship_id": "s"})
	got := ActiveGrants([]Grant{first, second, slot}, dates, now)
	if len(got) != 1 || got[0].RelationshipID != "s" {
		t.Fatalf("%+v", got)
	}
}

func TestEvaluateMarksSelfAndRestrictsCompetitionScopeForGrantees(t *testing.T) {
	actor := value.Item{"pk": "bob", "mapped_pk": "bob", "roles": []any{"coach"}}
	owner := value.Item{"pk": "alice", "mapped_pk": "alice", "roles": []any{"athlete"}}
	grant := value.Item{"sk": "Relationship#r", "state": "approved", "grant_type": "coach", "relationship_id": "r", "grantee_person_pk": "bob", "tied_competition_ids": []any{"m1"}}
	ctx := Evaluate("bob", "alice", owner, actor, []Grant{GrantOf(grant)}, map[string]string{"m1": "2026-12-01"}, now)
	if ctx.IsSelf || ctx.ReadScope.Unrestricted || !ctx.Has("competition:write") || !slices.Equal(ctx.WriteScope.IDs, []string{"m1"}) {
		t.Fatalf("%+v", ctx)
	}
	self := Evaluate("alice", "alice", owner, owner, nil, nil, now)
	if !self.IsSelf || !self.ReadScope.Unrestricted || self.Has("sessions:read") {
		t.Fatalf("an athlete without basics cannot use training domains: %+v", self)
	}
}
