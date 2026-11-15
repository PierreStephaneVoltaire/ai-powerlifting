package relations

import (
	"context"
	"slices"
	"sort"
	"strings"

	"powerlifting/profile/internal/store"
	"powerlifting/profile/internal/value"
)

var publicRequestFields = []string{
	"relationship_id", "state", "active", "athlete_mapped_pk", "athlete_person_pk",
	"requester_person_pk", "recipient_person_pk", "request_direction", "relationship_type", "scope",
	"permissions", "tied_competition_ids", "expires_at", "note", "created_at", "updated_at",
	"responded_by", "responded_at", "replaced_by", "revoked_by", "revoked_at", "replace_current_relationship_id",
	"athlete_display_name",
}

func (s *Service) indexed(ctx context.Context, index, keyName, keyValue string) ([]value.Item, error) {
	rows, err := s.DB.Query(ctx, store.Query{
		Table:      s.requests(),
		Index:      index,
		KeyCond:    keyName + " = :key",
		Values:     map[string]any{":key": keyValue},
		Descending: true,
	})
	if err != nil {
		return nil, err
	}
	out := rows[:0]
	for _, row := range rows {
		if row["entity"] == "relationship_request" {
			out = append(out, row)
		}
	}
	return out, nil
}

func (s *Service) current(ctx context.Context, actor string, indexed []value.Item) ([]any, error) {
	result := []any{}
	for _, entry := range indexed {
		item, err := s.get(ctx, requestKey(value.Str(entry["relationship_id"])))
		if err != nil {
			return nil, err
		}
		if item == nil || !slices.Contains([]string{textOf(item["athlete_person_pk"]), textOf(item["requester_person_pk"]), textOf(item["recipient_person_pk"])}, actor) {
			continue
		}
		item = value.CopyItem(item)
		item["active"] = false
		athlete := value.Str(item["athlete_mapped_pk"])
		if item["state"] == "approved" {
			tied := stringList(item["tied_competition_ids"])
			dates, err := s.storedCompetitionDates(ctx, athlete, tied)
			if err != nil {
				return nil, err
			}
			active, err := s.activeRelationshipIDs(ctx, athlete, value.Str(item["relationship_type"]))
			if err != nil {
				return nil, err
			}
			item["active"] = active[value.Str(item["relationship_id"])]
			if expires, err := expiry(value.Str(item["relationship_type"]), tied, dates); err == nil {
				item["expires_at"] = expires
			} else {
				item["expires_at"] = ""
			}
		}
		granted, err := s.Access.Context(ctx, actor, athlete)
		if err != nil {
			return nil, err
		}
		if granted.Has("profile:read") {
			owner, err := s.People.Record(ctx, athlete)
			if err != nil {
				return nil, err
			}
			if owner != nil {
				item["athlete_display_name"] = value.Or(owner["display_name"], value.Or(owner["nickname"], athlete))
			}
		}
		public := map[string]any{}
		for _, field := range publicRequestFields {
			if v, ok := item[field]; ok {
				public[field] = v
			}
		}
		result = append(result, public)
	}
	return result, nil
}

func (s *Service) List(ctx context.Context, caller Caller) (map[string]any, error) {
	actor, err := s.person(caller)
	if err != nil {
		return nil, err
	}
	sentRows, err := s.indexed(ctx, s.DB.Tables.SentIndex, "sent_pk", "Sent#"+actor)
	if err != nil {
		return nil, err
	}
	sent, err := s.current(ctx, actor, sentRows)
	if err != nil {
		return nil, err
	}
	receivedRows, err := s.indexed(ctx, s.DB.Tables.InboxIndex, "inbox_pk", "Inbox#"+actor)
	if err != nil {
		return nil, err
	}
	received, err := s.current(ctx, actor, receivedRows)
	if err != nil {
		return nil, err
	}
	return map[string]any{"sent": sent, "received": received, "history": append(slices.Clone(sent), received...)}, nil
}

func (s *Service) History(ctx context.Context, caller Caller) (map[string]any, error) {
	listed, err := s.List(ctx, caller)
	if err != nil {
		return nil, err
	}
	history := slices.Clone(listed["history"].([]any))
	sort.SliceStable(history, func(i, j int) bool {
		return value.Str(value.Or(history[i].(map[string]any)["created_at"], "")) > value.Str(value.Or(history[j].(map[string]any)["created_at"], ""))
	})
	return map[string]any{"items": history}, nil
}

func (s *Service) Favorite(ctx context.Context, args map[string]any, caller Caller) (any, error) {
	person, err := s.person(caller)
	if err != nil {
		return nil, err
	}
	athlete, err := safe(args["athlete_mapped_pk"], 128)
	if err != nil {
		return nil, err
	}
	action := strings.ToLower(textOf(args["action"]))
	if action == "" {
		action = "add"
	}
	key := store.PKSK("Favorite#"+person, "Athlete#"+athlete)
	switch action {
	case "remove":
		if err := s.DB.Delete(ctx, s.requests(), key); err != nil {
			return nil, err
		}
		return map[string]any{"removed": true, "athlete_mapped_pk": athlete}, nil
	case "add":
		item := value.Item{"pk": key["pk"], "sk": key["sk"], "entity": "favorite", "person_pk": person, "athlete_mapped_pk": athlete, "created_at": s.Env.Stamp()}
		if err := s.DB.Put(ctx, s.requests(), item, ""); err != nil {
			return nil, err
		}
		return item, nil
	}
	return nil, invalid("invalid_favorite_action")
}

func (s *Service) Favorites(ctx context.Context, caller Caller) (any, error) {
	person, err := s.person(caller)
	if err != nil {
		return nil, err
	}
	rows, err := s.DB.Query(ctx, store.Query{Table: s.requests(), KeyCond: "pk = :pk", Values: map[string]any{":pk": "Favorite#" + person}})
	if err != nil {
		return nil, err
	}
	items := []any{}
	for _, row := range rows {
		if row["entity"] == "favorite" {
			items = append(items, row)
		}
	}
	return map[string]any{"favorites": items}, nil
}

func (s *Service) Notifications(ctx context.Context, caller Caller) (any, error) {
	person, err := s.person(caller)
	if err != nil {
		return nil, err
	}
	rows, err := s.DB.Query(ctx, store.Query{
		Table:      s.DB.Tables.Notifications,
		KeyCond:    "pk = :pk",
		Values:     map[string]any{":pk": "Person#" + person},
		Descending: true,
	})
	if err != nil {
		return nil, err
	}
	items := []any{}
	for _, row := range rows {
		if value.Truthy(row["notification_id"]) {
			items = append(items, row)
		}
	}
	return map[string]any{"notifications": items, "total": len(items)}, nil
}

func (s *Service) MarkRead(ctx context.Context, args map[string]any, caller Caller) (any, error) {
	person, err := s.person(caller)
	if err != nil {
		return nil, err
	}
	raw := value.Or(args["notification_ids"], []any{})
	ids, ok := raw.([]any)
	if !ok || len(ids) > 100 {
		return nil, invalid("invalid_notification_ids")
	}
	now := s.Env.Stamp()
	changed := 0
	for _, entry := range ids {
		id, err := safe(entry, 512)
		if err != nil {
			return nil, err
		}
		rows, err := s.DB.Query(ctx, store.Query{
			Table:   s.DB.Tables.Notifications,
			KeyCond: "pk = :pk",
			Filter:  "notification_id = :id",
			Values:  map[string]any{":pk": "Person#" + person, ":id": id},
		})
		if err != nil {
			return nil, err
		}
		for _, row := range rows {
			err := s.DB.Update(ctx, s.DB.Tables.Notifications, store.PKSK(value.Str(row["pk"]), value.Str(row["sk"])), store.Update{
				Expression: "SET read_at=:at",
				Values:     map[string]any{":at": now},
			})
			if err != nil {
				return nil, err
			}
			changed++
		}
	}
	return map[string]any{"marked": changed}, nil
}
