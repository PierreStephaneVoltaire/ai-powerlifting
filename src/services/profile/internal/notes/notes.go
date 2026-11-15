package notes

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"slices"
	"sort"
	"strings"

	"powerlifting/profile/internal/access"
	"powerlifting/profile/internal/apperr"
	"powerlifting/profile/internal/clock"
	"powerlifting/profile/internal/store"
	"powerlifting/profile/internal/value"
)

var contextDomains = []string{"program", "sessions", "competition"}

type Store struct {
	DB  *store.DB
	Env clock.Env
}

func (s *Store) table() string { return s.DB.Tables.Health }

func plain(message string) error { return apperr.New(422, "validation", message) }

func forbidden(message string) error { return apperr.New(403, "forbidden", message) }

func conflict(message string, revision int, record any) error {
	return apperr.Detailed(409, "conflict", message, map[string]any{"current_revision": value.Int(revision), "current_record": record})
}

func idempotencyConflict() error {
	return apperr.New(409, "conflict", "Idempotency key was already used for another mutation")
}

func asInt(v any) (int, bool) {
	number, ok := v.(json.Number)
	if !ok || strings.ContainsAny(string(number), ".eE") {
		return 0, false
	}
	return value.IntOf(number, 0), true
}

func nonEmptyText(v any) (string, bool) {
	text, ok := v.(string)
	return text, ok && strings.TrimSpace(text) != ""
}

func payloadHash(payload map[string]any) string {
	sum := sha256.Sum256([]byte(value.Dump(payload)))
	return hex.EncodeToString(sum[:])
}

func number(item value.Item, key string, fallback int) int {
	if _, ok := item[key]; !ok {
		return fallback
	}
	return value.IntOf(item[key], fallback)
}

func orEmpty(item value.Item, key string) any {
	if v, ok := item[key]; ok {
		return v
	}
	return ""
}

func publicNote(item value.Item) map[string]any {
	return map[string]any{
		"note_id":    item["note_id"],
		"text":       orEmpty(item, "text"),
		"revision":   value.Int(number(item, "revision", 0)),
		"created_at": orEmpty(item, "created_at"),
		"updated_at": orEmpty(item, "updated_at"),
	}
}

func publicAttachment(item value.Item, snapshot value.Item) map[string]any {
	source := item
	if snapshot != nil {
		source = snapshot
	}
	sourceRevision := number(source, "source_revision", number(item, "source_revision", 0))
	author := orEmpty(item, "author_person_pk")
	if v, ok := source["author_person_pk"]; ok {
		author = v
	}
	return map[string]any{
		"attachment_id":    item["attachment_id"],
		"note_id":          item["note_id"],
		"text":             orEmpty(source, "text"),
		"revision":         value.Int(number(item, "attachment_revision", 0)),
		"source_revision":  value.Int(sourceRevision),
		"author_person_pk": author,
		"context_domain":   orEmpty(item, "context_domain"),
		"context_id":       item["context_id"],
		"attached_at":      orEmpty(item, "attached_at"),
	}
}

func (s *Store) get(ctx context.Context, pk, sk string) (value.Item, error) {
	return s.DB.Get(ctx, s.table(), store.PKSK(pk, sk))
}

func (s *Store) replay(ledger value.Item, hash, actor string) (any, bool, error) {
	if ledger == nil {
		return nil, false, nil
	}
	if ledger["payload_hash"] != hash || ledger["actor"] != actor {
		return nil, false, idempotencyConflict()
	}
	result, _ := ledger["result"].(map[string]any)
	if result == nil {
		result = map[string]any{}
	}
	return result, true, nil
}

func (s *Store) ledgerReplay(ctx context.Context, pk, prefix, key, hash, actor string) (any, bool, error) {
	ledger, err := s.get(ctx, pk, prefix+key)
	if err != nil {
		return nil, false, err
	}
	return s.replay(ledger, hash, actor)
}

func (s *Store) ListPrivate(ctx context.Context, person string) (any, error) {
	rows, err := s.DB.Query(ctx, store.Query{
		Table:      s.table(),
		KeyCond:    "pk = :pk AND begins_with(sk, :prefix)",
		Values:     map[string]any{":pk": person, ":prefix": "Note#"},
		Consistent: true,
	})
	if err != nil {
		return nil, err
	}
	notes := make([]map[string]any, 0, len(rows))
	for _, row := range rows {
		notes = append(notes, publicNote(row))
	}
	sort.SliceStable(notes, func(i, j int) bool { return value.Str(notes[i]["updated_at"]) > value.Str(notes[j]["updated_at"]) })
	out := make([]any, len(notes))
	for i, note := range notes {
		out[i] = note
	}
	return map[string]any{"notes": out}, nil
}

func (s *Store) SavePrivate(ctx context.Context, person string, args map[string]any) (any, error) {
	text, hasText := args["text"].(string)
	if !hasText || strings.TrimSpace(text) == "" {
		return nil, plain("text is required")
	}
	expected, ok := asInt(args["expected_revision"])
	if !ok || expected < 0 {
		return nil, plain("expected_revision must be a nonnegative integer")
	}
	key, ok := nonEmptyText(args["idempotency_key"])
	if !ok {
		return nil, plain("idempotency_key is required")
	}
	hash := payloadHash(map[string]any{"note_id": args["note_id"], "text": text, "expected_revision": value.Int(expected)})
	noteID := args["note_id"]
	if !value.Truthy(noteID) {
		noteID = uuid5("authored-note:" + person + ":" + key)
	}
	id, ok := nonEmptyText(noteID)
	if !ok {
		return nil, plain("note_id must be a nonempty string")
	}
	if result, replayed, err := s.ledgerReplay(ctx, person, "NoteMutation#", key, hash, person); err != nil || replayed {
		return result, err
	}
	sk := "Note#" + id
	current, err := s.get(ctx, person, sk)
	if err != nil {
		return nil, err
	}
	now := s.Env.Stamp()
	ledgerKey := "NoteMutation#" + key
	if current == nil {
		if expected != 0 {
			return nil, conflict("Note revision differs", 0, nil)
		}
		item := value.Item{
			"pk": person, "sk": sk, "note_id": id, "author_person_pk": person, "text": text, "revision": 1,
			"revisions":  []any{map[string]any{"revision": 1, "text": text, "updated_at": now}},
			"created_at": now, "updated_at": now,
		}
		result := publicNote(item)
		err := s.DB.Transact(ctx, []store.Write{
			{Kind: store.WritePut, Table: s.table(), Item: item, Condition: "attribute_not_exists(pk)"},
			{Kind: store.WritePut, Table: s.table(), Item: value.Item{"pk": person, "sk": ledgerKey, "result": result, "payload_hash": hash, "actor": person, "created_at": now}, Condition: "attribute_not_exists(pk)"},
		})
		if err == nil {
			return result, nil
		}
		return s.afterFailure(ctx, err, person, "NoteMutation#", key, hash, sk, true)
	}
	revision := number(current, "revision", 0)
	if expected != revision {
		return nil, conflict("Note revision differs", revision, publicNote(current))
	}
	next := revision + 1
	revisions, _ := current["revisions"].([]any)
	revisions = append(slices.Clone(revisions), map[string]any{"revision": next, "text": text, "updated_at": now})
	result := publicNote(value.Item{"note_id": id, "text": text, "revision": next, "created_at": value.Or(current["created_at"], now), "updated_at": now})
	err = s.DB.Transact(ctx, []store.Write{
		{
			Kind: store.WriteUpdate, Table: s.table(), Key: store.PKSK(person, sk),
			Update:    "SET #text = :text, #revision = :revision, #revisions = :revisions, #updated_at = :updated_at",
			Condition: "#revision = :expected_revision",
			Names:     map[string]string{"#text": "text", "#revision": "revision", "#revisions": "revisions", "#updated_at": "updated_at"},
			Values:    map[string]any{":text": text, ":revision": next, ":revisions": revisions, ":updated_at": now, ":expected_revision": expected},
		},
		{Kind: store.WritePut, Table: s.table(), Item: value.Item{"pk": person, "sk": ledgerKey, "result": result, "payload_hash": hash, "actor": person, "created_at": now}, Condition: "attribute_not_exists(pk)"},
	})
	if err == nil {
		return result, nil
	}
	return s.afterFailure(ctx, err, person, "NoteMutation#", key, hash, sk, false)
}

func (s *Store) afterFailure(ctx context.Context, cause error, pk, prefix, key, hash, noteSK string, creating bool) (any, error) {
	if !errors.Is(cause, store.ErrTransactionCanceled) && !errors.Is(cause, store.ErrConditionFailed) {
		return nil, cause
	}
	if result, replayed, err := s.ledgerReplay(ctx, pk, prefix, key, hash, pk); err != nil || replayed {
		return result, err
	}
	latest, err := s.get(ctx, pk, noteSK)
	if err != nil {
		return nil, err
	}
	if latest == nil {
		if creating {
			return nil, cause
		}
		return nil, conflict("Note revision differs", 0, nil)
	}
	return nil, conflict("Note revision differs", number(latest, "revision", 0), publicNote(latest))
}

func checkContext(access *access.Context, domain any, action string) (string, error) {
	name, _ := domain.(string)
	if !slices.Contains(contextDomains, name) {
		return "", plain("context_domain is invalid")
	}
	if !access.Has(name + ":" + action) {
		return "", forbidden(name + ":" + action + " permission required")
	}
	return name, nil
}

func (s *Store) ListAttachments(ctx context.Context, athlete string, args map[string]any, granted *access.Context) (any, error) {
	domain, err := checkContext(granted, args["context_domain"], "read")
	if err != nil {
		return nil, err
	}
	rows, err := s.DB.Query(ctx, store.Query{
		Table:      s.table(),
		KeyCond:    "pk = :pk AND begins_with(sk, :prefix)",
		Values:     map[string]any{":pk": athlete, ":prefix": "SharedNote#"},
		Consistent: true,
	})
	if err != nil {
		return nil, err
	}
	attachments := []any{}
	for _, item := range rows {
		if strings.Contains(value.Str(item["sk"]), "#r") || value.Truthy(item["detached"]) || item["context_domain"] != domain {
			continue
		}
		if wanted := args["context_id"]; wanted != nil && item["context_id"] != wanted {
			continue
		}
		snapshot, err := s.get(ctx, athlete, "SharedNote#"+value.Str(item["attachment_id"])+"#r"+value.Str(item["attachment_revision"]))
		if err != nil {
			return nil, err
		}
		if snapshot != nil {
			attachments = append(attachments, publicAttachment(item, snapshot))
		}
	}
	return map[string]any{"attachments": attachments, "next_cursor": nil}, nil
}

func (s *Store) Share(ctx context.Context, athlete, person string, args map[string]any, granted *access.Context) (any, error) {
	noteID, ok := nonEmptyText(args["note_id"])
	if !ok {
		return nil, plain("note_id is required")
	}
	wanted, ok := asInt(args["wanted_revision"])
	if !ok || wanted < 1 {
		return nil, plain("wanted_revision must be a positive integer")
	}
	expected, ok := asInt(args["expected_attachment_revision"])
	if !ok || expected < 0 {
		return nil, plain("expected_attachment_revision must be a nonnegative integer")
	}
	key, ok := nonEmptyText(args["idempotency_key"])
	if !ok {
		return nil, plain("idempotency_key is required")
	}
	for _, forbiddenKey := range []string{"text", "author_person_pk", "author"} {
		if _, present := args[forbiddenKey]; present {
			return nil, plain("Share payload cannot include note text or author")
		}
	}
	domain, err := checkContext(granted, args["context_domain"], "write")
	if err != nil {
		return nil, err
	}
	note, err := s.get(ctx, person, "Note#"+noteID)
	if err != nil {
		return nil, err
	}
	if note == nil {
		return nil, apperr.New(404, "not_found", "Note not found")
	}
	if note["author_person_pk"] != person {
		return nil, forbidden("Only the author may share a note")
	}
	var revision map[string]any
	revisions, _ := note["revisions"].([]any)
	for _, entry := range revisions {
		if object, ok := entry.(map[string]any); ok && number(object, "revision", 0) == wanted {
			revision = object
			break
		}
	}
	if revision == nil {
		return nil, conflict("Requested note revision is unavailable", number(note, "revision", 0), publicNote(note))
	}
	contextID := args["context_id"]
	hash := payloadHash(map[string]any{"note_id": noteID, "wanted_revision": value.Int(wanted), "context_domain": domain, "context_id": contextID, "expected_attachment_revision": value.Int(expected)})
	if result, replayed, err := s.ledgerReplay(ctx, athlete, "SharedNoteMutation#", key, hash, person); err != nil || replayed {
		return wrap("attachment", result, replayed, err)
	}
	digest := sha256.Sum256([]byte(person + "\x00" + noteID + "\x00" + domain + "\x00" + value.Str(value.Or(contextID, ""))))
	attachmentID := "shared-" + hex.EncodeToString(digest[:])[:32]
	pointerSK := "SharedNote#" + attachmentID
	pointer, err := s.get(ctx, athlete, pointerSK)
	if err != nil {
		return nil, err
	}
	current := number(pointer, "attachment_revision", 0)
	if expected != current {
		var record any
		if pointer != nil {
			record = publicAttachment(pointer, nil)
		}
		return nil, conflict("Attachment revision differs", current, record)
	}
	next := current + 1
	now := s.Env.Stamp()
	snapshot := value.Item{
		"pk": athlete, "sk": "SharedNote#" + attachmentID + "#r" + value.Str(value.Int(next)), "attachment_id": attachmentID, "note_id": noteID,
		"attachment_revision": next, "source_revision": wanted, "text": orEmpty(revision, "text"), "author_person_pk": person,
		"context_domain": domain, "context_id": contextID, "attached_at": now,
	}
	nextPointer := value.Item{
		"pk": athlete, "sk": pointerSK, "attachment_id": attachmentID, "note_id": noteID, "attachment_revision": next, "source_revision": wanted,
		"author_person_pk": person, "context_domain": domain, "context_id": contextID, "attached_at": now, "detached": false,
	}
	writes := []store.Write{{Kind: store.WritePut, Table: s.table(), Item: snapshot, Condition: "attribute_not_exists(pk)"}}
	if pointer != nil {
		writes = append(writes, store.Write{
			Kind: store.WriteUpdate, Table: s.table(), Key: store.PKSK(athlete, pointerSK),
			Update:    "SET #revision = :revision, #source = :source, #author = :author, #note = :note, #domain = :domain, #context_id = :context_id, #attached_at = :attached_at, #detached = :detached",
			Condition: "#revision = :expected AND #author = :author AND #note = :note",
			Names:     map[string]string{"#revision": "attachment_revision", "#source": "source_revision", "#author": "author_person_pk", "#note": "note_id", "#domain": "context_domain", "#context_id": "context_id", "#attached_at": "attached_at", "#detached": "detached"},
			Values:    map[string]any{":revision": next, ":source": wanted, ":author": person, ":note": noteID, ":domain": domain, ":context_id": contextID, ":attached_at": now, ":detached": false, ":expected": expected},
		})
	} else {
		writes = append(writes, store.Write{Kind: store.WritePut, Table: s.table(), Item: nextPointer, Condition: "attribute_not_exists(pk)"})
	}
	result := publicAttachment(nextPointer, snapshot)
	writes = append(writes, store.Write{Kind: store.WritePut, Table: s.table(), Item: value.Item{"pk": athlete, "sk": "SharedNoteMutation#" + key, "result": result, "payload_hash": hash, "actor": person, "created_at": now}, Condition: "attribute_not_exists(pk)"})
	if err := s.DB.Transact(ctx, writes); err != nil {
		if !errors.Is(err, store.ErrTransactionCanceled) {
			return nil, err
		}
		if replayed, ok, lookup := s.ledgerReplay(ctx, athlete, "SharedNoteMutation#", key, hash, person); lookup != nil || ok {
			return wrap("attachment", replayed, ok, lookup)
		}
		latest, lookup := s.get(ctx, athlete, pointerSK)
		if lookup != nil {
			return nil, lookup
		}
		var record any
		if latest != nil {
			record = publicAttachment(latest, nil)
		}
		return nil, conflict("Attachment revision differs", number(latest, "attachment_revision", 0), record)
	}
	return map[string]any{"attachment": result}, nil
}

func wrap(key string, result any, ok bool, err error) (any, error) {
	if err != nil {
		return nil, err
	}
	return map[string]any{key: result}, nil
}

func (s *Store) Detach(ctx context.Context, athlete string, args map[string]any, granted *access.Context) (any, error) {
	if !granted.IsSelf || granted.OwnAthletePK != athlete {
		return nil, forbidden("Only the Athlete may detach an attachment")
	}
	attachmentID, ok := nonEmptyText(value.Or(args["attachment_id"], args["note_id"]))
	if !ok {
		return nil, plain("attachment_id is required")
	}
	expected, ok := asInt(args["expected_attachment_revision"])
	if !ok || expected < 1 {
		return nil, plain("expected_attachment_revision must be a positive integer")
	}
	key, ok := nonEmptyText(args["idempotency_key"])
	if !ok {
		return nil, plain("idempotency_key is required")
	}
	actor := granted.PersonPK
	if actor == "" {
		actor = athlete
	}
	hash := payloadHash(map[string]any{"attachment_id": attachmentID, "expected_attachment_revision": value.Int(expected)})
	if result, replayed, err := s.ledgerReplay(ctx, athlete, "SharedNoteMutation#", key, hash, actor); err != nil || replayed {
		return result, err
	}
	pointerSK := "SharedNote#" + attachmentID
	pointer, err := s.get(ctx, athlete, pointerSK)
	if err != nil {
		return nil, err
	}
	if pointer == nil {
		return nil, apperr.New(404, "not_found", "Attachment not found")
	}
	if number(pointer, "attachment_revision", 0) != expected {
		return nil, conflict("Attachment revision differs", number(pointer, "attachment_revision", 0), publicAttachment(pointer, nil))
	}
	revision := expected + 1
	result := map[string]any{"attachment_id": attachmentID, "detached": true, "revision": revision}
	err = s.DB.Transact(ctx, []store.Write{
		{
			Kind: store.WriteUpdate, Table: s.table(), Key: store.PKSK(athlete, pointerSK),
			Update:    "SET #detached = :detached, #revision = :revision",
			Condition: "#revision = :expected AND #detached = :attached",
			Names:     map[string]string{"#detached": "detached", "#revision": "attachment_revision"},
			Values:    map[string]any{":detached": true, ":revision": revision, ":expected": expected, ":attached": false},
		},
		{Kind: store.WritePut, Table: s.table(), Item: value.Item{"pk": athlete, "sk": "SharedNoteMutation#" + key, "result": result, "payload_hash": hash, "actor": actor, "created_at": s.Env.Stamp()}, Condition: "attribute_not_exists(pk)"},
	})
	if err != nil {
		if !errors.Is(err, store.ErrTransactionCanceled) {
			return nil, err
		}
		if replayed, ok, lookup := s.ledgerReplay(ctx, athlete, "SharedNoteMutation#", key, hash, actor); lookup != nil || ok {
			return replayed, lookup
		}
		latest, lookup := s.get(ctx, athlete, pointerSK)
		if lookup != nil {
			return nil, lookup
		}
		var record any
		if latest != nil {
			record = publicAttachment(latest, nil)
		}
		return nil, conflict("Attachment revision differs", number(latest, "attachment_revision", 0), record)
	}
	return result, nil
}
