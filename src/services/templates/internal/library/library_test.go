package library

import (
	"context"
	"encoding/json"
	"errors"
	"testing"
	"time"
)

type memory struct {
	items     map[string]map[string]any
	puts      int
	conflicts int
	commits   int
}

func (m *memory) Get(_ context.Context, pk, sk string) (map[string]any, error) {
	item := m.items[pk+"/"+sk]
	if item == nil {
		return nil, nil
	}
	b, _ := json.Marshal(item)
	var out map[string]any
	json.Unmarshal(b, &out)
	return out, nil
}
func (m *memory) Commit(_ context.Context, item map[string]any, remove bool, claim *ImportClaim, index map[string]any, revision string) error {
	m.commits++
	if m.conflicts > 0 {
		m.conflicts--
		return ErrConflict
	}
	current := m.items[index["pk"].(string)+"/template#index"]
	if current != nil && stringValueForTest(current["index_revision"]) != revision {
		return libraryConflictForTest()
	}
	key := item["pk"].(string) + "/" + item["sk"].(string)
	if remove {
		delete(m.items, key)
	} else {
		m.items[key] = copyForTest(item)
	}
	m.items[index["pk"].(string)+"/template#index"] = copyForTest(index)
	m.puts += 2
	return nil
}
func stringValueForTest(v any) string { s, _ := v.(string); return s }
func copyForTest(item map[string]any) map[string]any {
	raw, _ := json.Marshal(item)
	var out map[string]any
	json.Unmarshal(raw, &out)
	return out
}
func libraryConflictForTest() error { return ErrConflict }
func TestCreateVisibilityAndValidation(t *testing.T) {
	ctx := context.Background()
	db := &memory{items: map[string]map[string]any{}}
	store := Library{Backend: db, Now: func() time.Time { return time.Date(2026, 1, 1, 0, 0, 0, 0, time.UTC) }}
	invalid := map[string]any{"sessions": []any{map[string]any{"exercises": []any{map[string]any{"rep_mode": "amrap", "reps": 8}}}}}
	if _, err := store.Create(ctx, invalid, "alice", "", false); err == nil || db.puts != 0 {
		t.Fatalf("invalid template wrote data: %v", err)
	}
	sk, err := store.Create(ctx, map[string]any{"meta": map[string]any{"name": "private"}}, "alice", "", false)
	if err != nil {
		t.Fatal(err)
	}
	if _, err = store.Get(ctx, sk, []string{"bob"}); !errors.Is(err, ErrNotFound) {
		t.Fatalf("private template visible to non-owner: %v", err)
	}
	list, err := store.List(ctx, []string{"alice"}, false)
	if err != nil || len(list) != 1 || list[0]["is_owner"] != true {
		t.Fatalf("owner listing: %#v, %v", list, err)
	}
	list, err = store.List(ctx, []string{"bob"}, false)
	if err != nil || len(list) != 0 {
		t.Fatalf("private listing: %#v, %v", list, err)
	}
}

func TestUpdateAndStatusEnforceOwnerAndProtectMetadata(t *testing.T) {
	ctx := context.Background()
	db := &memory{items: map[string]map[string]any{}}
	store := Library{Backend: db}
	sk, err := store.Create(ctx, map[string]any{"meta": map[string]any{"name": "one"}}, "alice", "", true)
	if err != nil {
		t.Fatal(err)
	}
	if err = store.Update(ctx, sk, map[string]any{"meta": map[string]any{"author_pk": "bob"}}, []string{"bob"}); !errors.Is(err, ErrForbidden) {
		t.Fatalf("unexpected non-owner update: %v", err)
	}
	if err = store.Update(ctx, sk, map[string]any{"meta": map[string]any{"name": "two", "author_pk": "bob", "published": false}}, []string{"alice"}); err != nil {
		t.Fatal(err)
	}
	item, err := store.Get(ctx, sk, []string{"alice"})
	if err != nil {
		t.Fatal(err)
	}
	meta := item["meta"].(map[string]any)
	if meta["author_pk"] != "alice" || meta["published"] != true || meta["name"] != "two" {
		t.Fatalf("unexpected metadata: %#v", meta)
	}
	if err = store.SetStatus(ctx, sk, []string{"alice"}, "published", false); err != nil {
		t.Fatal(err)
	}
	if _, err = store.Get(ctx, sk, []string{"bob"}); !errors.Is(err, ErrNotFound) {
		t.Fatalf("private template visible: %v", err)
	}
	if err = store.Delete(ctx, sk, []string{"bob"}); !errors.Is(err, ErrForbidden) {
		t.Fatalf("non-owner deleted template: %v", err)
	}
	if err = store.Delete(ctx, sk, []string{"alice"}); err != nil {
		t.Fatal(err)
	}
	list, err := store.List(ctx, []string{"alice"}, true)
	if err != nil || len(list) != 0 {
		t.Fatalf("deleted template still indexed: %#v, %v", list, err)
	}
}

func TestCopyRequiresVisibilityAndCreatesPrivateOwnedCopy(t *testing.T) {
	ctx := context.Background()
	db := &memory{items: map[string]map[string]any{}}
	store := Library{Backend: db}
	sk, err := store.Create(ctx, map[string]any{"meta": map[string]any{"name": "original"}}, "alice", "", false)
	if err != nil {
		t.Fatal(err)
	}
	if _, err = store.Copy(ctx, sk, "copy", "bob", "", []string{"bob"}); !errors.Is(err, ErrNotFound) {
		t.Fatalf("copied hidden template: %v", err)
	}
	copied, err := store.Copy(ctx, sk, "copy", "alice", "", []string{"alice"})
	if err != nil {
		t.Fatal(err)
	}
	item, err := store.Get(ctx, copied, []string{"alice"})
	if err != nil {
		t.Fatal(err)
	}
	meta := item["meta"].(map[string]any)
	if meta["name"] != "copy" || meta["derived_from_template_sk"] != sk || meta["published"] != false {
		t.Fatalf("unexpected copy: %#v", meta)
	}
	if _, err = store.Get(ctx, copied, []string{"bob"}); !errors.Is(err, ErrNotFound) {
		t.Fatalf("copy visible to non-owner: %v", err)
	}
}

func TestIndexConflictsRetryWithoutPartialWrites(t *testing.T) {
	ctx := context.Background()
	db := &memory{items: map[string]map[string]any{}, conflicts: 2}
	store := Library{Backend: db}
	sk, err := store.Create(ctx, map[string]any{}, "alice", "", false)
	if err != nil {
		t.Fatal(err)
	}
	if db.commits != 3 || db.puts != 2 {
		t.Fatalf("commits=%d writes=%d", db.commits, db.puts)
	}
	db.conflicts = 12
	if err := store.Delete(ctx, sk, []string{"alice"}); !errors.Is(err, ErrConflict) {
		t.Fatalf("delete error = %v", err)
	}
	if _, err := store.Get(ctx, sk, []string{"alice"}); err != nil {
		t.Fatalf("failed transaction deleted template: %v", err)
	}
	list, err := store.List(ctx, []string{"alice"}, false)
	if err != nil || len(list) != 1 {
		t.Fatalf("index changed: %#v %v", list, err)
	}
}

type interleaving struct {
	*memory
	injected bool
}

func (db *interleaving) Commit(ctx context.Context, item map[string]any, remove bool, claim *ImportClaim, index map[string]any, revision string) error {
	if !db.injected {
		db.injected = true
		other := map[string]any{"sk": "template#other", "name": "other", "published": true}
		db.items["template_library/template#index"] = map[string]any{"pk": "template_library", "sk": "template#index", "index_revision": "other-revision", "templates": []any{other}}
		return ErrConflict
	}
	return db.memory.Commit(ctx, item, remove, claim, index, revision)
}
func TestConcurrentIndexUpdateIsRetainedAfterRetry(t *testing.T) {
	ctx := context.Background()
	backend := &interleaving{memory: &memory{items: map[string]map[string]any{}}}
	store := Library{Backend: backend}
	if _, err := store.Create(ctx, map[string]any{}, "alice", "", false); err != nil {
		t.Fatal(err)
	}
	list, err := store.List(ctx, []string{"alice"}, false)
	if err != nil {
		t.Fatal(err)
	}
	if len(list) != 2 {
		t.Fatalf("concurrent entry was lost: %#v", list)
	}
}
