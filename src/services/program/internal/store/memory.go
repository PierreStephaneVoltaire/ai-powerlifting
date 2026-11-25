package store

import (
	"context"
	"encoding/json"
	"fmt"
	"sort"
	"strings"
	"sync"

	"powerlifting/program/internal/pyval"
)

type Memory struct {
	mu     sync.Mutex
	tables map[Table]map[Key]Item
	Writes int
}

func NewMemory() *Memory {
	return &Memory{tables: map[Table]map[Key]Item{}}
}

func (m *Memory) SaveProgram(_ context.Context, tables Tables, athlete string, program Item, expectedSK, currentBlockID, now, importID, importClaim string) error {
	round, err := stored(program)
	if err != nil {
		return err
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	pointerKey := Key{PK: athlete, SK: PointerSK}
	current := m.rows(tables.Health)[pointerKey]
	if importID != "" {
		claim := m.rows(tables.Health)[Key{PK: athlete, SK: "import#pending#" + importID}]
		if claim["status"] != "applying" || claim["apply_claim_id"] != importClaim {
			return fmt.Errorf("import claim changed")
		}
	}
	if current == nil || pyval.Str2(current["ref_sk"]) != expectedSK {
		return fmt.Errorf("program changed during save")
	}
	m.rows(tables.Health)[keyOf(round)] = round
	current["current_block_id"] = currentBlockID
	current["updated_at"] = now
	m.Writes++
	return nil
}

func (m *Memory) rows(table Table) map[Key]Item {
	if m.tables[table] == nil {
		m.tables[table] = map[Key]Item{}
	}
	return m.tables[table]
}

func keyOf(item Item) Key {
	pk, _ := item["pk"].(string)
	sk, _ := item["sk"].(string)
	return Key{PK: pk, SK: sk}
}

func stored(item Item) (Item, error) {
	attrs, err := ToAttrMap(item)
	if err != nil {
		return nil, err
	}
	round := FromAttrMap(attrs)
	normalizeNumbers(round)
	return round, nil
}

func normalizeNumbers(value any) {
	switch typed := value.(type) {
	case map[string]any:
		for key, item := range typed {
			typed[key] = normalized(item)
		}
	case []any:
		for index, item := range typed {
			typed[index] = normalized(item)
		}
	}
}

func normalized(value any) any {
	switch typed := value.(type) {
	case map[string]any:
		normalizeNumbers(typed)
		return typed
	case []any:
		normalizeNumbers(typed)
		return typed
	}
	if number, ok := value.(json.Number); ok {
		return pyval.Normalize(number)
	}
	return value
}

func (m *Memory) Seed(table Table, items ...Item) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	for _, item := range items {
		round, err := stored(item)
		if err != nil {
			return err
		}
		m.rows(table)[keyOf(round)] = round
	}
	return nil
}

func (m *Memory) Get(_ context.Context, table Table, key Key, options GetOptions) (Item, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	item, ok := m.rows(table)[key]
	if !ok {
		return nil, nil
	}
	copied := pyval.CopyMap(item)
	if len(options.Projection) == 0 {
		return copied, nil
	}
	projected := Item{}
	for _, path := range options.Projection {
		project(projected, copied, strings.Split(path, "."))
	}
	return projected, nil
}

func project(out, source map[string]any, path []string) {
	value, ok := source[path[0]]
	if !ok {
		return
	}
	if len(path) == 1 {
		out[path[0]] = value
		return
	}
	nested, ok := value.(map[string]any)
	if !ok {
		return
	}
	target, _ := out[path[0]].(map[string]any)
	if target == nil {
		target = map[string]any{}
	}
	project(target, nested, path[1:])
	out[path[0]] = target
}

func (m *Memory) Put(_ context.Context, table Table, item Item) error {
	round, err := stored(item)
	if err != nil {
		return err
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	m.rows(table)[keyOf(round)] = round
	m.Writes++
	return nil
}

func (m *Memory) Query(_ context.Context, query Query) ([]Item, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	var matched []Item
	for _, item := range m.rows(query.Table) {
		pk, _ := item[query.pkAttr()].(string)
		sk, ok := item[query.skAttr()].(string)
		if pk != query.PK || !ok || !query.matches(sk) {
			continue
		}
		matched = append(matched, pyval.CopyMap(item))
	}
	skAttr := query.skAttr()
	sort.SliceStable(matched, func(i, j int) bool {
		a, _ := matched[i][skAttr].(string)
		b, _ := matched[j][skAttr].(string)
		if a != b {
			return a < b
		}
		ka, kb := keyOf(matched[i]), keyOf(matched[j])
		return ka.SK < kb.SK
	})
	return matched, nil
}

func (m *Memory) BatchPut(ctx context.Context, table Table, items []Item) error {
	for _, item := range items {
		if err := m.Put(ctx, table, item); err != nil {
			return err
		}
	}
	return nil
}

func (m *Memory) BatchDelete(_ context.Context, table Table, keys []Key) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	for _, key := range keys {
		delete(m.rows(table), key)
	}
	return nil
}

func (m *Memory) Dump(table Table) []Item {
	m.mu.Lock()
	defer m.mu.Unlock()
	items := make([]Item, 0, len(m.rows(table)))
	for _, item := range m.rows(table) {
		items = append(items, pyval.CopyMap(item))
	}
	sort.Slice(items, func(i, j int) bool {
		a, b := keyOf(items[i]), keyOf(items[j])
		if a.PK != b.PK {
			return a.PK < b.PK
		}
		return a.SK < b.SK
	})
	return items
}
