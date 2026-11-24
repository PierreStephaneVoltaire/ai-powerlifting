package library

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"sort"
	"time"

	"powerlifting/templates/internal/payload"
)

var ErrNotFound = errors.New("template not found")
var ErrForbidden = errors.New("template mutation requires the original author")
var ErrConflict = errors.New("template index conflict")
var ErrValidation = errors.New("invalid template")

type Backend interface {
	Get(context.Context, string, string) (map[string]any, error)
	Commit(context.Context, map[string]any, bool, *ImportClaim, map[string]any, string) error
}

type ImportClaim struct{ Athlete, ImportID, ClaimID string }

type Library struct {
	Backend   Backend
	Partition string
	Now       func() time.Time
}

func (s Library) partition() string {
	if s.Partition != "" {
		return s.Partition
	}
	return "template_library"
}
func (s Library) now() string {
	if s.Now != nil {
		return s.Now().UTC().Format(time.RFC3339Nano)
	}
	return time.Now().UTC().Format(time.RFC3339Nano)
}
func stringValue(v any) string {
	if s, ok := v.(string); ok {
		return s
	}
	return ""
}
func metadata(item map[string]any) map[string]any {
	if meta, ok := item["meta"].(map[string]any); ok {
		return meta
	}
	return item
}
func owns(item map[string]any, owners []string) bool {
	author := stringValue(metadata(item)["author_pk"])
	if author == "" {
		return false
	}
	for _, owner := range owners {
		if owner == author {
			return true
		}
	}
	return false
}
func visible(item map[string]any, owners []string) bool {
	published, exists := metadata(item)["published"]
	if !exists {
		return true
	}
	b, _ := published.(bool)
	return b || owns(item, owners)
}
func summary(item map[string]any) map[string]any {
	meta := metadata(item)
	out := map[string]any{"sk": item["sk"]}
	for _, key := range []string{"name", "source_filename", "source_file_hash", "estimated_weeks", "days_per_week", "created_at", "updated_at", "author", "author_pk", "published_at", "import_job_id"} {
		out[key] = meta[key]
	}
	archived, _ := meta["archived"].(bool)
	out["archived"] = archived
	published, exists := meta["published"].(bool)
	out["published"] = !exists || published
	return out
}
func (s Library) index(ctx context.Context) ([]map[string]any, string, error) {
	index, err := s.Backend.Get(ctx, s.partition(), "template#index")
	if err != nil {
		return nil, "", err
	}
	result := []map[string]any{}
	switch entries := index["templates"].(type) {
	case []any:
		for _, entry := range entries {
			if m, ok := entry.(map[string]any); ok {
				result = append(result, m)
			}
		}
	case []map[string]any:
		result = append(result, entries...)
	}
	return result, stringValue(index["index_revision"]), nil
}
func (s Library) List(ctx context.Context, owners []string, includeArchived bool) ([]map[string]any, error) {
	entries, _, err := s.index(ctx)
	if err != nil {
		return nil, err
	}
	result := []map[string]any{}
	for _, entry := range entries {
		archived, _ := entry["archived"].(bool)
		if !visible(entry, owners) || (archived && !includeArchived) {
			continue
		}
		row := map[string]any{}
		for k, v := range entry {
			row[k] = v
		}
		row["is_owner"] = owns(entry, owners)
		result = append(result, row)
	}
	sort.SliceStable(result, func(i, j int) bool {
		return stringValue(result[i]["updated_at"]) > stringValue(result[j]["updated_at"])
	})
	return result, nil
}
func (s Library) Get(ctx context.Context, sk string, owners []string) (map[string]any, error) {
	item, err := s.Backend.Get(ctx, s.partition(), sk)
	if err != nil {
		return nil, err
	}
	if item == nil || !visible(item, owners) {
		return nil, ErrNotFound
	}
	return item, nil
}
func (s Library) write(ctx context.Context, item map[string]any) error {
	return s.commit(ctx, item, false, nil)
}
func (s Library) commit(ctx context.Context, item map[string]any, remove bool, claim *ImportClaim) error {
	for attempt := 0; attempt < 12; attempt++ {
		entries, revision, err := s.index(ctx)
		if err != nil {
			return err
		}
		out := make([]map[string]any, 0, len(entries)+1)
		for _, entry := range entries {
			if entry["sk"] != item["sk"] {
				out = append(out, entry)
			}
		}
		if !remove {
			out = append(out, summary(item))
		}
		sort.SliceStable(out, func(i, j int) bool { return stringValue(out[i]["created_at"]) < stringValue(out[j]["created_at"]) })
		var token [16]byte
		if _, err = rand.Read(token[:]); err != nil {
			return err
		}
		index := map[string]any{"pk": s.partition(), "sk": "template#index", "templates": out, "updated_at": s.now(), "index_revision": hex.EncodeToString(token[:])}
		err = s.Backend.Commit(ctx, item, remove, claim, index, revision)
		if !errors.Is(err, ErrConflict) {
			return err
		}
	}
	return ErrConflict
}
func validate(item map[string]any) error {
	sessions, _ := item["sessions"].([]any)
	for _, raw := range sessions {
		session, ok := raw.(map[string]any)
		if !ok {
			return fmt.Errorf("%w: invalid template session", ErrValidation)
		}
		exercises, _ := session["exercises"].([]any)
		for _, entry := range exercises {
			exercise, ok := entry.(map[string]any)
			if !ok {
				return fmt.Errorf("%w: invalid template exercise", ErrValidation)
			}
			if err := payload.NormalizePrescription(exercise); err != nil {
				return fmt.Errorf("%w: %s", ErrValidation, err)
			}
		}
	}
	return nil
}
func (s Library) Create(ctx context.Context, input map[string]any, actor, author string, published bool) (string, error) {
	return s.create(ctx, input, actor, author, published, "", nil)
}

func (s Library) CreateImport(ctx context.Context, input map[string]any, actor, author string, claim ImportClaim) (string, error) {
	hash := sha256.Sum256([]byte(claim.Athlete + ":" + claim.ImportID))
	sk := "template#import-" + hex.EncodeToString(hash[:16])
	if existing, err := s.Backend.Get(ctx, s.partition(), sk); err != nil {
		return "", err
	} else if existing != nil {
		return sk, nil
	}
	created, err := s.create(ctx, input, actor, author, false, sk, &claim)
	if err != nil {
		if existing, lookup := s.Backend.Get(ctx, s.partition(), sk); lookup == nil && existing != nil {
			return sk, nil
		}
	}
	return created, err
}

func (s Library) create(ctx context.Context, input map[string]any, actor, author string, published bool, sk string, claim *ImportClaim) (string, error) {
	if actor == "" {
		return "", ErrForbidden
	}
	item, err := payload.Prepare(input, true)
	if err != nil {
		return "", err
	}
	if err := validate(item); err != nil {
		return "", err
	}
	var random [4]byte
	if _, err := rand.Read(random[:]); err != nil {
		return "", err
	}
	now := s.now()
	if sk == "" {
		sk = fmt.Sprintf("template#%s#%s", time.Now().UTC().Format("20060102T150405.000000Z"), hex.EncodeToString(random[:]))
	}
	meta := item["meta"].(map[string]any)
	if _, ok := meta["created_at"]; !ok {
		meta["created_at"] = now
	}
	meta["updated_at"] = now
	if existing, ok := meta["published"].(bool); ok {
		published = existing
	}
	meta["published"] = published
	if published {
		if meta["published_at"] == nil {
			meta["published_at"] = now
		}
	} else {
		delete(meta, "published_at")
	}
	meta["author_pk"] = actor
	if author == "" {
		author = actor
	}
	meta["author"] = author
	item["pk"], item["sk"] = s.partition(), sk
	delete(item, "is_owner")
	if err := s.commit(ctx, item, false, claim); err != nil {
		return "", err
	}
	return sk, nil
}

func (s Library) Update(ctx context.Context, sk string, input map[string]any, owners []string) error {
	existing, err := s.Get(ctx, sk, owners)
	if err != nil {
		return err
	}
	if !owns(existing, owners) {
		return ErrForbidden
	}
	incoming, err := payload.Prepare(input, false)
	if err != nil {
		return err
	}
	if err := validate(incoming); err != nil {
		return err
	}
	oldMeta := metadata(existing)
	inMeta := metadata(incoming)
	meta := map[string]any{}
	for key, value := range oldMeta {
		meta[key] = value
	}
	for key, value := range inMeta {
		meta[key] = value
	}
	for _, key := range []string{"created_at", "author_pk", "author", "published", "published_at", "import_job_id"} {
		if value, ok := oldMeta[key]; ok {
			meta[key] = value
		} else {
			delete(meta, key)
		}
	}
	if _, ok := meta["created_at"]; !ok {
		meta["created_at"] = s.now()
	}
	if _, ok := meta["published"]; !ok {
		meta["published"] = true
	}
	meta["updated_at"] = s.now()
	for key, value := range incoming {
		existing[key] = value
	}
	existing["meta"], existing["pk"], existing["sk"] = meta, s.partition(), sk
	delete(existing, "is_owner")
	return s.write(ctx, existing)
}

func (s Library) SetStatus(ctx context.Context, sk string, owners []string, field string, enabled bool) error {
	if field != "archived" && field != "published" {
		return errors.New("unknown template status")
	}
	item, err := s.Get(ctx, sk, owners)
	if err != nil {
		return err
	}
	if !owns(item, owners) {
		return ErrForbidden
	}
	meta, ok := item["meta"].(map[string]any)
	if !ok {
		meta = map[string]any{}
		item["meta"] = meta
	}
	now := s.now()
	meta[field], meta["updated_at"] = enabled, now
	if field == "published" {
		if enabled {
			meta["published_at"] = now
		} else {
			delete(meta, "published_at")
		}
	}
	return s.write(ctx, item)
}

func (s Library) SetEvaluation(ctx context.Context, sk string, owners []string, evaluation map[string]any, context string) error {
	item, err := s.Get(ctx, sk, owners)
	if err != nil {
		return err
	}
	if !owns(item, owners) {
		return ErrForbidden
	}
	meta, ok := item["meta"].(map[string]any)
	if !ok {
		meta = map[string]any{}
		item["meta"] = meta
	}
	meta["ai_evaluation"], meta["program_context"], meta["updated_at"] = evaluation, context, s.now()
	return s.write(ctx, item)
}

func (s Library) Delete(ctx context.Context, sk string, owners []string) error {
	item, err := s.Backend.Get(ctx, s.partition(), sk)
	if err != nil {
		return err
	}
	if item == nil {
		return ErrNotFound
	}
	if !owns(item, owners) {
		return ErrForbidden
	}
	return s.commit(ctx, item, true, nil)
}

func (s Library) Copy(ctx context.Context, sk, name, actor, author string, owners []string) (string, error) {
	if actor == "" {
		return "", ErrForbidden
	}
	item, err := s.Get(ctx, sk, owners)
	if err != nil {
		return "", err
	}
	cloned, err := payload.Clone(item)
	if err != nil {
		return "", err
	}
	meta, ok := cloned["meta"].(map[string]any)
	if !ok {
		meta = map[string]any{}
		cloned["meta"] = meta
	}
	now := s.now()
	meta["name"], meta["derived_from_template_sk"] = name, sk
	meta["created_at"], meta["updated_at"], meta["archived"], meta["published"] = now, now, false, false
	meta["author_pk"] = actor
	if author == "" {
		author = actor
	}
	meta["author"] = author
	delete(meta, "published_at")
	hash := sha256.Sum256([]byte(sk + ":" + name))
	newSK := "template#copy-" + hex.EncodeToString(hash[:16])
	cloned["pk"], cloned["sk"] = s.partition(), newSK
	delete(cloned, "is_owner")
	if err := s.write(ctx, cloned); err != nil {
		return "", err
	}
	return newSK, nil
}
