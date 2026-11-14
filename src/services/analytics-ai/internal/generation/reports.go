package generation

import (
	"context"
	"time"

	"powerlifting/analytics-ai/internal/pyjson"
)

const (
	inflightTTL = time.Hour
	swapRetries = 5
)

type Reports struct {
	Pointers Pointers
	Objects  Objects
	Prefix   string
}

func pointerKey(athlete, id string) string { return "pl:report:" + athlete + ":" + id }

func (r Reports) objectKey(athlete, id string) string {
	return r.Prefix + "/" + athlete + "/" + id + ".json"
}

func ttl(item Item) time.Duration {
	if Terminal(text(item["status"])) {
		return 0
	}
	return inflightTTL
}

func decodeItem(raw []byte) (Item, error) {
	value, err := pyjson.Decode(raw)
	if err != nil {
		return nil, err
	}
	item, _ := value.(Item)
	return item, nil
}

func (r Reports) load(ctx context.Context, athlete, id string) (string, Item, error) {
	raw, found, err := r.Pointers.Get(ctx, pointerKey(athlete, id))
	if err != nil {
		return "", nil, err
	}
	if found {
		item, err := decodeItem([]byte(raw))
		return raw, item, err
	}
	body, found, err := r.Objects.Get(ctx, r.objectKey(athlete, id))
	if err != nil || !found {
		return "", nil, err
	}
	item, err := decodeItem(body)
	if err != nil {
		return "", nil, err
	}
	delete(item, "result")
	pointer, err := pyjson.Encode(item)
	if err != nil {
		return "", nil, err
	}
	if _, err := r.Pointers.SetNX(ctx, pointerKey(athlete, id), string(pointer), 0); err != nil {
		return "", nil, err
	}
	return string(pointer), item, nil
}

func (r Reports) Get(ctx context.Context, athlete, id string) (Item, error) {
	_, item, err := r.load(ctx, athlete, id)
	return item, err
}

func (r Reports) PutIfAbsent(ctx context.Context, item Item) (bool, error) {
	encoded, err := pyjson.Encode(item)
	if err != nil {
		return false, err
	}
	return r.Pointers.SetNX(ctx, pointerKey(text(item["athlete"]), text(item["generation_id"])), string(encoded), ttl(item))
}

func (r Reports) PutIfCurrent(ctx context.Context, item Item, status string, attempt int) (bool, error) {
	athlete, id := text(item["athlete"]), text(item["generation_id"])
	raw, current, err := r.load(ctx, athlete, id)
	if err != nil || current == nil || text(current["status"]) != status || toInt(current["attempt"]) != attempt {
		return false, err
	}
	encoded, err := pyjson.Encode(item)
	if err != nil {
		return false, err
	}
	return r.Pointers.Swap(ctx, pointerKey(athlete, id), raw, string(encoded), ttl(item))
}

func (r Reports) merge(ctx context.Context, athlete, id string, attempt int, fields Item, result any) error {
	for range swapRetries {
		raw, current, err := r.load(ctx, athlete, id)
		if err != nil || current == nil || toInt(current["attempt"]) != attempt {
			return err
		}
		for name, value := range fields {
			current[name] = value
		}
		pointer, err := pyjson.Encode(current)
		if err != nil {
			return err
		}
		if result != nil {
			body := Item{"result": result}
			for name, value := range current {
				body[name] = value
			}
			encoded, err := pyjson.Encode(body)
			if err != nil {
				return err
			}
			if err := r.Objects.Put(ctx, r.objectKey(athlete, id), encoded); err != nil {
				return err
			}
		}
		swapped, err := r.Pointers.Swap(ctx, pointerKey(athlete, id), raw, string(pointer), ttl(current))
		if err != nil || swapped {
			return err
		}
	}
	return nil
}

func (r Reports) Update(ctx context.Context, athlete, id string, attempt int, fields Item) error {
	return r.merge(ctx, athlete, id, attempt, fields, nil)
}

func (r Reports) Save(ctx context.Context, athlete, id string, attempt int, fields Item, result any) error {
	return r.merge(ctx, athlete, id, attempt, fields, result)
}

func (r Reports) Result(ctx context.Context, athlete, id string) (any, error) {
	body, found, err := r.Objects.Get(ctx, r.objectKey(athlete, id))
	if err != nil || !found {
		return nil, err
	}
	item, err := decodeItem(body)
	if err != nil {
		return nil, err
	}
	return item["result"], nil
}
