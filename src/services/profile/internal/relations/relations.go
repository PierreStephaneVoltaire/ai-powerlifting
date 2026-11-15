package relations

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"slices"
	"sort"
	"strings"
	"time"

	"powerlifting/profile/internal/access"
	"powerlifting/profile/internal/apperr"
	"powerlifting/profile/internal/clock"
	"powerlifting/profile/internal/people"
	"powerlifting/profile/internal/store"
	"powerlifting/profile/internal/value"
)

var relationshipTypes = []string{"coach", "handler", "peer"}

type Service struct {
	DB     *store.DB
	People *people.Repo
	Access *access.Provider
	Env    clock.Env
}

type Caller struct {
	Person string
	Access *access.Context
}

func invalid(code string) error { return apperr.Validation(code) }

func sha(text string) string {
	sum := sha256.Sum256([]byte(text))
	return hex.EncodeToString(sum[:])
}

func textOf(v any) string {
	if !value.Truthy(v) {
		return ""
	}
	return value.Str(v)
}

func trimmed(v any) string { return people.Strip(textOf(v)) }

func safe(v any, maximum int) (string, error) {
	text := trimmed(v)
	if text == "" || len([]rune(text)) > maximum {
		return "", invalid("invalid_identifier")
	}
	return text, nil
}

func (s *Service) person(caller Caller) (string, error) {
	if caller.Person == "" {
		return "", invalid("authenticated_person_required")
	}
	return strings.TrimSpace(caller.Person), nil
}

func idempotencyKey(args map[string]any) (string, error) {
	key := trimmed(args["idempotency_key"])
	if key == "" || len([]rune(key)) > 200 {
		return "", invalid("idempotency_key_required")
	}
	return key, nil
}

func actionHash(relationshipID, action, actor string, payload map[string]any) string {
	if payload == nil {
		payload = map[string]any{}
	}
	return sha(value.Dump(map[string]any{"relationship_id": relationshipID, "action": action, "actor": actor, "payload": payload}))
}

func sortedStrings(raw any) []any {
	list, _ := raw.([]any)
	out := make([]string, 0, len(list))
	for _, entry := range list {
		out = append(out, value.Str(entry))
	}
	sort.Strings(out)
	result := make([]any, len(out))
	for i, entry := range out {
		result[i] = entry
	}
	return result
}

func approvalHash(relationshipID, actor string, args map[string]any, request value.Item) string {
	payload := map[string]any{
		"relationship_id":                 relationshipID,
		"actor":                           actor,
		"requester_person_pk":             request["requester_person_pk"],
		"recipient_person_pk":             request["recipient_person_pk"],
		"athlete_person_pk":               request["athlete_person_pk"],
		"athlete_mapped_pk":               request["athlete_mapped_pk"],
		"relationship_type":               request["relationship_type"],
		"scope":                           args["scope"],
		"permissions":                     sortedStrings(args["permissions"]),
		"tied_competition_ids":            sortedStrings(args["tied_competition_ids"]),
		"replace_current_relationship_id": textOf(args["replace_current_relationship_id"]),
	}
	return sha(relationshipID + ":approve:" + value.Dump(payload))
}

func requestPayloadHash(args map[string]any) string {
	fields := map[string]any{}
	for _, key := range []string{"athlete_mapped_pk", "recipient_person_pk", "relationship_type", "scope", "permissions", "tied_competition_ids", "note", "replace_current_relationship_id"} {
		fields[key] = args[key]
	}
	return sha(value.Dump(fields))
}

func parseDate(text string) (time.Time, error) {
	parsed, _, ok := clock.ParseISO(text)
	if !ok {
		return time.Time{}, errors.New("bad date")
	}
	return parsed, nil
}

func expiry(role string, ids []string, dates map[string]string) (string, error) {
	if role == "peer" {
		return "", nil
	}
	if len(ids) == 0 {
		return "", invalid("competition_ties_required")
	}
	for _, id := range ids {
		if _, ok := dates[id]; !ok {
			return "", invalid("competition_ties_required")
		}
	}
	var latest time.Time
	for i, id := range ids {
		parsed, err := parseDate(dates[id])
		if err != nil {
			return "", invalid("invalid_tied_competition_dates")
		}
		if i == 0 || parsed.After(latest) {
			latest = parsed
		}
	}
	end := latest.AddDate(0, 0, 7)
	day := time.Date(end.Year(), end.Month(), end.Day(), 23, 59, 59, 999999000, time.UTC)
	return day.Format("2006-01-02T15:04:05.000000") + "+00:00", nil
}

func Permissions(role string, requested any, scope string) ([]string, error) {
	list, isList := requested.([]any)
	var values []string
	if isList {
		for _, entry := range list {
			values = append(values, value.Str(entry))
		}
	} else {
		switch role {
		case "coach":
			values = access.CoachPermissions
		case "handler":
			values = access.HandlerPermissions
		}
	}
	set := map[string]bool{}
	for _, candidate := range values {
		if slices.Contains(access.CoachPermissions, candidate) {
			set[candidate] = true
		}
	}
	result := make([]string, 0, len(set))
	for candidate := range set {
		result = append(result, candidate)
	}
	sort.Strings(result)
	if role == "peer" && slices.ContainsFunc(result, func(p string) bool { return !strings.HasSuffix(p, ":read") }) {
		return nil, invalid("peer_grants_are_read_only")
	}
	if scope == "read" {
		result = slices.DeleteFunc(result, func(p string) bool { return !strings.HasSuffix(p, ":read") })
	}
	if len(result) == 0 {
		return nil, invalid("permissions_required")
	}
	return result, nil
}

func asAny(values []string) []any {
	out := make([]any, len(values))
	for i, v := range values {
		out[i] = v
	}
	return out
}

func (s *Service) requests() string { return s.DB.Tables.Requests }

func requestKey(id string) store.Key { return store.PKSK("Relationship#"+id, "Record") }

func pendingKey(athlete, requester, recipient, role string) store.Key {
	return store.PKSK("RelationshipPending#"+sha(athlete+":"+requester+":"+recipient+":"+role), "Record")
}

func idempotencyItemKey(person, key string) store.Key {
	return store.PKSK("RelationshipIdempotency#"+person, "Request#"+sha(key))
}

func (s *Service) get(ctx context.Context, key store.Key) (value.Item, error) {
	return s.DB.Get(ctx, s.requests(), key)
}

func (s *Service) notificationWrites(person, eventID, kind string, payload map[string]any) []store.Write {
	now := s.Env.Stamp()
	marker := value.Item{"pk": "Event#" + eventID, "sk": "Notification", "event_id": eventID, "created_at": now}
	item := value.Item{
		"pk": "Person#" + person, "sk": "Notification#" + now + "#" + eventID,
		"notification_id": eventID, "event_id": eventID, "kind": kind, "payload": payload, "read_at": nil,
		"created_at": now, "gsi1pk": "Event#" + eventID, "gsi1sk": "Notification",
	}
	table := s.DB.Tables.Notifications
	return []store.Write{
		{Kind: store.WritePut, Table: table, Item: marker, Condition: "attribute_not_exists(pk)"},
		{Kind: store.WritePut, Table: table, Item: item, Condition: "attribute_not_exists(pk)"},
	}
}

func (s *Service) storedCompetitionDates(ctx context.Context, athlete string, identifiers []string) (map[string]string, error) {
	dates := map[string]string{}
	if len(identifiers) == 0 {
		return dates, nil
	}
	rows, err := s.DB.Query(ctx, store.Query{
		Table:      s.DB.Tables.Competitions,
		KeyCond:    "pk = :pk AND begins_with(sk, :prefix)",
		Values:     map[string]any{":pk": athlete, ":prefix": "COMP#"},
		Consistent: true,
	})
	if err != nil {
		return nil, err
	}
	for _, row := range rows {
		date, ok := value.Or(value.Or(row["date"], row["competition_date"]), row["start_date"]).(string)
		if !ok {
			continue
		}
		candidates := []string{textOf(row["id"]), textOf(row["competition_id"]), textOf(row["master_id"]), textOf(row["sk"])}
		for _, candidate := range slices.Clone(candidates) {
			if strings.HasPrefix(candidate, "COMP#") {
				candidates = append(candidates, candidate[5:])
			}
		}
		for _, candidate := range candidates {
			if slices.Contains(identifiers, candidate) {
				dates[candidate] = date
			}
		}
	}
	return dates, nil
}

func (s *Service) recipientRecord(ctx context.Context, identifier string) (value.Item, error) {
	record, err := s.People.Get(ctx, identifier)
	if err != nil || record != nil {
		return record, err
	}
	return s.People.Record(ctx, identifier)
}

func (s *Service) slotIsActive(ctx context.Context, slot value.Item, athlete string) (bool, error) {
	sk := textOf(slot["grant_sk"])
	if sk == "" {
		return false, nil
	}
	grant, err := s.get(ctx, store.PKSK("Grant#"+athlete, sk))
	if err != nil || grant == nil {
		return false, err
	}
	dates, err := s.storedCompetitionDates(ctx, athlete, stringList(grant["tied_competition_ids"]))
	if err != nil {
		return false, err
	}
	grants := []access.Grant{access.GrantOf(grant), access.GrantOf(slot)}
	return slices.Contains(access.ActiveIndexes(grants, dates, s.Env.Now()), 0), nil
}

func stringList(raw any) []string {
	list, _ := raw.([]any)
	out := make([]string, 0, len(list))
	for _, entry := range list {
		out = append(out, value.Str(entry))
	}
	return out
}

func (s *Service) activeRelationshipIDs(ctx context.Context, athlete, role string) (map[string]bool, error) {
	rows, err := s.DB.Query(ctx, store.Query{
		Table:      s.requests(),
		KeyCond:    "pk = :pk",
		Values:     map[string]any{":pk": "Grant#" + athlete},
		Consistent: true,
	})
	if err != nil {
		return nil, err
	}
	var grants []access.Grant
	idSet := map[string]bool{}
	for _, row := range rows {
		if textOf(row["grant_type"]) != role || row["entity"] == "relationship_slot" {
			continue
		}
		grants = append(grants, access.GrantOf(row))
		for _, id := range stringList(row["tied_competition_ids"]) {
			idSet[id] = true
		}
	}
	ids := make([]string, 0, len(idSet))
	for id := range idSet {
		ids = append(ids, id)
	}
	sort.Strings(ids)
	dates, err := s.storedCompetitionDates(ctx, athlete, ids)
	if err != nil {
		return nil, err
	}
	result := map[string]bool{}
	for _, grant := range access.ActiveGrants(grants, dates, s.Env.Now()) {
		if grant.RelationshipID != "" {
			result[grant.RelationshipID] = true
		}
	}
	return result, nil
}

func (s *Service) athleteOf(args map[string]any, caller Caller) (string, error) {
	candidate := value.Or(args["athlete_mapped_pk"], value.Or(caller.Access.AthletePK, args["pk"]))
	return safe(candidate, 128)
}

func (s *Service) isAthleteOwner(ctx context.Context, actor, athlete string) (bool, error) {
	owner, err := s.People.Record(ctx, athlete)
	if err != nil {
		return false, err
	}
	return actor == textOf(owner["pk"]) || actor == textOf(owner["mapped_pk"]), nil
}

func (s *Service) requesterHasRole(ctx context.Context, actor, role string) (bool, error) {
	record, err := s.People.Record(ctx, actor)
	if err != nil {
		return false, err
	}
	roles, _ := record["roles"].([]any)
	return slices.Contains(stringList(roles), role), nil
}

func (s *Service) requestItem(ctx context.Context, args map[string]any, caller Caller, id, now string, stored map[string]string) (value.Item, error) {
	role := strings.ToLower(trimmed(value.Or(args["relationship_type"], args["grant_type"])))
	if !slices.Contains(relationshipTypes, role) {
		return nil, invalid("invalid_relationship_type")
	}
	athlete, err := s.athleteOf(args, caller)
	if err != nil {
		return nil, err
	}
	recipient, err := safe(args["recipient_person_pk"], 256)
	if err != nil {
		return nil, err
	}
	actor, err := s.person(caller)
	if err != nil {
		return nil, err
	}
	if recipient == actor {
		return nil, invalid("cannot_request_self")
	}
	incoming := value.Truthy(args["_incoming_invitation"])
	if incoming {
		owns, err := s.isAthleteOwner(ctx, recipient, athlete)
		if err != nil {
			return nil, err
		}
		if !owns {
			return nil, invalid("athlete_recipient_required")
		}
		has, err := s.requesterHasRole(ctx, actor, role)
		if err != nil {
			return nil, err
		}
		if !has {
			return nil, invalid("requester_role_required")
		}
	} else if !(caller.Access != nil && caller.Access.IsSelf && caller.Access.AthletePK == athlete) {
		return nil, invalid("athlete_owner_required")
	}
	rawIDs := value.Or(args["tied_competition_ids"], []any{})
	list, isList := rawIDs.([]any)
	if !isList {
		return nil, invalid("invalid_tied_competition_ids")
	}
	idSet := map[string]bool{}
	for _, entry := range list {
		id, err := safe(entry, 128)
		if err != nil {
			return nil, err
		}
		idSet[id] = true
	}
	ids := make([]string, 0, len(idSet))
	for id := range idSet {
		ids = append(ids, id)
	}
	sort.Strings(ids)
	if (role == "coach" || role == "handler") && !incoming && len(ids) == 0 {
		return nil, invalid("competition_ties_required")
	}
	expires := ""
	if len(ids) > 0 {
		if expires, err = expiry(role, ids, stored); err != nil {
			return nil, err
		}
	}
	scope := strings.ToLower(textOf(args["scope"]))
	if scope == "" {
		scope = "write"
	}
	if scope != "read" && scope != "write" {
		return nil, invalid("invalid_scope")
	}
	permissions := []string{}
	if !(incoming && !value.Truthy(args["permissions"])) {
		if permissions, err = Permissions(role, args["permissions"], scope); err != nil {
			return nil, err
		}
	}
	var owner value.Item
	if incoming {
		if owner, err = s.People.Record(ctx, athlete); err != nil {
			return nil, err
		}
	}
	ownerPerson := textOf(value.Or(args["_athlete_person_pk"], value.Or(owner["pk"], actor)))
	delegate, direction := recipient, "athlete_to_delegate"
	if incoming {
		delegate, direction = actor, "coach_to_athlete"
	}
	dates := map[string]any{}
	for key, date := range stored {
		if slices.Contains(ids, key) {
			dates[key] = date
		}
	}
	note := people.Truncate(trimmed(args["note"]), 280)
	return value.Item{
		"pk": requestKey(id)["pk"], "sk": "Record",
		"entity": "relationship_request", "relationship_id": id, "state": "pending",
		"athlete_mapped_pk": athlete, "athlete_person_pk": ownerPerson, "requester_person_pk": actor, "recipient_person_pk": recipient,
		"request_direction": direction, "relationship_type": role, "grant_type": role, "scope": scope,
		"permissions": asAny(permissions), "tied_competition_ids": asAny(ids), "tied_competition_dates": dates,
		"expires_at": expires, "note": note, "created_at": now, "updated_at": now,
		"inbox_pk": "Inbox#" + recipient, "inbox_sk": now + "#" + id,
		"sent_pk": "Sent#" + actor, "sent_sk": now + "#" + id,
		"roster_pk": "Roster#" + delegate, "roster_sk": role + "#" + athlete + "#" + id,
		"replace_current_relationship_id": textOf(args["replace_current_relationship_id"]),
	}, nil
}

func (s *Service) Request(ctx context.Context, args map[string]any, caller Caller) (any, error) {
	key, err := idempotencyKey(args)
	if err != nil {
		return nil, err
	}
	actor, err := s.person(caller)
	if err != nil {
		return nil, err
	}
	payloadHash := requestPayloadHash(args)
	idemKey := idempotencyItemKey(actor, key)
	previous, err := s.get(ctx, idemKey)
	if err != nil {
		return nil, err
	}
	if previous != nil && value.Truthy(previous["request_id"]) {
		if previous["payload_hash"] != payloadHash {
			return nil, invalid("idempotency_key_reused")
		}
		return s.requestOr(ctx, previous)
	}
	requestID := s.Env.ID()
	athlete, err := s.athleteOf(args, caller)
	if err != nil {
		return nil, err
	}
	rawIDs := value.Or(args["tied_competition_ids"], []any{})
	list, isList := rawIDs.([]any)
	if !isList {
		return nil, invalid("invalid_tied_competition_ids")
	}
	idSet := map[string]bool{}
	for _, entry := range list {
		id, err := safe(entry, 128)
		if err != nil {
			return nil, err
		}
		idSet[id] = true
	}
	ids := make([]string, 0, len(idSet))
	for id := range idSet {
		ids = append(ids, id)
	}
	sort.Strings(ids)
	role := strings.ToLower(trimmed(value.Or(args["relationship_type"], args["grant_type"])))
	owner, err := s.People.Record(ctx, athlete)
	if err != nil {
		return nil, err
	}
	var ownerIDs []string
	if owner != nil {
		ownerIDs = []string{textOf(owner["pk"]), textOf(owner["mapped_pk"])}
	}
	incoming := !slices.Contains(ownerIDs, actor)
	recipientIdentifier := trimmed(args["recipient_person_pk"])
	recipient, err := s.recipientRecord(ctx, recipientIdentifier)
	if err != nil {
		return nil, err
	}
	if incoming {
		has := false
		if role != "peer" {
			if has, err = s.requesterHasRole(ctx, actor, role); err != nil {
				return nil, err
			}
		}
		if !has {
			return nil, invalid("requester_role_required")
		}
		if recipient == nil || !slices.Contains(ownerIDs, textOf(recipient["pk"])) {
			return nil, invalid("athlete_recipient_required")
		}
	} else {
		roles, _ := recipient["roles"].([]any)
		if recipient == nil || (role != "peer" && !slices.Contains(stringList(roles), role)) {
			return nil, invalid("recipient_role_required")
		}
	}
	if owner == nil {
		return nil, apperr.Internal("athlete owner unavailable")
	}
	scoped := make(map[string]any, len(args)+3)
	for k, v := range args {
		scoped[k] = v
	}
	scoped["recipient_person_pk"] = textOf(value.Or(recipient["pk"], recipientIdentifier))
	scoped["_athlete_person_pk"] = textOf(value.Or(owner["pk"], actor))
	stored := map[string]string{}
	if incoming {
		scoped["_incoming_invitation"] = true
	} else if stored, err = s.storedCompetitionDates(ctx, athlete, ids); err != nil {
		return nil, err
	}
	pending := pendingKey(athlete, actor, value.Str(scoped["recipient_person_pk"]), role)
	pendingItem, err := s.get(ctx, pending)
	if err != nil {
		return nil, err
	}
	if pendingItem != nil && value.Truthy(pendingItem["request_id"]) {
		existing, err := s.get(ctx, requestKey(value.Str(pendingItem["request_id"])))
		if err != nil {
			return nil, err
		}
		if existing != nil && existing["state"] == "pending" {
			return existing, nil
		}
	}
	replacement := textOf(args["replace_current_relationship_id"])
	if (role == "coach" || role == "handler") && !incoming {
		slot, err := s.get(ctx, store.PKSK("Grant#"+athlete, "RelationshipSlot#"+role))
		if err != nil {
			return nil, err
		}
		if slot != nil {
			if slot["state"] == "active" {
				active, err := s.slotIsActive(ctx, slot, athlete)
				if err != nil {
					return nil, err
				}
				if active && replacement != textOf(slot["relationship_id"]) {
					return nil, invalid("current_relationship_confirmation_required")
				}
			}
		} else {
			activeIDs, err := s.activeRelationshipIDs(ctx, athlete, role)
			if err != nil {
				return nil, err
			}
			if len(activeIDs) > 0 && !activeIDs[replacement] {
				return nil, invalid("current_relationship_confirmation_required")
			}
		}
	}
	item, err := s.requestItem(ctx, scoped, caller, requestID, s.Env.Stamp(), stored)
	if err != nil {
		return nil, err
	}
	table := s.requests()
	idem := value.Item{"pk": idemKey["pk"], "sk": idemKey["sk"], "entity": "relationship_idempotency", "request_id": requestID, "payload_hash": payloadHash, "created_at": item["created_at"]}
	writes := []store.Write{
		{Kind: store.WritePut, Table: table, Item: item, Condition: "attribute_not_exists(pk)"},
		{Kind: store.WritePut, Table: table, Item: idem, Condition: "attribute_not_exists(pk)"},
		{Kind: store.WritePut, Table: table, Item: value.Item{"pk": pending["pk"], "sk": pending["sk"], "entity": "relationship_pending", "request_id": requestID, "created_at": item["created_at"]}, Condition: "attribute_not_exists(pk)"},
	}
	writes = append(writes, s.notificationWrites(value.Str(item["recipient_person_pk"]), "relationship:"+requestID+":requested", "relationship_requested", map[string]any{
		"relationship_id": requestID, "athlete_mapped_pk": item["athlete_mapped_pk"], "relationship_type": item["relationship_type"],
		"message": "A " + role + " relationship request is waiting for your decision.",
	})...)
	if err := s.DB.Transact(ctx, writes); err != nil {
		if again, lookup := s.get(ctx, idemKey); lookup == nil && again != nil && value.Truthy(again["request_id"]) {
			return s.requestOr(ctx, again)
		}
		if again, lookup := s.get(ctx, pending); lookup == nil && again != nil && value.Truthy(again["request_id"]) {
			return s.requestOr(ctx, again)
		}
		return nil, err
	}
	return item, nil
}

func (s *Service) requestOr(ctx context.Context, fallback value.Item) (any, error) {
	request, err := s.get(ctx, requestKey(value.Str(fallback["request_id"])))
	if err != nil {
		return nil, err
	}
	if request != nil {
		return request, nil
	}
	return fallback, nil
}

func merged(base value.Item, extra value.Item) value.Item {
	out := value.CopyItem(base)
	for key, v := range extra {
		out[key] = v
	}
	return out
}

func (s *Service) stateUpdate(ctx context.Context, request value.Item, state, actor, actionKey string) (value.Item, error) {
	participants := []string{textOf(request["athlete_person_pk"]), textOf(request["requester_person_pk"]), textOf(request["recipient_person_pk"])}
	if !slices.Contains(participants, actor) {
		return nil, invalid("relationship_request_actor_forbidden")
	}
	id := value.Str(request["relationship_id"])
	if request["state"] != "pending" {
		if request["state"] == state && request["last_action"] == state && textOf(request["last_action_key"]) == actionKey && request["last_action_hash"] == actionHash(id, state, actor, map[string]any{"action": state}) {
			return request, nil
		}
		return nil, invalid("relationship_request_already_decided")
	}
	requester := textOf(value.Or(request["requester_person_pk"], request["athlete_person_pk"]))
	owner := textOf(request["recipient_person_pk"])
	if state == "cancelled" {
		owner = requester
	}
	if actor != owner {
		return nil, invalid("relationship_request_actor_forbidden")
	}
	now := s.Env.Stamp()
	target := requester
	if actor == requester {
		target = textOf(request["recipient_person_pk"])
	}
	hash := actionHash(id, state, actor, map[string]any{"action": state})
	update := value.Item{"state": state, "responded_by": actor, "responded_at": now, "updated_at": now, "last_action": state, "last_action_key": actionKey, "last_action_hash": hash}
	pending := pendingKey(textOf(request["athlete_mapped_pk"]), requester, textOf(request["recipient_person_pk"]), textOf(request["relationship_type"]))
	table := s.requests()
	writes := []store.Write{
		{
			Kind: store.WriteUpdate, Table: table, Key: requestKey(id),
			Update:    "SET #state=:state, responded_by=:actor, responded_at=:at, updated_at=:at, last_action=:action, last_action_key=:action_key, last_action_hash=:action_hash",
			Condition: "#state=:pending", Names: map[string]string{"#state": "state"},
			Values: map[string]any{":state": state, ":pending": "pending", ":actor": actor, ":at": now, ":action": state, ":action_key": actionKey, ":action_hash": hash},
		},
		{Kind: store.WriteDelete, Table: table, Key: pending},
	}
	writes = append(writes, s.notificationWrites(target, "relationship:"+id+":"+state, "relationship_"+state, map[string]any{
		"relationship_id": id, "relationship_type": request["relationship_type"], "athlete_mapped_pk": request["athlete_mapped_pk"],
		"message": "Your " + textOf(request["relationship_type"]) + " relationship request was " + state + ".",
	})...)
	if err := s.DB.Transact(ctx, writes); err != nil {
		return nil, err
	}
	return merged(request, update), nil
}

func delegateOf(request value.Item) string {
	requester := textOf(value.Or(request["requester_person_pk"], request["athlete_person_pk"]))
	if requester != "" && requester != textOf(request["athlete_person_pk"]) {
		return requester
	}
	return textOf(value.Or(request["recipient_person_pk"], value.Or(request["grantee_person_pk"], request["grantee_mapped_pk"])))
}

func (s *Service) Respond(ctx context.Context, args map[string]any, caller Caller) (any, error) {
	if _, err := idempotencyKey(args); err != nil {
		return nil, err
	}
	actor, err := s.person(caller)
	if err != nil {
		return nil, err
	}
	id, err := safe(args["relationship_id"], 64)
	if err != nil {
		return nil, err
	}
	action := strings.ToLower(trimmed(args["action"]))
	request, err := s.get(ctx, requestKey(id))
	if err != nil {
		return nil, err
	}
	if request == nil {
		return nil, invalid("relationship_request_not_found")
	}
	actionKey := value.Str(args["idempotency_key"])
	if action == "cancel" || action == "reject" {
		state := "rejected"
		if action == "cancel" {
			state = "cancelled"
		}
		return s.stateUpdate(ctx, request, state, actor, actionKey)
	}
	if action != "approve" {
		return nil, invalid("invalid_relationship_action")
	}
	participants := []string{textOf(request["athlete_person_pk"]), textOf(request["requester_person_pk"]), textOf(request["recipient_person_pk"])}
	if !slices.Contains(participants, actor) {
		return nil, invalid("relationship_request_actor_forbidden")
	}
	requester := textOf(value.Or(request["requester_person_pk"], request["athlete_person_pk"]))
	incoming := requester != textOf(request["athlete_person_pk"])
	expectedActor := textOf(request["recipient_person_pk"])
	if incoming {
		expectedActor = textOf(request["athlete_person_pk"])
	}
	if actor != expectedActor {
		return nil, invalid("relationship_request_actor_forbidden")
	}
	if request["state"] != "pending" {
		replay := map[string]any{}
		for _, key := range []string{"scope", "permissions", "tied_competition_ids", "replace_current_relationship_id"} {
			if given, present := args[key]; incoming || present && given != nil {
				replay[key] = args[key]
			} else {
				replay[key] = request[key]
			}
		}
		if request["state"] == "approved" && request["last_action"] == "approve" && request["last_action_key"] == actionKey && request["last_action_hash"] == approvalHash(id, actor, replay, request) {
			return request, nil
		}
		return nil, invalid("relationship_request_already_decided")
	}
	role := value.Str(request["relationship_type"])
	var tied []string
	var scope string
	var permissions []string
	if incoming {
		given, isList := args["permissions"].([]any)
		if role == "peer" || !isList || len(given) == 0 {
			return nil, invalid("athlete_authorization_required")
		}
		ids, isIDs := args["tied_competition_ids"].([]any)
		if !isIDs || len(ids) == 0 {
			return nil, invalid("competition_ties_required")
		}
		idSet := map[string]bool{}
		for _, entry := range ids {
			clean, err := safe(entry, 128)
			if err != nil {
				return nil, err
			}
			idSet[clean] = true
		}
		for clean := range idSet {
			tied = append(tied, clean)
		}
		sort.Strings(tied)
		scope = strings.ToLower(textOf(args["scope"]))
		if scope != "read" && scope != "write" {
			return nil, invalid("athlete_authorization_required")
		}
		if permissions, err = Permissions(role, args["permissions"], scope); err != nil {
			return nil, err
		}
	} else {
		tied = stringList(request["tied_competition_ids"])
		scope = value.Str(request["scope"])
		permissions = stringList(request["permissions"])
	}
	athlete := value.Str(request["athlete_mapped_pk"])
	dates, err := s.storedCompetitionDates(ctx, athlete, tied)
	if err != nil {
		return nil, err
	}
	expires, err := expiry(role, tied, dates)
	if err != nil {
		return nil, err
	}
	table := s.requests()
	grantKey := store.PKSK("Grant#"+athlete, "Relationship#"+id)
	dateMap := map[string]any{}
	for key, date := range dates {
		dateMap[key] = date
	}
	grant := value.Item{
		"pk": grantKey["pk"], "sk": grantKey["sk"], "entity": "grant", "relationship_id": id, "state": "approved",
		"athlete_mapped_pk": athlete, "athlete_person_pk": request["athlete_person_pk"],
		"grantee_person_pk": delegateOf(request), "grantee_mapped_pk": delegateOf(request),
		"grant_type": role, "scope": scope, "permissions": asAny(permissions), "tied_competition_ids": asAny(tied),
		"tied_competition_dates": dateMap, "expires_at": expires, "created_by": request["athlete_person_pk"],
		"created_at": request["created_at"], "updated_at": s.Env.Stamp(), "revoked_at": nil, "revoked_by": nil,
	}
	slotKey := store.PKSK("Grant#"+athlete, "RelationshipSlot#"+role)
	slot, err := s.get(ctx, slotKey)
	if err != nil {
		return nil, err
	}
	replacement := textOf(request["replace_current_relationship_id"])
	if incoming {
		replacement = textOf(args["replace_current_relationship_id"])
	}
	coachOrHandler := role == "coach" || role == "handler"
	slotActive := false
	if coachOrHandler && slot != nil && slot["state"] == "active" {
		if slotActive, err = s.slotIsActive(ctx, slot, athlete); err != nil {
			return nil, err
		}
		if slotActive && replacement != textOf(slot["relationship_id"]) {
			return nil, invalid("current_relationship_confirmation_required")
		}
	}
	if coachOrHandler && slot == nil {
		activeIDs, err := s.activeRelationshipIDs(ctx, athlete, role)
		if err != nil {
			return nil, err
		}
		if len(activeIDs) > 0 && !activeIDs[replacement] {
			return nil, invalid("current_relationship_confirmation_required")
		}
	}
	var oldRequest value.Item
	if replacement != "" {
		if oldRequest, err = s.get(ctx, requestKey(replacement)); err != nil {
			return nil, err
		}
		if oldRequest == nil || oldRequest["state"] != "approved" || oldRequest["athlete_mapped_pk"] != request["athlete_mapped_pk"] || oldRequest["relationship_type"] != role {
			return nil, invalid("replacement_relationship_not_found")
		}
	}
	now := s.Env.Stamp()
	hash := approvalHash(id, actor, map[string]any{"scope": scope, "permissions": asAny(permissions), "tied_competition_ids": asAny(tied), "replace_current_relationship_id": replacement}, request)
	updated := merged(request, value.Item{
		"state": "approved", "responded_by": actor, "responded_at": now, "updated_at": now, "grant_sk": grantKey["sk"],
		"expires_at": expires, "tied_competition_ids": asAny(tied), "tied_competition_dates": dateMap, "scope": scope,
		"permissions": asAny(permissions), "replace_current_relationship_id": replacement, "last_action": "approve",
		"last_action_key": actionKey, "last_action_hash": hash, "approval_payload_hash": hash,
	})
	writes := []store.Write{
		{
			Kind: store.WriteUpdate, Table: table, Key: requestKey(id),
			Update:    "SET #state=:approved, responded_by=:actor, responded_at=:at, updated_at=:at, grant_sk=:grant_sk, expires_at=:expires, tied_competition_ids=:ids, tied_competition_dates=:dates, #scope=:scope, #permissions=:permissions, replace_current_relationship_id=:replacement, last_action=:action, last_action_key=:action_key, last_action_hash=:action_hash, approval_payload_hash=:action_hash",
			Condition: "#state=:pending", Names: map[string]string{"#state": "state", "#scope": "scope", "#permissions": "permissions"},
			Values: map[string]any{
				":approved": "approved", ":pending": "pending", ":actor": actor, ":at": now, ":grant_sk": grantKey["sk"], ":expires": expires,
				":ids": asAny(tied), ":dates": dateMap, ":scope": scope, ":permissions": asAny(permissions), ":replacement": replacement,
				":action": "approve", ":action_key": actionKey, ":action_hash": hash,
			},
		},
		{Kind: store.WritePut, Table: table, Item: grant, Condition: "attribute_not_exists(pk)"},
		{Kind: store.WriteDelete, Table: table, Key: pendingKey(athlete, requester, textOf(request["recipient_person_pk"]), role)},
	}
	if coachOrHandler {
		if slot != nil && slot["state"] == "active" && slotActive {
			oldKey := store.PKSK(slotKey["pk"], textOf(value.Or(slot["grant_sk"], "Relationship#"+textOf(slot["relationship_id"]))))
			writes = append(writes, store.Write{
				Kind: store.WriteUpdate, Table: table, Key: oldKey,
				Update:    "SET #state=:replaced, replaced_by=:replacement, revoked_at=:at, revoked_by=:actor, updated_at=:at",
				Condition: "relationship_id=:old AND #state=:approved", Names: map[string]string{"#state": "state"},
				Values: map[string]any{":old": slot["relationship_id"], ":approved": "approved", ":replaced": "replaced", ":replacement": id, ":at": now, ":actor": request["athlete_person_pk"]},
			})
			if oldRequest != nil {
				writes = append(writes, store.Write{
					Kind: store.WriteUpdate, Table: table, Key: requestKey(replacement),
					Update:    "SET #state=:replaced, replaced_by=:replacement, revoked_at=:at, revoked_by=:actor, updated_at=:at",
					Condition: "#state=:approved", Names: map[string]string{"#state": "state"},
					Values: map[string]any{":approved": "approved", ":replaced": "replaced", ":replacement": id, ":at": now, ":actor": request["athlete_person_pk"]},
				})
				writes = append(writes, s.notificationWrites(delegateOf(oldRequest), "relationship:"+replacement+":replaced", "relationship_replaced", map[string]any{
					"relationship_id": replacement, "replaced_by": id, "relationship_type": role, "athlete_mapped_pk": request["athlete_mapped_pk"],
					"message": "Your relationship was replaced by a new relationship.",
				})...)
			}
		}
		observedRelationship, observedState, observedRevision := "", "", 0
		if slot != nil {
			observedRelationship, observedState = textOf(slot["relationship_id"]), textOf(slot["state"])
			observedRevision = value.IntOf(value.Or(slot["revision"], 0), 0)
		}
		slotItem := value.Item{
			"pk": slotKey["pk"], "sk": slotKey["sk"], "entity": "relationship_slot", "relationship_id": id, "grant_sk": grantKey["sk"],
			"state": "active", "grant_type": role, "athlete_mapped_pk": athlete, "grantee_person_pk": delegateOf(request),
			"expires_at": expires, "revision": observedRevision + 1, "updated_at": now,
		}
		writes = append(writes, store.Write{
			Kind: store.WritePut, Table: table, Item: slotItem,
			Condition: "attribute_not_exists(pk) OR (relationship_id=:observed_relationship AND #state=:observed_state AND (revision=:observed_revision OR (attribute_not_exists(revision) AND :observed_revision=:zero)))",
			Names:     map[string]string{"#state": "state"},
			Values:    map[string]any{":observed_relationship": observedRelationship, ":observed_state": observedState, ":observed_revision": observedRevision, ":zero": 0},
		})
	}
	writes = append(writes, s.notificationWrites(delegateOf(request), "relationship:"+id+":approved", "relationship_approved", map[string]any{
		"relationship_id": id, "relationship_type": role, "athlete_mapped_pk": request["athlete_mapped_pk"],
		"message": "Your " + role + " relationship was approved.",
	})...)
	if err := s.DB.Transact(ctx, writes); err != nil {
		if errors.Is(err, store.ErrTransactionCanceled) || errors.Is(err, store.ErrConditionFailed) {
			return nil, apperr.Conflict("relationship_conflict", "Relationship changed; reload before retrying")
		}
		return nil, err
	}
	updated["grant"] = grant
	return updated, nil
}

func (s *Service) Revoke(ctx context.Context, args map[string]any, caller Caller) (any, error) {
	actionKey, err := idempotencyKey(args)
	if err != nil {
		return nil, err
	}
	actor, err := s.person(caller)
	if err != nil {
		return nil, err
	}
	id, err := safe(args["relationship_id"], 64)
	if err != nil {
		return nil, err
	}
	request, err := s.get(ctx, requestKey(id))
	if err != nil {
		return nil, err
	}
	if request == nil {
		return nil, invalid("active_relationship_not_found")
	}
	if actor != textOf(request["athlete_person_pk"]) && actor != textOf(request["recipient_person_pk"]) {
		return nil, invalid("relationship_request_actor_forbidden")
	}
	hash := actionHash(id, "revoke", actor, map[string]any{"action": "revoke"})
	if request["state"] == "revoked" {
		if request["last_action"] == "revoke" && request["last_action_key"] == actionKey && request["last_action_hash"] == hash {
			return request, nil
		}
		return nil, invalid("relationship_already_revoked")
	}
	if request["state"] != "approved" {
		return nil, invalid("active_relationship_not_found")
	}
	if actor != textOf(request["athlete_person_pk"]) {
		return nil, invalid("only_athlete_may_revoke")
	}
	now := s.Env.Stamp()
	athlete := value.Str(request["athlete_mapped_pk"])
	table := s.requests()
	grantKey := store.PKSK("Grant#"+athlete, textOf(value.Or(request["grant_sk"], "Relationship#"+id)))
	update := map[string]any{":revoked": "revoked", ":approved": "approved", ":actor": actor, ":at": now}
	requestValues := map[string]any{":revoked": "revoked", ":approved": "approved", ":actor": actor, ":at": now, ":action": "revoke", ":action_key": actionKey, ":action_hash": hash}
	requester := textOf(value.Or(request["requester_person_pk"], request["athlete_person_pk"]))
	writes := []store.Write{
		{Kind: store.WriteUpdate, Table: table, Key: grantKey, Update: "SET #state=:revoked, revoked_by=:actor, revoked_at=:at, updated_at=:at", Condition: "#state=:approved", Names: map[string]string{"#state": "state"}, Values: update},
		{Kind: store.WriteUpdate, Table: table, Key: requestKey(id), Update: "SET #state=:revoked, revoked_by=:actor, revoked_at=:at, updated_at=:at, last_action=:action, last_action_key=:action_key, last_action_hash=:action_hash", Condition: "#state=:approved", Names: map[string]string{"#state": "state"}, Values: requestValues},
		{Kind: store.WriteDelete, Table: table, Key: pendingKey(athlete, requester, textOf(request["recipient_person_pk"]), textOf(request["relationship_type"]))},
	}
	role := textOf(request["relationship_type"])
	if role == "coach" || role == "handler" {
		writes = append(writes, store.Write{
			Kind: store.WriteUpdate, Table: table, Key: store.PKSK("Grant#"+athlete, "RelationshipSlot#"+role),
			Update: "SET #state=:revoked, updated_at=:at", Condition: "relationship_id=:relationship", Names: map[string]string{"#state": "state"},
			Values: map[string]any{":revoked": "revoked", ":at": now, ":relationship": id},
		})
	}
	writes = append(writes, s.notificationWrites(delegateOf(request), "relationship:"+id+":revoked", "relationship_revoked", map[string]any{
		"relationship_id": id, "relationship_type": request["relationship_type"], "athlete_mapped_pk": request["athlete_mapped_pk"],
		"message": "Your " + role + " relationship was revoked.",
	})...)
	if err := s.DB.Transact(ctx, writes); err != nil {
		return nil, err
	}
	return merged(request, value.Item{"state": "revoked", "revoked_by": actor, "revoked_at": now, "updated_at": now, "last_action": "revoke", "last_action_key": actionKey, "last_action_hash": hash}), nil
}
