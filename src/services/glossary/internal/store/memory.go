package store

import (
	"context"
	"slices"
	"strings"
	"sync"
)

type Memory struct {
	mu    sync.Mutex
	items map[Key]Item
	names map[string]string
}

func NewMemory() *Memory {
	return &Memory{items: map[Key]Item{}, names: map[string]string{}}
}

func clone(value any) any {
	switch typed := value.(type) {
	case map[string]any:
		copied := make(map[string]any, len(typed))
		for key, inner := range typed {
			copied[key] = clone(inner)
		}
		return copied
	case []any:
		copied := make([]any, len(typed))
		for index, inner := range typed {
			copied[index] = clone(inner)
		}
		return copied
	}
	return value
}

func (m *Memory) Get(_ context.Context, key Key) (Item, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	item, found := m.items[key]
	if !found {
		return nil, nil
	}
	return clone(item).(Item), nil
}

func (m *Memory) List(_ context.Context, pk string) ([]Item, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	var keys []Key
	for key := range m.items {
		if key.PK == pk {
			keys = append(keys, key)
		}
	}
	slices.SortFunc(keys, func(a, b Key) int { return strings.Compare(a.SK, b.SK) })
	items := make([]Item, 0, len(keys))
	for _, key := range keys {
		items = append(items, clone(m.items[key]).(Item))
	}
	return items, nil
}

func (m *Memory) Update(_ context.Context, key Key, patch Patch) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	item, found := m.items[key]
	if !found {
		item = Item{}
		m.items[key] = item
	}
	for field, value := range patch.Set {
		item[field] = clone(value)
	}
	for _, field := range patch.Remove {
		delete(item, field)
	}
	return nil
}

func (m *Memory) CreateCatalog(_ context.Context, item Item) (bool, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	id, _ := item["id"].(string)
	nameKey, _ := item["name_key"].(string)
	key := CatalogKey(id)
	if _, exists := m.items[key]; exists {
		return false, nil
	}
	if _, taken := m.names[nameKey]; taken {
		return false, nil
	}
	m.items[key] = clone(item).(Item)
	m.names[nameKey] = id
	return true, nil
}

func (m *Memory) Pending(_ context.Context, limit int) ([]Item, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	var pending []Item
	for key, item := range m.items {
		if key.PK == CatalogPK && item["generic_pending"] == PendingMarker {
			pending = append(pending, clone(item).(Item))
		}
	}
	slices.SortFunc(pending, func(a, b Item) int {
		first, _ := a["created_at"].(string)
		second, _ := b["created_at"].(string)
		return strings.Compare(first, second)
	})
	if len(pending) > limit {
		pending = pending[:limit]
	}
	return pending, nil
}
