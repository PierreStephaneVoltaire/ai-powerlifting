package store

import "context"

type Item = map[string]any

type Field struct {
	Name  string
	Value any
}

type EntryUpdate struct {
	UpdatedAt string
	Set       []Field
	Remove    []string
}

type Projection struct {
	Values       []Field
	SnapshotDate string
	UpdatedAt    string
}

type Entries interface {
	Get(ctx context.Context, pk, sk string) (Item, error)
	Query(ctx context.Context, pk, skPrefix string) ([]Item, error)
	QueryByDate(ctx context.Context, pk string) ([]Item, error)
	Update(ctx context.Context, pk, sk string, update EntryUpdate) error
	SaveProjection(ctx context.Context, pk, sk string, projection Projection) error
}

type Programs interface {
	Pointer(ctx context.Context, pk string) (Item, error)
	Item(ctx context.Context, pk, sk string) (Item, error)
	Sessions(ctx context.Context, pk, programSK string) ([]Item, error)
	GlossaryEntries(ctx context.Context, pk string) ([]Item, error)
}

type AnalysisVersions interface {
	Bump(ctx context.Context, athlete string) error
}

const (
	PointerSK         = "program#current"
	SessionSKPrefix   = "session#"
	EntrySKPrefix     = "COMP#"
	GlossarySKPrefix  = "EXERCISE#"
	GlossaryCatalogPK = "CATALOG"
	GlossaryAthletePK = "ATHLETE#"
	EntriesByDate     = "entries-by-date"
	AnalysisVersionPK = "pl:analysis-version:"
)
