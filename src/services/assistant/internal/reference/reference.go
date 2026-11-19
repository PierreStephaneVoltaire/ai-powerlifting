package reference

import (
	"context"
	"errors"
	"fmt"
	"math"
	"strings"
	"sync"
	"time"

	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/jackc/pgx/v5/pgxpool"
)

const (
	passageSize      = 1200
	passageOverlap   = 150
	defaultBatchSize = 16
	maxBatchSize     = 64
	maxSearchLimit   = 20
)

type Config struct {
	Pool        *pgxpool.Pool
	S3          *s3.Client
	Bucket      string
	Collections []Collection
	Embed       func(context.Context, string) ([]float32, error)
	EmbedBatch  func(context.Context, []string) ([][]float32, error)
	EmbedDim    int
	BatchSize   int
}

type Collection struct{ Name, Prefix, Scope string }
type SearchRequest struct {
	Collection, Scope, Query, EffectiveDate string
	Limit                                   int
}
type Passage struct {
	Text          string
	SourceKey     string
	Edition       string
	EffectiveDate *time.Time
	Page          int
}

type Store struct {
	config Config
	start  sync.Once
}

func New(config Config) (*Store, error) {
	if config.Pool == nil || config.S3 == nil || config.Embed == nil || config.EmbedBatch == nil || config.Bucket == "" || config.EmbedDim <= 0 {
		return nil, errors.New("reference store requires pool, S3, bucket, embedder and positive embedding dimension")
	}
	if len(config.Collections) == 0 {
		return nil, errors.New("reference store requires collections")
	}
	seen := make(map[string]bool, len(config.Collections))
	for _, collection := range config.Collections {
		if collection.Name == "" || collection.Prefix == "" || collection.Scope == "" || seen[collection.Name] {
			return nil, errors.New("reference collections require unique names, prefixes and scopes")
		}
		seen[collection.Name] = true
	}
	if config.BatchSize <= 0 {
		config.BatchSize = defaultBatchSize
	}
	if config.BatchSize > maxBatchSize {
		config.BatchSize = maxBatchSize
	}
	return &Store{config: config}, nil
}

func (s *Store) Start(ctx context.Context) error {
	if err := retryBootstrap(ctx, s.bootstrap, time.Second); err != nil {
		return err
	}
	s.start.Do(func() {
		for _, collection := range s.config.Collections {
			go s.retryCollection(ctx, collection)
		}
	})
	return nil
}

func (s *Store) Search(ctx context.Context, request SearchRequest) ([]Passage, error) {
	var collection *Collection
	for i := range s.config.Collections {
		if s.config.Collections[i].Name == request.Collection {
			collection = &s.config.Collections[i]
			break
		}
	}
	validScope := collection != nil && request.Scope == collection.Scope
	if collection != nil && collection.Scope == "federation:*" && strings.HasPrefix(request.Scope, "federation:") && len(strings.TrimPrefix(request.Scope, "federation:")) > 0 {
		validScope = true
	}
	if !validScope || strings.TrimSpace(request.Query) == "" {
		return nil, errors.New("invalid reference search scope or query")
	}
	if request.Limit <= 0 {
		request.Limit = 5
	}
	if request.Limit > maxSearchLimit {
		request.Limit = maxSearchLimit
	}
	var effectiveDate any
	if request.EffectiveDate != "" {
		parsed, err := time.Parse("2006-01-02", request.EffectiveDate)
		if err != nil {
			return nil, errors.New("invalid effective date")
		}
		effectiveDate = parsed
	}
	vector, err := s.config.Embed(ctx, request.Query)
	if err != nil {
		return nil, err
	}
	if err := validateVector(vector, s.config.EmbedDim); err != nil {
		return nil, err
	}
	rows, err := s.config.Pool.Query(ctx, `WITH scoped AS MATERIALIZED (
 SELECT p.* FROM reference.passages p JOIN reference.documents d
 ON d.collection=p.collection AND d.source_key=p.source_key AND d.version_id=p.version_id
 WHERE p.collection=$1 AND p.scope=$2 AND ($5::date IS NULL OR p.effective_date IS NULL OR p.effective_date <= $5::date)
 ), candidates AS (
 (SELECT *, 1 AS lexical FROM scoped WHERE to_tsvector('simple', text) @@ plainto_tsquery('simple', $6)
 ORDER BY ts_rank_cd(to_tsvector('simple', text), plainto_tsquery('simple', $6)) DESC LIMIT $4)
 UNION ALL
 (SELECT *, 0 AS lexical FROM scoped ORDER BY embedding <-> $3::vector LIMIT $4)
 )
 SELECT text, source_key, edition, effective_date, page FROM candidates
 GROUP BY text,source_key,edition,effective_date,page,embedding
 ORDER BY MAX(lexical) DESC, embedding <-> $3::vector LIMIT $4`, collection.Name, request.Scope, vectorLiteral(vector), request.Limit, effectiveDate, request.Query)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	passages := make([]Passage, 0, request.Limit)
	for rows.Next() {
		var passage Passage
		if err := rows.Scan(&passage.Text, &passage.SourceKey, &passage.Edition, &passage.EffectiveDate, &passage.Page); err != nil {
			return nil, err
		}
		passages = append(passages, passage)
	}
	return passages, rows.Err()
}

func validateVector(vector []float32, dim int) error {
	if len(vector) != dim {
		return fmt.Errorf("embedding has %d dimensions, want %d", len(vector), dim)
	}
	for _, value := range vector {
		if math.IsNaN(float64(value)) || math.IsInf(float64(value), 0) {
			return errors.New("embedding contains a non-finite value")
		}
	}
	return nil
}

func vectorLiteral(vector []float32) string {
	var out strings.Builder
	out.WriteByte('[')
	for i, value := range vector {
		if i > 0 {
			out.WriteByte(',')
		}
		fmt.Fprintf(&out, "%g", value)
	}
	out.WriteByte(']')
	return out.String()
}
