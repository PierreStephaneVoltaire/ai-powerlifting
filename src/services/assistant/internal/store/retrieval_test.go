package store

import (
	"slices"
	"strings"
	"testing"
)

func TestRetrievalFiltersBeforeOrdering(t *testing.T) {
	sql, args := BuildRetrieval(RetrievalQuery{Athlete: "a1", Person: "p1", Permissions: []string{"sessions:read"}, Embedding: []float32{0.5, 1, -2}, Limit: 3})
	where, order := strings.Index(sql, "WHERE"), strings.Index(sql, "ORDER BY")
	if where < 0 || order < 0 || where > order {
		t.Fatalf("authorization WHERE must precede ORDER BY:\n%s", sql)
	}
	filter := sql[where:order]
	for _, want := range []string{"c.athlete_pk = $1", "e.athlete_pk = $1", "participants", "c.owner_person = $2", "e.required_permissions <@ $3::text[]"} {
		if !strings.Contains(filter, want) {
			t.Errorf("filter missing %q", want)
		}
	}
	if !strings.Contains(sql[order:], "e.embedding <-> $4::vector") || !strings.HasSuffix(sql, "LIMIT $5") {
		t.Errorf("ordering clause wrong:\n%s", sql[order:])
	}
	if len(args) != 5 || args[0] != "a1" || args[1] != "p1" || !slices.Equal(args[2].([]string), []string{"sessions:read"}) || args[3] != "[0.5,1,-2]" || args[4] != 3 {
		t.Errorf("args wrong: %#v", args)
	}
}

func TestRetrievalNilPermissionsBecomeEmptyArray(t *testing.T) {
	_, args := BuildRetrieval(RetrievalQuery{Athlete: "a", Person: "p", Embedding: []float32{1}})
	if permissions, ok := args[2].([]string); !ok || permissions == nil || len(permissions) != 0 {
		t.Fatalf("permissions arg: %#v", args[2])
	}
	if args[4] != 5 {
		t.Fatalf("default limit: %#v", args[4])
	}
}

func TestHistoryAppliesVisibilityAndPermissions(t *testing.T) {
	sql, args := BuildHistory(HistoryQuery{ConversationID: "powerlifting:a1:discord:c", Athlete: "a1", Person: "p2", Permissions: []string{"goals:read"}, Limit: 500})
	where, order := strings.Index(sql, "WHERE"), strings.Index(sql, "ORDER BY")
	if !strings.Contains(sql[where:order], "t.required_permissions <@ $3::text[]") || !strings.Contains(sql[where:order], "participants") {
		t.Fatalf("history filter incomplete:\n%s", sql)
	}
	if args[4] != 20 || args[5] != "powerlifting:a1:discord:c" {
		t.Fatalf("args: %#v", args)
	}
}

func TestParseConversationID(t *testing.T) {
	discord, err := ParseConversationID("powerlifting:a1:discord:chan9")
	if err != nil || !discord.Shared || discord.Athlete != "a1" || discord.Scope != "chan9" {
		t.Fatalf("discord: %+v %v", discord, err)
	}
	web, err := ParseConversationID("powerlifting:a1:web:p2:session:2026-01-01")
	if err != nil || web.Shared || web.Owner != "p2" || web.Scope != "session:2026-01-01" {
		t.Fatalf("web: %+v %v", web, err)
	}
	for _, bad := range []string{"", "powerlifting:a1", "other:a1:discord:c", "powerlifting:a1:web:p2", "powerlifting:a1:slack:c", "powerlifting::discord:c", "powerlifting:a1:discord:c:extra"} {
		if _, err := ParseConversationID(bad); err == nil {
			t.Errorf("%q accepted", bad)
		}
	}
}
