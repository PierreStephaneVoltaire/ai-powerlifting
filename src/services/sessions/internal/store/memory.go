package store

import (
	"context"
	"encoding/json"
	"slices"
	"strings"
	"sync"

	"powerlifting/sessions/internal/session"
	"powerlifting/sessions/internal/value"
)

type Memory struct {
	mu       sync.Mutex
	Sessions map[string]value.Item
	Health   map[string]value.Item
	Writes   int
}

func NewMemory() *Memory {
	return &Memory{Sessions: map[string]value.Item{}, Health: map[string]value.Item{}}
}

func rowKey(item value.Item) string { return value.Str(item["pk"]) + "\x00" + value.Str(item["sk"]) }

func wire(item value.Item) value.Item { return value.FromAV(value.ToAV(item)) }

func Decimals(v any) any {
	switch typed := v.(type) {
	case json.Number:
		return value.Decimal(typed)
	case map[string]any:
		out := make(map[string]any, len(typed))
		for key, child := range typed {
			out[key] = Decimals(child)
		}
		return out
	case []any:
		out := make([]any, len(typed))
		for i, child := range typed {
			out[i] = Decimals(child)
		}
		return out
	}
	return v
}

func (m *Memory) SeedSession(item value.Item) {
	m.Sessions[rowKey(item)] = wire(Decimals(item).(map[string]any))
}
func (m *Memory) SeedHealth(item value.Item) {
	m.Health[rowKey(item)] = wire(Decimals(item).(map[string]any))
}

func (m *Memory) sorted(match func(value.Item) bool) []value.Item {
	var out []value.Item
	for _, item := range m.Sessions {
		if match(item) {
			out = append(out, value.CopyItem(item))
		}
	}
	slices.SortFunc(out, func(a, b value.Item) int { return strings.Compare(value.Str(a["sk"]), value.Str(b["sk"])) })
	return out
}

func (m *Memory) ForProgram(_ context.Context, pk, programSK string) ([]value.Item, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	prefix := "session#" + programSK + "#"
	return m.sorted(func(i value.Item) bool {
		return i["pk"] == pk && strings.HasPrefix(value.Str(i["sk"]), prefix)
	}), nil
}

func (m *Memory) Listing(_ context.Context, pk, programSK string) ([]value.Item, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	items := m.sorted(func(i value.Item) bool { return i["pk"] == pk && i["program_sk"] == programSK })
	slices.Reverse(items)
	return items, nil
}

func (m *Memory) Put(_ context.Context, item value.Item) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.Writes++
	m.Sessions[rowKey(item)] = wire(item)
	return nil
}

func (m *Memory) Delete(_ context.Context, pk, sk string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.Writes++
	delete(m.Sessions, pk+"\x00"+sk)
	return nil
}

func (m *Memory) Apply(_ context.Context, pk string, deleteSKs []string, puts []value.Item) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.Writes++
	for _, sk := range deleteSKs {
		delete(m.Sessions, pk+"\x00"+sk)
	}
	for _, item := range puts {
		m.Sessions[rowKey(item)] = wire(item)
	}
	return nil
}

func (m *Memory) CurrentSK(_ context.Context, pk string) (string, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if ref, ok := m.Health[pk+"\x00"+pointerSK]["ref_sk"].(string); ok && ref != "" {
		return ref, nil
	}
	return fallbackSK, nil
}

func (m *Memory) Program(_ context.Context, pk, sk string) (session.Program, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	item, ok := m.Health[pk+"\x00"+sk]
	if !ok {
		return session.Program{}, nil
	}
	program := session.Program{Found: true}
	if published, ok := item["published"].(bool); ok && !published {
		program.Unpublished = true
	}
	if phases, ok := item["phases"].([]any); ok {
		program.Phases = value.Copy(phases).([]any)
	}
	return program, nil
}
