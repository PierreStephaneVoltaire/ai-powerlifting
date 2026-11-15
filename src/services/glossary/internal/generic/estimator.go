package generic

import (
	"context"
	"fmt"
	"log/slog"
	"strings"
	"sync"
	"time"

	"powerlifting/glossary/internal/coach"
	"powerlifting/glossary/internal/exercise"
	"powerlifting/glossary/internal/store"
)

const (
	Operation   = "glossary_generic_estimate"
	maxAttempts = 3
	batchSize   = 5
	flightLimit = 20 * time.Minute
)

var defaultProfile = exercise.Item{"axial": 0.3, "neural": 0.3, "peripheral": 0.5, "systemic": 0.3}

type Estimator struct {
	Store    store.Store
	Coach    coach.Client
	Interval time.Duration
	Now      func() time.Time

	mu     sync.Mutex
	flight map[string]time.Time
}

func (e *Estimator) timestamp() string {
	return e.Now().UTC().Format(time.RFC3339Nano)
}

func (e *Estimator) Create(ctx context.Context, definition exercise.Item, athlete, person string) (bool, error) {
	now := e.timestamp()
	item := exercise.Definition(definition)
	item["created_by"], item["created_by_person"] = athlete, person
	item["created_at"], item["updated_at"] = now, now
	item["generic_status"], item["generic_attempts"] = exercise.GenericPending, float64(0)
	item["generic_pending"] = store.PendingMarker
	return e.Store.CreateCatalog(ctx, item)
}

func (e *Estimator) Requeue(ctx context.Context, id string) error {
	return e.Store.Update(ctx, store.CatalogKey(id), store.Patch{Set: exercise.Item{
		"generic_status": exercise.GenericPending, "generic_attempts": float64(0), "generic_pending": store.PendingMarker, "updated_at": e.timestamp(),
	}})
}

func (e *Estimator) Complete(ctx context.Context, id string, estimated exercise.Item) error {
	set := exercise.Item{"generic_status": exercise.GenericReady, "updated_at": e.timestamp()}
	for key, value := range estimated {
		set[key] = value
	}
	return e.Store.Update(ctx, store.CatalogKey(id), store.Patch{Set: set, Remove: []string{"generic_pending"}})
}

func (e *Estimator) Done(id string) {
	e.mu.Lock()
	defer e.mu.Unlock()
	delete(e.flight, id)
}

func (e *Estimator) Fail(ctx context.Context, id string) {
	e.Done(id)
	item, err := e.Store.Get(ctx, store.CatalogKey(id))
	if err != nil || item == nil {
		slog.Warn("generic failure not recorded", "id", id, "error", err)
		return
	}
	attempts, _ := item["generic_attempts"].(float64)
	patch := store.Patch{Set: exercise.Item{"generic_attempts": attempts + 1, "updated_at": e.timestamp()}}
	if attempts+1 >= maxAttempts {
		patch.Set["generic_status"] = exercise.GenericFailed
		if _, estimated := item["fatigue_profile"]; !estimated {
			patch.Set["fatigue_profile"] = defaultProfile
			patch.Set["fatigue_profile_source"] = "default"
			patch.Set["fatigue_profile_reasoning"] = "Generic estimate unavailable"
		}
		patch.Remove = []string{"generic_pending"}
	}
	if err := e.Store.Update(ctx, store.CatalogKey(id), patch); err != nil {
		slog.Warn("generic failure not recorded", "id", id, "error", err)
	}
}

func (e *Estimator) Run(ctx context.Context) {
	ticker := time.NewTicker(e.Interval)
	defer ticker.Stop()
	for {
		select {
		case <-ticker.C:
			e.Tick(ctx)
		case <-ctx.Done():
			return
		}
	}
}

func (e *Estimator) claim(id string) (claimed, expired bool) {
	e.mu.Lock()
	defer e.mu.Unlock()
	if e.flight == nil {
		e.flight = map[string]time.Time{}
	}
	if started, running := e.flight[id]; running {
		if e.Now().Sub(started) < flightLimit {
			return false, false
		}
		delete(e.flight, id)
		return false, true
	}
	e.flight[id] = e.Now()
	return true, false
}

func (e *Estimator) Tick(ctx context.Context) {
	pending, err := e.Store.Pending(ctx, batchSize)
	if err != nil {
		slog.Error("generic pending query failed", "error", err)
		return
	}
	var claimed []exercise.Item
	for _, item := range pending {
		id := exercise.Text(item, "id")
		fresh, expired := e.claim(id)
		if expired {
			e.Fail(ctx, id)
			continue
		}
		if !fresh {
			continue
		}
		if exercise.Text(item, "created_by") == "" {
			e.Fail(ctx, id)
			continue
		}
		claimed = append(claimed, item)
	}
	if len(claimed) == 0 {
		return
	}
	ids := make([]any, 0, len(claimed))
	keys := make([]string, 0, len(claimed))
	for _, item := range claimed {
		attempts, _ := item["generic_attempts"].(float64)
		ids = append(ids, exercise.Text(item, "id"))
		keys = append(keys, fmt.Sprintf("%s:%.0f", exercise.Text(item, "id"), attempts))
	}
	athlete := exercise.Text(claimed[0], "created_by")
	person := exercise.Text(claimed[0], "created_by_person")
	if person == "" {
		person = athlete
	}
	_, err = e.Coach.Submit(ctx, coach.Submission{
		Operation: Operation, Arguments: map[string]any{"ids": ids, "pk": athlete},
		Athlete: athlete, Person: person, Key: strings.Join(keys, ","),
	})
	if err != nil {
		slog.Warn("generic estimate submit failed", "ids", ids, "error", err)
		for _, id := range ids {
			e.Fail(ctx, id.(string))
		}
	}
}
