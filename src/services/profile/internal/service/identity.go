package service

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"regexp"
	"slices"
	"sort"
	"strings"

	"powerlifting/profile/internal/apperr"
	"powerlifting/profile/internal/people"
	"powerlifting/profile/internal/store"
	"powerlifting/profile/internal/value"
)

const (
	discordCDN    = "https://cdn.discordapp.com/avatars/"
	discordIssuer = "https://discord.com"
)

var discordSubject = regexp.MustCompile(`^\d{1,32}$`)

func identityKey(issuer, sub string) string {
	sum := sha256.Sum256([]byte(issuer + "\x00" + sub))
	return "Identity#" + hex.EncodeToString(sum[:])
}

func (s *Service) registerIdentity() {
	s.handlers["identity_resolve"] = s.identityResolve
}

func (s *Service) discordAvatar(ctx context.Context, args map[string]any) string {
	if given, ok := args["avatar_url"].(string); ok && strings.HasPrefix(given, discordCDN) {
		return given
	}
	var subjects []string
	if list, ok := args["discord_subjects"].([]any); ok {
		for _, entry := range list {
			if value.Truthy(entry) {
				subjects = append(subjects, value.Str(entry))
			}
		}
	}
	if args["provider"] == "discord" && value.Truthy(args["sub"]) {
		subjects = append([]string{value.Str(args["sub"])}, subjects...)
	}
	if len(subjects) == 0 || s.deps.Discord == nil {
		return ""
	}
	return s.deps.Discord.Avatar(ctx, subjects[0])
}

func uploaded(person value.Item) bool {
	return person["avatar_source"] == "upload" || strings.HasPrefix(value.Str(value.Or(person["avatar_url"], "")), "/api/")
}

func (s *Service) syncAvatar(ctx context.Context, person value.Item, avatar string) (value.Item, error) {
	if avatar == "" || uploaded(person) || person["avatar_url"] == avatar {
		return person, nil
	}
	err := s.people.Update(ctx, value.Str(person["pk"]), store.Update{
		Expression: "SET avatar_url = :avatar, avatar_source = :source",
		Condition:  "attribute_exists(pk)",
		Values:     map[string]any{":avatar": avatar, ":source": "discord"},
	})
	if err != nil {
		return nil, err
	}
	updated := value.CopyItem(person)
	updated["avatar_url"], updated["avatar_source"] = avatar, "discord"
	return updated, nil
}

func (s *Service) identitySettings(item value.Item) map[string]any {
	settings := s.people.Settings(item).Map()
	for _, field := range []string{"identity_issuer", "identity_provider", "identity_sub"} {
		if value.Truthy(item[field]) {
			settings[field] = value.Str(item[field])
		}
	}
	return settings
}

func (s *Service) linkedPerson(ctx context.Context, issuer, sub string, discordSubjects []string) (value.Item, error) {
	rows, err := s.people.All(ctx)
	if err != nil {
		return nil, err
	}
	var matches []value.Item
	for _, item := range rows {
		exact := item["identity_issuer"] == issuer && value.Str(item["identity_sub"]) == sub
		verified := value.Truthy(item["discord_id"]) && slices.Contains(discordSubjects, value.Str(item["discord_id"]))
		if exact || verified {
			matches = append(matches, item)
		}
	}
	if len(matches) > 1 {
		return nil, apperr.Validation("Provider subject is linked to multiple Persons; operator repair required")
	}
	if len(matches) == 0 {
		return nil, nil
	}
	return matches[0], nil
}

func stringList(raw any) []string {
	list, _ := raw.([]any)
	out := make([]string, 0, len(list))
	for _, entry := range list {
		out = append(out, value.Str(entry))
	}
	return out
}

func (s *Service) identityResolve(ctx context.Context, req *Request) (any, error) {
	args := req.Args
	provider, _ := args["provider"].(string)
	issuer := people.Strip(value.Str(args["issuer"]))
	sub := people.Strip(value.Str(args["sub"]))
	if (provider != "discord" && provider != "authentik") || !value.Truthy(args["issuer"]) || !value.Truthy(args["sub"]) {
		return nil, apperr.Validation("Verified issuer, provider, and subject are required")
	}
	discordSubjects := stringList(args["discord_subjects"])
	resolved, err := s.resolveIdentity(ctx, args, provider, issuer, sub, discordSubjects)
	if err != nil {
		return nil, err
	}
	pk := value.Str(resolved["settings"].(map[string]any)["pk"])
	if allowed, present := args["ai_access"].(bool); present && provider == "authentik" {
		person, err := s.people.Get(ctx, pk)
		if err != nil {
			return nil, err
		}
		expires := value.IntOf(args["ai_access_expires"], 0)
		if person["ai_access"] != allowed || value.IntOf(person["ai_access_expires"], 0) != expires {
			if err := s.people.Update(ctx, pk, store.Update{Expression: "SET ai_access = :access, ai_access_expires = :expires", Condition: "attribute_exists(pk)", Values: map[string]any{":access": allowed, ":expires": expires}}); err != nil {
				return nil, err
			}
		}
	}
	if err := s.linkDiscordSubjects(ctx, pk, discordSubjects); err != nil {
		return nil, err
	}
	return resolved, nil
}

func (s *Service) resolveIdentity(ctx context.Context, args map[string]any, provider, issuer, sub string, discordSubjects []string) (map[string]any, error) {
	users := s.deps.DB.Tables.User
	key := identityKey(issuer, sub)
	avatar := s.discordAvatar(ctx, args)
	pointer, err := s.deps.DB.Get(ctx, users, store.PK(key))
	if err != nil {
		return nil, err
	}
	if pointer != nil {
		person, err := s.people.Get(ctx, value.Str(pointer["mapped_pk"]))
		if err != nil {
			return nil, err
		}
		if person != nil {
			synced, err := s.syncAvatar(ctx, person, avatar)
			if err != nil {
				return nil, err
			}
			return map[string]any{"settings": s.identitySettings(synced), "created": false}, nil
		}
	}
	linked, err := s.linkedPerson(ctx, issuer, sub, discordSubjects)
	if err != nil {
		return nil, err
	}
	pointerItem := func(mapped string) value.Item {
		return value.Item{"pk": key, "mapped_pk": mapped, "identity_issuer": issuer, "identity_provider": provider, "identity_sub": sub}
	}
	if linked != nil {
		person := value.Str(linked["pk"])
		err := s.deps.DB.Transact(ctx, []store.Write{
			{
				Kind: store.WriteUpdate, Table: users, Key: store.PK(person),
				Update:    "SET identity_issuer = if_not_exists(identity_issuer, :issuer), identity_provider = if_not_exists(identity_provider, :provider), identity_sub = if_not_exists(identity_sub, :sub), #roles = if_not_exists(#roles, :roles)",
				Names:     map[string]string{"#roles": "roles"},
				Values:    map[string]any{":issuer": issuer, ":provider": provider, ":sub": sub, ":roles": []any{"athlete"}},
				Condition: "attribute_exists(pk)",
			},
			{Kind: store.WritePut, Table: users, Item: pointerItem(person), Condition: "attribute_not_exists(pk)"},
		})
		if err != nil {
			if !errors.Is(err, store.ErrTransactionCanceled) {
				return nil, err
			}
			winner, err := s.deps.DB.Get(ctx, users, store.PK(key))
			if err != nil {
				return nil, err
			}
			if winner == nil || value.Str(winner["mapped_pk"]) != person {
				return nil, apperr.Validation("Provider subject linkage changed; retry authentication")
			}
		}
		fresh, err := s.people.Get(ctx, person)
		if err != nil {
			return nil, err
		}
		synced, err := s.syncAvatar(ctx, fresh, avatar)
		if err != nil {
			return nil, err
		}
		return map[string]any{"settings": s.identitySettings(synced), "created": false}, nil
	}

	now := s.deps.Env.Stamp()
	displayName := people.Truncate(people.Strip(value.Str(value.Or(args["display_name"], ""))), 80)
	username := "person_" + s.deps.Env.ID()[:24]
	given, _ := args["avatar_url"].(string)
	var avatarURL, avatarSource any
	if avatar != "" {
		avatarURL, avatarSource = avatar, "discord"
	} else if _, isText := args["avatar_url"].(string); isText {
		avatarURL = given
	}
	discordID, discordName := "", ""
	if provider == "discord" {
		discordID, discordName = sub, displayName
	}
	person := value.Item{
		"pk": username, "mapped_pk": username, "username": username,
		"identity_issuer": issuer, "identity_provider": provider, "identity_sub": sub,
		"discord_id": discordID, "discord_username": discordName,
		"avatar_url": avatarURL, "avatar_source": avatarSource,
		"nickname": username, "profile_visibility": "private",
		"display_name":                    value.Or(displayName, username),
		"bio":                             "",
		"public_training_summary_enabled": false,
		"ranking_country":                 nil, "ranking_region": nil,
		"age_class": "open", "sex": nil, "bodyweight_kg": nil, "training_maxes": nil,
		"federations": []any{}, "roles": []any{}, "active_role": "athlete",
		"athlete_basics_complete": false, "profile_complete": false,
		"created_at": now, "updated_at": now,
	}
	err = s.deps.DB.Transact(ctx, []store.Write{
		{Kind: store.WritePut, Table: users, Item: person, Condition: "attribute_not_exists(pk)"},
		{Kind: store.WritePut, Table: users, Item: pointerItem(username), Condition: "attribute_not_exists(pk)"},
	})
	if err == nil {
		return map[string]any{"settings": s.identitySettings(person), "created": true}, nil
	}
	if !errors.Is(err, store.ErrTransactionCanceled) {
		return nil, err
	}
	raced, err := s.deps.DB.Get(ctx, users, store.PK(key))
	if err != nil || raced == nil {
		return nil, apperr.Internal("identity pointer missing after conflict")
	}
	winner, err := s.people.Get(ctx, value.Str(raced["mapped_pk"]))
	if err != nil || winner == nil {
		return nil, apperr.Internal("identity person missing after conflict")
	}
	return map[string]any{"settings": s.identitySettings(winner), "created": false}, nil
}

func (s *Service) linkedSubjects(ctx context.Context, person string, subjects []string) (map[string]bool, error) {
	linked := map[string]bool{}
	for _, subject := range subjects {
		pointer, err := s.deps.DB.Get(ctx, s.deps.DB.Tables.User, store.PK(identityKey(discordIssuer, subject)))
		if err != nil {
			return nil, err
		}
		if pointer != nil && pointer["mapped_pk"] == person && pointer["identity_issuer"] == discordIssuer && pointer["identity_provider"] == "discord" && pointer["identity_sub"] == subject {
			linked[subject] = true
		}
	}
	return linked, nil
}

func (s *Service) linkDiscordSubjects(ctx context.Context, person string, subjects []string) error {
	unique := slices.Clone(subjects)
	sort.Strings(unique)
	unique = slices.Compact(unique)
	if len(unique) == 0 {
		return nil
	}
	if person == "" || len(unique) > 99 {
		return apperr.Validation("Invalid Discord aliases")
	}
	for _, subject := range unique {
		if !discordSubject.MatchString(subject) {
			return apperr.Validation("Invalid Discord subject")
		}
	}
	already, err := s.linkedSubjects(ctx, person, unique)
	if err != nil {
		return err
	}
	var pending []string
	for _, subject := range unique {
		if !already[subject] {
			pending = append(pending, subject)
		}
	}
	if len(pending) == 0 {
		return nil
	}
	users := s.deps.DB.Tables.User
	writes := []store.Write{{Kind: store.WriteCheck, Table: users, Key: store.PK(person), Condition: "attribute_exists(pk)"}}
	for _, subject := range pending {
		writes = append(writes, store.Write{
			Kind:  store.WritePut,
			Table: users,
			Item: value.Item{
				"pk": identityKey(discordIssuer, subject), "mapped_pk": person, "identity_issuer": discordIssuer,
				"identity_provider": "discord", "identity_sub": subject,
			},
			Condition: "attribute_not_exists(pk) OR (mapped_pk = :person AND identity_issuer = :issuer AND identity_provider = :provider AND identity_sub = :subject)",
			Values:    map[string]any{":person": person, ":issuer": discordIssuer, ":provider": "discord", ":subject": subject},
		})
	}
	err = s.deps.DB.Transact(ctx, writes)
	if err == nil {
		return nil
	}
	if !errors.Is(err, store.ErrTransactionCanceled) {
		return err
	}
	linked, lookupErr := s.linkedSubjects(ctx, person, pending)
	if lookupErr != nil {
		return lookupErr
	}
	if len(linked) != len(pending) {
		return err
	}
	return nil
}
