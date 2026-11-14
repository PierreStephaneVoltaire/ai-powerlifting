package store

import (
	"context"
	"testing"
)

func TestMemoryCatalogCreateIsIdempotentByIDAndName(t *testing.T) {
	m := NewMemory()
	ctx := context.Background()
	first := Item{"id": "a", "name_key": "bench", "created_at": "2026-01-01", "generic_pending": PendingMarker}
	if created, _ := m.CreateCatalog(ctx, first); !created {
		t.Fatal("first create failed")
	}
	if created, _ := m.CreateCatalog(ctx, first); created {
		t.Fatal("duplicate id created")
	}
	if created, _ := m.CreateCatalog(ctx, Item{"id": "b", "name_key": "bench"}); created {
		t.Fatal("duplicate name created")
	}
}

func TestMemoryPendingIsSparseAndOrdered(t *testing.T) {
	m := NewMemory()
	ctx := context.Background()
	_, _ = m.CreateCatalog(ctx, Item{"id": "late", "name_key": "late", "created_at": "2", "generic_pending": PendingMarker})
	_, _ = m.CreateCatalog(ctx, Item{"id": "early", "name_key": "early", "created_at": "1", "generic_pending": PendingMarker})
	_, _ = m.CreateCatalog(ctx, Item{"id": "done", "name_key": "done", "created_at": "0"})
	pending, _ := m.Pending(ctx, 5)
	if len(pending) != 2 || pending[0]["id"] != "early" {
		t.Fatalf("pending %v", pending)
	}
	_ = m.Update(ctx, CatalogKey("early"), Patch{Remove: []string{"generic_pending"}})
	if pending, _ = m.Pending(ctx, 1); len(pending) != 1 || pending[0]["id"] != "late" {
		t.Fatalf("pending after clear %v", pending)
	}
}

func TestKeysSeparateCatalogAndAthletes(t *testing.T) {
	if CatalogKey("x") != (Key{"CATALOG", "EXERCISE#x"}) || OverlayKey("a", "x") != (Key{"ATHLETE#a", "EXERCISE#x"}) {
		t.Fatal("unexpected keys")
	}
}
