package analysis

import (
	"context"
	"io"
	"log/slog"
	"testing"

	"github.com/alicebob/miniredis/v2"
	"github.com/redis/go-redis/v9"
)

func TestRecordBumpsOnlyInputWritesForTheAthleteKey(t *testing.T) {
	server := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: server.Addr()})
	valkey := Valkey{Client: client, Log: slog.New(slog.NewTextHandler(io.Discard, nil))}
	valkey.Record(context.Background(), "program_update_meta_field", "a1")
	valkey.Record(context.Background(), "program_update_meta_field", "a1")
	valkey.Record(context.Background(), "program_get", "a1")
	valkey.Record(context.Background(), "diet_notes_update", "a1")
	valkey.Record(context.Background(), "program_archive", "")
	value, err := server.Get(VersionKey("a1"))
	if err != nil || value != "2" {
		t.Fatalf("value %q err %v", value, err)
	}
	if server.Exists(VersionKey("")) {
		t.Fatal("empty athlete bumped")
	}
}

func TestVersionKeyMatchesPython(t *testing.T) {
	if VersionKey("athlete") != "pl:analysis-version:athlete" {
		t.Fatal(VersionKey("athlete"))
	}
}

func TestRecordSurvivesValkeyFailure(t *testing.T) {
	server := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: server.Addr()})
	server.Close()
	Valkey{Client: client, Log: slog.New(slog.NewTextHandler(io.Discard, nil))}.Record(context.Background(), "block_transition", "a1")
}
