package visibility

import (
	"slices"
	"testing"
)

func TestParticipantLackingPermissionWithholds(t *testing.T) {
	participants := []Participant{
		{Person: "p1", Permissions: []string{"sessions:read", "goals:read"}, Resolved: true},
		{Person: "p2", Permissions: []string{"sessions:read"}, Resolved: true},
	}
	result := Check([]string{"sessions:read", "goals:read"}, participants)
	if result.Allowed || !slices.Equal(result.Lacking["p2"], []string{"goals:read"}) || len(result.Lacking["p1"]) != 0 {
		t.Fatalf("result: %+v", result)
	}
}

func TestAllParticipantsPermittedAllows(t *testing.T) {
	participants := []Participant{
		{Person: "p1", Permissions: []string{"sessions:read"}, Resolved: true},
		{Person: "p2", Permissions: []string{"sessions:read", "goals:read"}, Resolved: true},
	}
	if !Check([]string{"sessions:read"}, participants).Allowed {
		t.Fatal("everyone holds the permission")
	}
	if !Check(nil, participants).Allowed {
		t.Fatal("no required permissions must allow")
	}
}

func TestUnresolvedParticipantFailsClosed(t *testing.T) {
	result := Check([]string{"sessions:read"}, []Participant{{Person: "p1", Resolved: false}})
	if result.Allowed {
		t.Fatal("unresolved participant must withhold")
	}
}

func TestUnion(t *testing.T) {
	if got := Union([]string{"b", "a"}, []string{"a", "c"}); !slices.Equal(got, []string{"a", "b", "c"}) {
		t.Fatalf("union: %v", got)
	}
}
