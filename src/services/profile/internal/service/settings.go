package service

import (
	"context"
	"encoding/base64"
	"errors"
	"net/url"
	"regexp"
	"strings"

	"powerlifting/profile/internal/apperr"
	"powerlifting/profile/internal/people"
	"powerlifting/profile/internal/store"
	"powerlifting/profile/internal/value"
)

var mimeExtension = map[string]string{"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/gif": "gif"}

var unsafeSegment = regexp.MustCompile(`[^A-Za-z0-9_-]`)

func (s *Service) registerSettings() {
	s.handlers["settings_get"] = s.settingsGet
	s.handlers["settings_create"] = s.settingsCreate
	s.handlers["settings_update_nickname"] = s.updateNickname
	s.handlers["settings_update_profile"] = s.updateProfile
	s.handlers["settings_update_age_class"] = s.updateAgeClass
	s.handlers["settings_update_ranking_location"] = s.updateRankingLocation
	s.handlers["settings_update_role"] = s.updateRole
	s.handlers["settings_update_onboarding_profile"] = s.updateOnboardingProfile
	s.handlers["settings_update_athlete_basics"] = s.updateAthleteBasics
	s.handlers["settings_update_avatar"] = s.updateAvatar
	s.handlers["onboarding_status"] = s.onboardingStatus
	s.handlers["settings_publication_get"] = s.publication
	s.handlers["settings_publication_update"] = s.publication
	s.handlers["master_copy_seed_user"] = s.masterCopy
}

func (s *Service) existing(ctx context.Context, req *Request) (value.Item, error) {
	item, err := s.people.Get(ctx, req.PK())
	if err != nil {
		return nil, err
	}
	if item == nil {
		return nil, apperr.Validation("Settings not found")
	}
	return item, nil
}

func (s *Service) settingsGet(ctx context.Context, req *Request) (any, error) {
	item, err := s.people.Get(ctx, req.PK())
	if err != nil {
		return nil, err
	}
	if item == nil {
		if mapped := text(req.Args, "mapped_pk"); mapped != "" {
			item, err = s.people.Get(ctx, mapped)
			if err != nil {
				return nil, err
			}
		}
	}
	if item == nil {
		return nil, apperr.Validation("Settings not found")
	}
	return s.people.Settings(item).Map(), nil
}

func (s *Service) mutate(ctx context.Context, shape string, existing value.Item, update store.Update) (any, error) {
	if update.Condition == "" {
		update.Condition = "attribute_exists(pk)"
	}
	if err := s.people.Update(ctx, value.Str(existing["pk"]), update); err != nil {
		if errors.Is(err, store.ErrConditionFailed) {
			return nil, apperr.Internal("settings changed concurrently")
		}
		return nil, err
	}
	updated, err := s.people.Get(ctx, value.Str(existing["pk"]))
	if err != nil {
		return nil, err
	}
	if updated == nil {
		updated = existing
	}
	return s.people.Settings(updated).Shape(shape), nil
}

func (s *Service) updateNickname(ctx context.Context, req *Request) (any, error) {
	nickname := text(req.Args, "nickname")
	if !people.NicknameValid(nickname) {
		return nil, apperr.Validation("Invalid nickname: must be 2-32 chars, lowercase alphanumeric, hyphens, underscores only")
	}
	existing, err := s.existing(ctx, req)
	if err != nil {
		return nil, err
	}
	return s.mutate(ctx, people.ShapeBasic, existing, store.Update{
		Expression: "SET #nick = :nick, updated_at = :now",
		Names:      map[string]string{"#nick": "nickname"},
		Values:     map[string]any{":nick": nickname, ":now": s.deps.Env.Stamp()},
	})
}

func (s *Service) updateProfile(ctx context.Context, req *Request) (any, error) {
	visibility := req.Args["profile_visibility"]
	if visibility != nil && visibility != "private" && visibility != "public" {
		return nil, apperr.Validation("profile_visibility must be private or public")
	}
	existing, err := s.existing(ctx, req)
	if err != nil {
		return nil, err
	}
	current := s.people.Settings(existing)
	next := current.ProfileVisibility
	if visibility != nil {
		next = value.Str(visibility)
	}
	display := current.DisplayName
	if given, present := req.Args["display_name"]; present && given != nil {
		trimmed := ""
		if text, ok := given.(string); ok {
			trimmed = people.Truncate(people.Strip(text), 80)
		}
		display = trimmed
		if display == "" {
			display = value.Str(value.Or(current.DiscordUsername, current.Nickname))
		}
	}
	bio := current.Bio
	if given, present := req.Args["bio"]; present && given != nil {
		bio = ""
		if text, ok := given.(string); ok {
			bio = people.Truncate(people.Strip(text), 280)
		}
	}
	summary := current.PublicSummary
	if given, present := req.Args["public_training_summary_enabled"]; present && given != nil {
		summary = value.Truthy(given)
	}
	return s.mutate(ctx, people.ShapeProfile, existing, store.Update{
		Expression: "SET profile_visibility = :visibility, display_name = :display, bio = :bio, public_training_summary_enabled = :summary, updated_at = :now",
		Values:     map[string]any{":visibility": next, ":display": display, ":bio": bio, ":summary": summary, ":now": s.deps.Env.Stamp()},
	})
}

func (s *Service) updateAgeClass(ctx context.Context, req *Request) (any, error) {
	given := req.Args["age_class"]
	if given != nil {
		if _, ok := given.(string); !ok {
			return nil, apperr.Validation("age_class must be a string or null")
		}
	}
	existing, err := s.existing(ctx, req)
	if err != nil {
		return nil, err
	}
	age := "open"
	if text, ok := given.(string); ok && containsString(people.AgeClasses, text) {
		age = text
	}
	return s.mutate(ctx, people.ShapeBasic, existing, store.Update{
		Expression: "SET age_class = :age, updated_at = :now",
		Values:     map[string]any{":age": age, ":now": s.deps.Env.Stamp()},
	})
}

func (s *Service) updateRankingLocation(ctx context.Context, req *Request) (any, error) {
	for _, field := range []string{"ranking_country", "ranking_region"} {
		if given := req.Args[field]; given != nil {
			if _, ok := given.(string); !ok {
				return nil, apperr.Validation(field + " must be a string or null")
			}
		}
	}
	existing, err := s.existing(ctx, req)
	if err != nil {
		return nil, err
	}
	trimmed := func(field string) any {
		if text, ok := req.Args[field].(string); ok {
			if stripped := people.Strip(text); stripped != "" {
				return stripped
			}
		}
		return nil
	}
	return s.mutate(ctx, people.ShapeBasic, existing, store.Update{
		Expression: "SET ranking_country = :country, ranking_region = :region, updated_at = :now",
		Values:     map[string]any{":country": trimmed("ranking_country"), ":region": trimmed("ranking_region"), ":now": s.deps.Env.Stamp()},
	})
}

func (s *Service) updateRole(ctx context.Context, req *Request) (any, error) {
	roles := people.Roles(req.Args["roles"])
	if len(roles) == 0 {
		return nil, apperr.Validation("At least one role is required")
	}
	active := req.Args["active_role"]
	if active != nil && !containsString(roles, value.Str(active)) {
		return nil, apperr.Validation("active_role must be one of the assigned roles")
	}
	activeRole := roles[0]
	if active != nil {
		activeRole = value.Str(active)
	}
	existing, err := s.existing(ctx, req)
	if err != nil {
		return nil, err
	}
	return s.mutate(ctx, people.ShapeBasic, existing, store.Update{
		Expression: "SET #roles = :roles, active_role = :active, updated_at = :now",
		Names:      map[string]string{"#roles": "roles"},
		Values:     map[string]any{":roles": anyStrings(roles), ":active": activeRole, ":now": s.deps.Env.Stamp()},
	})
}

func anyStrings(values []string) []any {
	out := make([]any, len(values))
	for i, v := range values {
		out[i] = v
	}
	return out
}

func (s *Service) updateOnboardingProfile(ctx context.Context, req *Request) (any, error) {
	input := object(req.Args, "input")
	if len(input) == 0 {
		input = req.Args
	}
	displayName, ok := input["display_name"].(string)
	if !ok || people.Strip(displayName) == "" {
		return nil, apperr.Validation("display_name is required")
	}
	display := people.Truncate(people.Strip(displayName), 80)
	if display == "" {
		return nil, apperr.Validation("display_name cannot be empty")
	}
	bio := ""
	if given := input["bio"]; given != nil {
		text, ok := given.(string)
		if !ok {
			return nil, apperr.Validation("bio must be a string")
		}
		bio = people.Truncate(people.Strip(text), 280)
	}
	visibility := "private"
	if given := input["profile_visibility"]; given != nil {
		if given != "private" && given != "public" {
			return nil, apperr.Validation("profile_visibility must be 'private' or 'public'")
		}
		visibility = value.Str(given)
	}
	summary := value.Truthy(input["public_training_summary_enabled"])
	var federations []any
	if raw := input["federations"]; raw != nil {
		list, ok := raw.([]any)
		if !ok {
			return nil, apperr.Validation("federations must be an array of strings")
		}
		federations = []any{}
		seen := map[string]bool{}
		for _, item := range list {
			if text, ok := item.(string); ok {
				if trimmed := people.Strip(text); trimmed != "" && !seen[trimmed] {
					seen[trimmed] = true
					federations = append(federations, trimmed)
				}
			}
			if len(federations) >= 20 {
				break
			}
		}
	}
	existing, err := s.existing(ctx, req)
	if err != nil {
		return nil, err
	}
	expression := "SET display_name = :display, bio = :bio, profile_visibility = :visibility, public_training_summary_enabled = :summary, profile_complete = :complete, updated_at = :now"
	values := map[string]any{":display": display, ":bio": bio, ":visibility": visibility, ":summary": summary, ":complete": true, ":now": s.deps.Env.Stamp()}
	if federations != nil {
		expression += ", federations = :federations"
		values[":federations"] = federations
	}
	return s.mutate(ctx, people.ShapeBasic, existing, store.Update{Expression: expression, Values: values})
}

func publicationDomains(item value.Item) []any {
	publication, _ := item["publication"].(map[string]any)
	domains, _ := publication["domains"].([]any)
	out := []any{}
	for _, domain := range domains {
		out = append(out, domain)
	}
	return out
}

func (s *Service) publication(ctx context.Context, req *Request) (any, error) {
	owner, err := s.people.Get(ctx, req.Access.SettingsPK)
	if err != nil {
		return nil, err
	}
	if owner == nil {
		return nil, apperr.New(404, "not_found", "Profile not found")
	}
	if req.Name == "settings_publication_get" {
		return map[string]any{"domains": publicationDomains(owner)}, nil
	}
	roles, _ := owner["roles"].([]any)
	if !containsString(stringList(roles), "athlete") {
		return nil, apperr.Forbidden("Only Athletes publish training domains")
	}
	chosen := map[string]bool{}
	for _, domain := range stringList(req.Args["domains"]) {
		chosen[domain] = true
	}
	domains := []string{}
	for domain := range chosen {
		domains = append(domains, domain)
	}
	sortStrings(domains)
	result := map[string]any{"domains": anyStrings(domains), "updated_at": s.deps.Env.Stamp()}
	if err := s.people.Update(ctx, req.Access.SettingsPK, store.Update{
		Expression: "SET publication = :publication",
		Values:     map[string]any{":publication": result},
	}); err != nil {
		return nil, err
	}
	return map[string]any{"domains": anyStrings(domains)}, nil
}

func (s *Service) onboardingStatus(ctx context.Context, req *Request) (any, error) {
	item, err := s.people.Get(ctx, req.PK())
	if err != nil {
		return nil, err
	}
	if item == nil {
		if mapped := text(req.Args, "mapped_pk"); mapped != "" {
			item, err = s.people.Get(ctx, mapped)
			if err != nil {
				return nil, err
			}
		}
	}
	if item == nil {
		return nil, apperr.Validation("Settings not found")
	}
	settings := s.people.Settings(item)
	status := people.DeriveOnboarding(settings.Map())
	result := status.Map()
	if !status.HasAthleteBasics {
		athlete := settings.MappedPK
		if athlete == "" {
			athlete = settings.PK
		}
		prefill, err := s.existingBasics(ctx, athlete)
		if err != nil {
			return nil, err
		}
		result["prefill"] = prefill
	}
	return result, nil
}

func (s *Service) existingBasics(ctx context.Context, athlete string) (map[string]any, error) {
	prefill := map[string]any{}
	if athlete == "" {
		return prefill, nil
	}
	health := s.deps.DB.Tables.Health
	pointer, err := s.deps.DB.Get(ctx, health, store.PKSK(athlete, "program#current"))
	if err != nil || pointer == nil || !value.Truthy(pointer["ref_sk"]) {
		return prefill, err
	}
	program, err := s.deps.DB.Get(ctx, health, store.PKSK(athlete, value.Str(pointer["ref_sk"])))
	if err != nil {
		return nil, err
	}
	meta, _ := program["meta"].(map[string]any)
	maxes, _ := value.Or(meta["manual_maxes"], program["current_maxes"]).(map[string]any)
	training := map[string]any{}
	for _, lift := range people.Lifts {
		if kg, ok := people.Positive(maxes[lift]); ok {
			training[lift+"_kg"] = people.FloatValue(kg)
		}
	}
	prefill["training_maxes"] = training
	if bodyweight, ok := people.Positive(meta["current_body_weight_kg"]); ok {
		prefill["bodyweight_kg"] = people.FloatValue(bodyweight)
	}
	return prefill, nil
}

func (s *Service) settingsCreate(ctx context.Context, req *Request) (any, error) {
	args := req.Args
	provider, _ := args["identity_provider"].(string)
	sub, _ := args["identity_sub"].(string)
	username := people.SanitizeUsername(value.Str(value.Or(args["discord_username"], "")), s.deps.Env.Now())
	if provider != "" && sub != "" {
		rows, err := s.deps.DB.Scan(ctx, store.Scan{
			Table:  s.deps.DB.Tables.User,
			Filter: "identity_provider = :provider AND identity_sub = :sub",
			Values: map[string]any{":provider": provider, ":sub": sub},
		})
		if err != nil {
			return nil, err
		}
		if len(rows) > 0 {
			return map[string]any{"settings": s.people.Settings(rows[0]).Map(), "created": false}, nil
		}
		taken, err := s.people.Get(ctx, username)
		if err != nil {
			return nil, err
		}
		if taken != nil {
			digest := identityKey("", sub)
			username = people.SanitizeUsername(username+"_"+strings.TrimPrefix(digest, "Identity#")[:8], s.deps.Env.Now())
		}
	}
	now := s.deps.Env.Stamp()
	discordName := value.Str(value.Or(args["discord_username"], ""))
	item := value.Item{"pk": username}
	if provider != "" && sub != "" {
		item["identity_provider"], item["identity_sub"] = provider, sub
	}
	avatar, _ := args["avatar_url"].(string)
	var avatarValue any
	if _, ok := args["avatar_url"].(string); ok {
		avatarValue = avatar
	}
	for key, v := range map[string]any{
		"username": username, "discord_id": value.Str(value.Or(args["discord_id"], "")), "discord_username": discordName,
		"avatar_url": avatarValue, "nickname": username, "profile_visibility": "private", "display_name": discordName, "bio": "",
		"public_training_summary_enabled": false, "ranking_country": nil, "ranking_region": nil, "age_class": "open", "sex": nil,
		"bodyweight_kg": nil, "training_maxes": nil, "federations": []any{}, "roles": []any{}, "active_role": "athlete",
		"athlete_basics_complete": false, "profile_complete": false, "created_at": now, "updated_at": now,
	} {
		item[key] = v
	}
	created := true
	if err := s.deps.DB.Put(ctx, s.deps.DB.Tables.User, item, "attribute_not_exists(pk)"); err != nil {
		if !errors.Is(err, store.ErrConditionFailed) {
			return nil, err
		}
		created = false
		if raced, getErr := s.people.Get(ctx, username); getErr != nil {
			return nil, getErr
		} else if raced != nil {
			return map[string]any{"settings": s.people.Settings(raced).Map(), "created": false}, nil
		}
	}
	return map[string]any{"settings": s.people.Settings(item).Map(), "created": created}, nil
}

func (s *Service) masterCopy(context.Context, *Request) (any, error) {
	return nil, apperr.New(501, "not_served", "master_copy_seed_user is not served: its master_copy implementation does not exist in this repository")
}

func (s *Service) updateAvatar(ctx context.Context, req *Request) (any, error) {
	existing, err := s.existing(ctx, req)
	if err != nil {
		return nil, err
	}
	mimetype := text(req.Args, "mimetype")
	if mimetype == "" {
		mimetype = "image/jpeg"
	}
	if _, known := mimeExtension[mimetype]; !known {
		return nil, apperr.Validation("Invalid file type")
	}
	encoded := text(req.Args, "file_b64")
	var body []byte
	if encoded != "" {
		if strings.ContainsAny(encoded, "\r\n") {
			return nil, apperr.Validation("Invalid base64 image")
		}
		if body, err = base64.StdEncoding.DecodeString(encoded); err != nil {
			return nil, apperr.Validation("Invalid base64 image")
		}
	}
	if len(body) == 0 {
		return nil, apperr.Validation("No profile picture provided")
	}
	if len(body) > 8*1024*1024 {
		return nil, apperr.Validation("Profile picture is too large")
	}
	settings := s.people.Settings(existing)
	filename := text(req.Args, "filename")
	if filename == "" {
		filename = "avatar.jpg"
	}
	extension := mimeExtension[mimetype]
	owner := value.Str(value.Or(settings.MappedPK, value.Or(req.Args["mapped_pk"], settings.PK)))
	owner = people.Truncate(unsafeSegment.ReplaceAllString(owner, "_"), 128)
	if owner == "" {
		owner = "user"
	}
	key := "profiles/" + owner + "/avatars/" + s.deps.Env.UUID() + "." + extension
	if err := s.deps.Avatars.Put(ctx, key, mimetype, body, map[string]string{"profile_avatar": "true", "username": settings.Username, "mapped_pk": owner}); err != nil {
		return nil, apperr.Upstream(err.Error())
	}
	result, err := s.mutate(ctx, people.ShapeBasic, existing, store.Update{
		Expression: "SET avatar_url = :avatar, avatar_source = :source, updated_at = :now",
		Values:     map[string]any{":avatar": key, ":source": "upload", ":now": s.deps.Env.Stamp()},
	})
	if err != nil {
		return nil, err
	}
	if previous := previousAvatarKey(existing["avatar_url"]); previous != "" && previous != key && strings.HasPrefix(previous, "profiles/") {
		_ = s.deps.Avatars.Delete(ctx, previous)
	}
	return result, nil
}

func previousAvatarKey(raw any) string {
	text, ok := raw.(string)
	if !ok || text == "" {
		return ""
	}
	if strings.HasPrefix(text, "http://") || strings.HasPrefix(text, "https://") {
		parsed, err := url.Parse(text)
		if err != nil {
			return ""
		}
		return strings.TrimLeft(parsed.Path, "/")
	}
	if strings.HasPrefix(text, "profiles/") {
		return text
	}
	return ""
}
