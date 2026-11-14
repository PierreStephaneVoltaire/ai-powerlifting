package lookup

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"log/slog"
	"time"

	"powerlifting/prompt-cache/internal/decision"
	"powerlifting/prompt-cache/internal/entry"
	"powerlifting/prompt-cache/internal/semantic"
	"powerlifting/prompt-cache/internal/store"
)

type Entries interface {
	ExactID(ctx context.Context, athlete, operation, analysisVersion, hash string) (string, bool, error)
	Entry(ctx context.Context, id string) (entry.Entry, bool, error)
	Save(ctx context.Context, saved entry.Entry, hash string) error
}

type Index interface {
	Find(ctx context.Context, athlete, operation, query string) ([]semantic.Metadata, error)
	Store(ctx context.Context, athlete, operation, text string, metadata semantic.Metadata) error
}

type Service struct {
	Entries         Entries
	Index           Index
	Decider         decision.Decider
	CandidateLimit  int
	SemanticTimeout time.Duration
	DecisionTimeout time.Duration
	StoreTimeout    time.Duration
}

var _ Entries = store.Valkey{}

type Query struct {
	Athlete   string          `json:"athlete"`
	Operation string          `json:"operation"`
	Request   json.RawMessage `json:"request"`
	Context   entry.Context   `json:"context"`
}

type Save struct {
	Query
	Response json.RawMessage `json:"response"`
}

type Result struct {
	Hit      bool              `json:"hit"`
	Layer    string            `json:"layer,omitempty"`
	Response json.RawMessage   `json:"response,omitempty"`
	EntryID  string            `json:"entry_id,omitempty"`
	Decision *decision.Verdict `json:"decision,omitempty"`
}

func (s Service) Lookup(ctx context.Context, query Query) Result {
	started := time.Now()
	result, reason := s.find(ctx, query)
	layer := result.Layer
	if !result.Hit {
		layer = "none"
	}
	slog.Info("prompt_cache_lookup", "athlete", query.Athlete, "operation", query.Operation, "layer", layer, "reason", reason, "latency_ms", time.Since(started).Milliseconds())
	return result
}

func (s Service) find(ctx context.Context, query Query) (Result, string) {
	hash, err := entry.Hash(query.Request)
	if err != nil {
		return Result{}, "invalid_request"
	}
	if id, found, err := s.Entries.ExactID(ctx, query.Athlete, query.Operation, query.Context.AnalysisVersion, hash); err != nil {
		slog.Warn("prompt cache exact read failed", "error", err)
	} else if found {
		if stored, ok := s.loadEntry(ctx, id); ok {
			return Result{Hit: true, Layer: "exact", Response: stored.Response, EntryID: stored.ID}, "exact"
		}
	}
	return s.semantic(ctx, query)
}

func (s Service) loadEntry(ctx context.Context, id string) (entry.Entry, bool) {
	stored, found, err := s.Entries.Entry(ctx, id)
	if err != nil {
		slog.Warn("prompt cache entry read failed", "error", err)
		return entry.Entry{}, false
	}
	return stored, found
}

func (s Service) semantic(ctx context.Context, query Query) (Result, string) {
	candidates := s.candidates(ctx, query)
	if len(candidates) == 0 {
		return Result{}, decision.None
	}
	decideCtx, cancel := context.WithTimeout(ctx, s.DecisionTimeout)
	defer cancel()
	verdict, err := s.Decider.Decide(decideCtx, decision.Input{
		Athlete: query.Athlete, Operation: query.Operation, Request: query.Request, Context: query.Context, Candidates: candidates,
	})
	if err != nil {
		slog.Warn("prompt cache decision failed", "error", err)
		return Result{}, "decision_error"
	}
	if verdict.Reason != decision.Same {
		return Result{Decision: &verdict}, verdict.Reason
	}
	for _, candidate := range candidates {
		if candidate.EntryID == verdict.EntryID {
			return Result{Hit: true, Layer: "semantic", Response: candidate.Response, EntryID: candidate.EntryID, Decision: &verdict}, decision.Same
		}
	}
	return Result{}, "unknown_entry"
}

func (s Service) candidates(ctx context.Context, query Query) []decision.Candidate {
	findCtx, cancel := context.WithTimeout(ctx, s.SemanticTimeout)
	defer cancel()
	found, err := s.Index.Find(findCtx, query.Athlete, query.Operation, entry.SearchableText(query.Request))
	if err != nil {
		slog.Warn("prompt cache semantic search failed", "error", err)
		return nil
	}
	seen := map[string]bool{}
	candidates := []decision.Candidate{}
	for _, metadata := range found {
		if len(candidates) >= s.CandidateLimit {
			break
		}
		if seen[metadata.EntryID] {
			continue
		}
		seen[metadata.EntryID] = true
		stored, ok := s.loadEntry(ctx, metadata.EntryID)
		if !ok || stored.Athlete != query.Athlete || stored.Operation != query.Operation {
			continue
		}
		candidates = append(candidates, decision.Candidate{EntryID: stored.ID, Request: stored.Request, Response: stored.Response, Context: stored.Context})
	}
	return candidates
}

func (s Service) Store(ctx context.Context, save Save) (string, error) {
	hash, err := entry.Hash(save.Request)
	if err != nil {
		return "", err
	}
	id, err := newID()
	if err != nil {
		return "", err
	}
	saved := entry.Entry{ID: id, Athlete: save.Athlete, Operation: save.Operation, Request: save.Request, Response: save.Response, Context: save.Context}
	if err := s.Entries.Save(ctx, saved, hash); err != nil {
		return "", err
	}
	indexCtx, cancel := context.WithTimeout(ctx, s.StoreTimeout)
	defer cancel()
	metadata := semantic.Metadata{EntryID: id, Date: save.Context.Date, AnalysisVersion: save.Context.AnalysisVersion}
	if err := s.Index.Store(indexCtx, save.Athlete, save.Operation, entry.SearchableText(save.Request), metadata); err != nil {
		slog.Warn("prompt cache semantic store failed", "error", err)
	}
	return id, nil
}

func newID() (string, error) {
	buffer := make([]byte, 16)
	if _, err := rand.Read(buffer); err != nil {
		return "", err
	}
	return hex.EncodeToString(buffer), nil
}
