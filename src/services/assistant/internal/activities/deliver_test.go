package activities

import (
	"context"
	"slices"
	"testing"

	"powerlifting/assistant/internal/access"
	"powerlifting/assistant/internal/visibility"
)

type fakeResolver map[string]access.Identity

func (f fakeResolver) Resolve(_ context.Context, person, athlete string) (access.Identity, error) {
	identity, ok := f[person]
	if !ok {
		return access.Identity{}, access.ErrDenied
	}
	return identity, nil
}

type failingResolver struct{}

func (failingResolver) Resolve(context.Context, string, string) (access.Identity, error) {
	return access.Identity{}, access.ErrUnavailable
}

func TestSharedChannelWithholdsWhenParticipantLacksPermission(t *testing.T) {
	resolver := fakeResolver{
		"p1": {Person: "p1", Permissions: []string{"sessions:read", "goals:read"}},
		"p2": {Person: "p2", Permissions: []string{"sessions:read"}},
	}
	required := requiredPermissions([]string{"session_get", "goals_list"})
	if !slices.Equal(required, []string{"goals:read", "sessions:read"}) {
		t.Fatalf("required: %v", required)
	}
	result := visibility.Check(required, participantsFor(context.Background(), resolver, "a1", []string{"p1", "p2"}))
	if result.Allowed || !slices.Equal(result.Lacking["p2"], []string{"goals:read"}) {
		t.Fatalf("content must be withheld: %+v", result)
	}
}

func TestSharedChannelAllowsWhenEveryoneMayView(t *testing.T) {
	resolver := fakeResolver{
		"p1": {Person: "p1", Permissions: []string{"sessions:read"}},
		"p2": {Person: "p2", Permissions: []string{"sessions:read", "goals:read"}},
	}
	result := visibility.Check([]string{"sessions:read"}, participantsFor(context.Background(), resolver, "a1", []string{"p1", "p2"}))
	if !result.Allowed {
		t.Fatalf("expected allowed: %+v", result)
	}
}

func TestRevokedOrUnresolvableParticipantWithholds(t *testing.T) {
	revoked := visibility.Check([]string{"sessions:read"}, participantsFor(context.Background(), fakeResolver{}, "a1", []string{"gone"}))
	unavailable := visibility.Check([]string{"sessions:read"}, participantsFor(context.Background(), failingResolver{}, "a1", []string{"p1"}))
	if revoked.Allowed || unavailable.Allowed {
		t.Fatal("revoked and unresolvable participants must fail closed")
	}
}
