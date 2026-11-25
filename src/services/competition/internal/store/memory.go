package store

import (
	"context"
	"sort"
	"strings"
	"sync"

	"powerlifting/competition/internal/pyval"
)

type Memory struct {
	mu            sync.Mutex
	EntryItems    map[[2]string]Item
	HealthItems   map[[2]string]Item
	SessionItems  map[[2]string]Item
	GlossaryItems map[[2]string]Item
	Bumps         map[string]int
	Updates       int
	FailUpdate    error
}

func NewMemory() *Memory {
	return &Memory{
		EntryItems:    map[[2]string]Item{},
		HealthItems:   map[[2]string]Item{},
		SessionItems:  map[[2]string]Item{},
		GlossaryItems: map[[2]string]Item{},
		Bumps:         map[string]int{},
	}
}

func (m *Memory) Load(table string, items []Item) {
	target := m.table(table)
	for _, item := range items {
		target[[2]string{item["pk"].(string), item["sk"].(string)}] = normalise(item).(map[string]any)
	}
}

func (m *Memory) table(name string) map[[2]string]Item {
	switch name {
	case "entries":
		return m.EntryItems
	case "health":
		return m.HealthItems
	case "glossary":
		return m.GlossaryItems
	}
	return m.SessionItems
}

func pick(table map[[2]string]Item, pk, prefix string, include func(Item) bool) []Item {
	var out []Item
	for k, item := range table {
		if k[0] == pk && strings.HasPrefix(k[1], prefix) && include(item) {
			out = append(out, pyval.Copy(item).(Item))
		}
	}
	sort.Slice(out, func(i, j int) bool { return out[i]["sk"].(string) < out[j]["sk"].(string) })
	return out
}

func all(Item) bool { return true }

func (m *Memory) Get(_ context.Context, pk, sk string) (Item, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	return copyOf(m.EntryItems[[2]string{pk, sk}]), nil
}

func copyOf(item Item) Item {
	if item == nil {
		return nil
	}
	return pyval.Copy(item).(Item)
}

func (m *Memory) Query(_ context.Context, pk, skPrefix string) ([]Item, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	return pick(m.EntryItems, pk, skPrefix, all), nil
}

func (m *Memory) QueryByDate(_ context.Context, pk string) ([]Item, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	items := pick(m.EntryItems, pk, "", func(item Item) bool { _, ok := item["entry_date"]; return ok })
	sort.SliceStable(items, func(i, j int) bool {
		return items[i]["entry_date"].(string) < items[j]["entry_date"].(string)
	})
	return items, nil
}

func (m *Memory) Update(_ context.Context, pk, sk string, update EntryUpdate) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.FailUpdate != nil {
		return m.FailUpdate
	}
	item := m.EntryItems[[2]string{pk, sk}]
	item["updated_at"] = update.UpdatedAt
	for _, field := range update.Set {
		item[field.Name] = normalise(field.Value)
	}
	for _, name := range update.Remove {
		delete(item, name)
	}
	return nil
}

func (m *Memory) SaveProjection(_ context.Context, pk, sk string, projection Projection) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.FailUpdate != nil {
		return m.FailUpdate
	}
	item := m.EntryItems[[2]string{pk, sk}]
	values := map[string]any{}
	for _, field := range projection.Values {
		values[field.Name] = normalise(field.Value)
	}
	item["projected_at_t_minus_1w"] = values
	item["projection_snapshot_date"] = projection.SnapshotDate
	item["updated_at"] = projection.UpdatedAt
	return nil
}

func normalise(value any) any {
	return FromAttr(ToAttr(value))
}

func (m *Memory) Pointer(_ context.Context, pk string) (Item, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	return copyOf(m.HealthItems[[2]string{pk, PointerSK}]), nil
}

func (m *Memory) Item(_ context.Context, pk, sk string) (Item, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	return copyOf(m.HealthItems[[2]string{pk, sk}]), nil
}

func (m *Memory) GlossaryEntries(_ context.Context, pk string) ([]Item, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	return pick(m.GlossaryItems, pk, GlossarySKPrefix, all), nil
}

func (m *Memory) Sessions(_ context.Context, pk, programSK string) ([]Item, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	return pick(m.SessionItems, pk, SessionSKPrefix+programSK+"#", all), nil
}

func (m *Memory) Bump(_ context.Context, athlete string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.Bumps[AnalysisVersionPK+athlete]++
	return nil
}

func (m *Memory) Dump(table string) []Item {
	m.mu.Lock()
	defer m.mu.Unlock()
	var out []Item
	keys := make([][2]string, 0)
	for k := range m.table(table) {
		keys = append(keys, k)
	}
	sort.Slice(keys, func(i, j int) bool {
		if keys[i][0] != keys[j][0] {
			return keys[i][0] < keys[j][0]
		}
		return keys[i][1] < keys[j][1]
	})
	for _, k := range keys {
		out = append(out, copyOf(m.table(table)[k]))
	}
	return out
}
