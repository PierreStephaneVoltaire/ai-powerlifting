package projection

const narrowTransfer = 0.9

type transfer [3]float64

type Glossary struct {
	entries map[string]glossaryEntry
}

type glossaryEntry struct {
	archived bool
	transfer *transfer
}

func GlossaryFromItems(items []any) Glossary {
	glossary := Glossary{entries: map[string]glossaryEntry{}}
	for _, raw := range items {
		item, ok := raw.(map[string]any)
		if !ok {
			continue
		}
		name, _ := item["name"].(string)
		key := NormalizeName(name)
		entry := glossaryEntry{archived: truthy(item["archived"])}
		if values, ok := item["lift_transfer"].(map[string]any); ok {
			parsed := transfer{}
			for _, lift := range lifts {
				parsed[lift] = min(max(numOf(values[lift.Key()]), 0), 1)
			}
			entry.transfer = &parsed
		}
		existing, present := glossary.entries[key]
		if present && (!existing.archived || entry.archived) {
			continue
		}
		glossary.entries[key] = entry
	}
	return glossary
}

func truthy(value any) bool {
	switch typed := value.(type) {
	case nil:
		return false
	case bool:
		return typed
	case string:
		return typed != ""
	}
	return numOf(value) != 0
}

func (g Glossary) ResolveLift(key string) (Lift, bool) {
	if lift, ok := liftFromName(key); ok {
		return lift, true
	}
	entry, present := g.entries[key]
	if !present || entry.transfer == nil {
		return 0, false
	}
	best, strongest := Lift(0), 0.0
	for _, lift := range lifts {
		if value := entry.transfer[lift]; value > 0 && value >= strongest {
			best, strongest = lift, value
		}
	}
	if strongest < narrowTransfer {
		return 0, false
	}
	return best, true
}
