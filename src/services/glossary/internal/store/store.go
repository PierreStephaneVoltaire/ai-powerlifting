package store

import (
	"context"

	"powerlifting/glossary/internal/exercise"
)

const (
	CatalogPK     = "CATALOG"
	PendingMarker = "1"
	catalogNamePK = "CATALOG_NAME"
	athletePrefix = "ATHLETE#"
	sortPrefix    = "EXERCISE#"
	genericIndex  = "generic-pending"
)

type Item = exercise.Item

type Key struct{ PK, SK string }

func CatalogKey(id string) Key { return Key{CatalogPK, sortPrefix + id} }

func OverlayKey(athlete, id string) Key { return Key{AthletePK(athlete), sortPrefix + id} }

func AthletePK(athlete string) string { return athletePrefix + athlete }

type Patch struct {
	Set    Item
	Remove []string
}

type Store interface {
	Get(ctx context.Context, key Key) (Item, error)
	List(ctx context.Context, pk string) ([]Item, error)
	Update(ctx context.Context, key Key, patch Patch) error
	CreateCatalog(ctx context.Context, item Item) (bool, error)
	Pending(ctx context.Context, limit int) ([]Item, error)
}
