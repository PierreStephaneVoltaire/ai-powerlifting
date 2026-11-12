package generation

import (
	"context"
	"maps"
	"sync"
)

type Memory struct {
	mu    sync.Mutex
	items map[string]Item
}

func NewMemory() *Memory { return &Memory{items: map[string]Item{}} }

func memoryKey(pk, sk string) string { return pk + "\x00" + sk }

func (m *Memory) Get(_ context.Context, pk, sk string) (Item, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	item, ok := m.items[memoryKey(pk, sk)]
	if !ok {
		return nil, nil
	}
	return maps.Clone(item), nil
}

func (m *Memory) PutIfAbsent(_ context.Context, item Item) (bool, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	key := memoryKey(item["pk"].(string), item["sk"].(string))
	if _, exists := m.items[key]; exists {
		return false, nil
	}
	m.items[key] = maps.Clone(item)
	return true, nil
}

func (m *Memory) PutIfCurrent(_ context.Context, item Item, status string, attempt int) (bool, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	key := memoryKey(item["pk"].(string), item["sk"].(string))
	current, exists := m.items[key]
	if !exists || current["status"] != status || toInt(current["attempt"]) != attempt {
		return false, nil
	}
	m.items[key] = maps.Clone(item)
	return true, nil
}

func (m *Memory) Put(_ context.Context, item Item) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.items[memoryKey(item["pk"].(string), item["sk"].(string))] = maps.Clone(item)
	return nil
}

func (m *Memory) Update(_ context.Context, pk, sk string, attempt int, fields Item) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	current, exists := m.items[memoryKey(pk, sk)]
	if !exists || toInt(current["attempt"]) != attempt {
		return nil
	}
	maps.Copy(current, fields)
	return nil
}
