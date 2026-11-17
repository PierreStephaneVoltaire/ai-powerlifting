package activities

import (
	"context"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"powerlifting/assistant/internal/store"
)

func assistantTestStore(t *testing.T) (*store.Store, store.ConversationRef) {
	t.Helper()
	dsn := os.Getenv("ASSISTANT_TEST_DATABASE_URL")
	if dsn == "" {
		t.Skip("ASSISTANT_TEST_DATABASE_URL is not set")
	}
	ctx := context.Background()
	admin, err := pgxpool.New(ctx, dsn)
	if err != nil {
		t.Fatal(err)
	}
	schema := pgx.Identifier{"progress_test_" + time.Now().Format("150405000000000")}.Sanitize()
	if _, err := admin.Exec(ctx, "CREATE SCHEMA "+schema); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		_, _ = admin.Exec(ctx, "DROP SCHEMA "+schema+" CASCADE")
		admin.Close()
	})
	config, err := pgxpool.ParseConfig(dsn)
	if err != nil {
		t.Fatal(err)
	}
	config.ConnConfig.RuntimeParams["search_path"] = schema + ",public"
	pool, err := pgxpool.NewWithConfig(ctx, config)
	if err != nil {
		t.Fatal(err)
	}
	s := &store.Store{Pool: pool}
	t.Cleanup(s.Close)
	if err := s.Bootstrap(ctx, 3); err != nil {
		t.Fatal(err)
	}
	ref, err := store.ParseConversationID("powerlifting:a:web:p:supplements")
	if err != nil {
		t.Fatal(err)
	}
	if err := s.EnsureConversation(ctx, ref, "p"); err != nil {
		t.Fatal(err)
	}
	return s, ref
}

func TestProgressSurvivesModelCallsAndCompletion(t *testing.T) {
	s, ref := assistantTestStore(t)
	ctx := context.Background()
	for _, status := range []string{"succeeded", "cancelled"} {
		t.Run(status, func(t *testing.T) {
			if err := s.InsertTurn(ctx, store.Turn{ID: status, ConversationID: ref.ID, PersonPK: "p", WorkflowID: status, Status: "running", Request: []byte(`{}`)}); err != nil {
				t.Fatal(err)
			}
			first := newProgressStream(ctx, s, status, "first")
			first.Add("First reasoning. ")
			first.Flush()
			first.Add("More reasoning. ")
			first.Flush()
			second := newProgressStream(ctx, s, status, "second")
			second.Add(strings.Repeat("Later reasoning. ", 500))
			second.Flush()
			assertProgress := func() {
				t.Helper()
				progress, err := s.Progress(ctx, status)
				if err != nil || progress == nil || !strings.Contains(progress.Text, "First reasoning. More reasoning.") || strings.Count(progress.Text, "First reasoning.") != 1 || strings.Count(progress.Text, "Later reasoning.") != 500 {
					t.Fatalf("reasoning was cleared, truncated, or duplicated: progress=%v error=%v", progress, err)
				}
			}
			assertProgress()
			var err error
			if status == "cancelled" {
				err = s.CancelTurn(ctx, status)
			} else {
				err = s.CompleteTurn(ctx, store.Completion{TurnID: status, Status: status})
			}
			if err != nil {
				t.Fatal(err)
			}
			assertProgress()
		})
	}
}
