package generation

import (
	"context"
	"sync"
	"time"
)

type memoryPointers struct {
	mu    sync.Mutex
	items map[string]string
}

func (m *memoryPointers) Get(_ context.Context, key string) (string, bool, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	value, ok := m.items[key]
	return value, ok, nil
}

func (m *memoryPointers) SetNX(_ context.Context, key, value string, _ time.Duration) (bool, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if _, exists := m.items[key]; exists {
		return false, nil
	}
	m.items[key] = value
	return true, nil
}

func (m *memoryPointers) Swap(_ context.Context, key, previous, next string, _ time.Duration) (bool, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.items[key] != previous {
		return false, nil
	}
	m.items[key] = next
	return true, nil
}

type memoryObjects struct {
	mu    sync.Mutex
	items map[string][]byte
}

func (m *memoryObjects) Get(_ context.Context, key string) ([]byte, bool, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	body, ok := m.items[key]
	return body, ok, nil
}

func (m *memoryObjects) Put(_ context.Context, key string, body []byte) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.items[key] = body
	return nil
}

func NewMemory() *Reports {
	return &Reports{Pointers: &memoryPointers{items: map[string]string{}}, Objects: &memoryObjects{items: map[string][]byte{}}, Prefix: "analysis-reports"}
}
