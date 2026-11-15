package store

import (
	"context"
	"encoding/json"
	"testing"
	"time"

	"powerlifting/program/internal/env"
)

func fixedEnv() env.Env {
	return env.Env{Now: func() time.Time { return time.Date(2026, 1, 1, 0, 0, 0, 0, time.UTC) }, UUID: func() string { return "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee" }}
}

func TestMemoryNormalizesNumbersLikeDynamo(t *testing.T) {
	db := NewMemory()
	if err := db.Seed("t", Item{"pk": "a", "sk": "b", "n": json.Number("100.0"), "f": 82.5, "i": int64(3), "nested": map[string]any{"x": json.Number("0.10")}}); err != nil {
		t.Fatal(err)
	}
	item, _ := db.Get(context.Background(), "t", Key{"a", "b"}, GetOptions{})
	if item["n"] != json.Number("100") || item["f"] != json.Number("82.5") || item["nested"].(map[string]any)["x"] != json.Number("0.1") {
		t.Fatalf("item %v", item)
	}
}

func TestMemoryRejectsUnsupportedTypes(t *testing.T) {
	if err := NewMemory().Put(context.Background(), "t", Item{"pk": "a", "sk": "b", "bad": struct{}{}}); err == nil {
		t.Fatal("unsupported type accepted")
	}
}

func TestSessionWindowQueryAndBlockFilter(t *testing.T) {
	db := NewMemory()
	tables := Tables{Sessions: "s", Health: "h"}
	sessions := Sessions{DB: db, Tables: tables, Env: fixedEnv()}
	for _, date := range []string{"2026-06-01", "2026-06-10", "2026-07-01"} {
		item := Item{"pk": "a", "sk": "session#p#" + date + "#001#id" + date, "date": date, "block": "b", "week_number": json.Number("1"), "same_day_ordinal": json.Number("1")}
		if err := db.Seed("s", item); err != nil {
			t.Fatal(err)
		}
	}
	all, _ := sessions.List(context.Background(), "a", "p", nil, SessionWindow{})
	windowed, _ := sessions.List(context.Background(), "a", "p", nil, SessionWindow{Start: "2026-06-05", End: "2026-06-30"})
	filtered, _ := sessions.List(context.Background(), "a", "p", nil, SessionWindow{BlockID: "other", ActiveBlock: "x"})
	if len(all) != 3 || len(windowed) != 1 || len(filtered) != 0 {
		t.Fatalf("all %d windowed %d filtered %d", len(all), len(windowed), len(filtered))
	}
}

func TestWriteFreshRejectsDuplicateIdentitiesAndUndatedSessions(t *testing.T) {
	db := NewMemory()
	sessions := Sessions{DB: db, Tables: Tables{Sessions: "s", Health: "h"}, Env: fixedEnv()}
	duplicate := []any{map[string]any{"date": "2026-01-01", "id": "x"}, map[string]any{"date": "2026-01-02", "id": "x"}}
	var conflict *IdentityConflictError
	if err := sessions.WriteFresh(context.Background(), "a", "program#v002-abc", duplicate, nil); err == nil {
		t.Fatal("duplicate accepted")
	} else if c, ok := err.(*IdentityConflictError); !ok {
		t.Fatalf("err %v", err)
	} else {
		conflict = c
	}
	if conflict.ID != "x" || len(db.Dump("s")) != 0 {
		t.Fatalf("conflict %v writes %d", conflict, len(db.Dump("s")))
	}
	if err := sessions.WriteFresh(context.Background(), "a", "program#v002-abc", []any{map[string]any{}}, nil); err != ErrSessionDate {
		t.Fatalf("err %v", err)
	}
}

func TestNextLabel(t *testing.T) {
	cases := []struct {
		label        string
		minor        bool
		current, new int
		want         string
	}{
		{"3.0", false, 3, 4, "4.0"}, {"3.2", true, 3, 4, "3.3"}, {"v003", false, 3, 4, "4.0"}, {"v001", false, 0, 1, "1.0"}, {"x.y", false, 5, 6, "6.0"},
	}
	for _, c := range cases {
		if got := nextLabel(c.label, c.minor, c.current, c.new); got != c.want {
			t.Errorf("%s: got %s want %s", c.label, got, c.want)
		}
	}
}
