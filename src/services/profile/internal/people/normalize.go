package people

import (
	"encoding/json"
	"regexp"
	"slices"
	"strconv"
	"strings"
	"time"
	"unicode"

	"golang.org/x/text/cases"
	"golang.org/x/text/unicode/norm"

	"powerlifting/profile/internal/value"
)

const (
	MaxTags        = 20
	MaxTagLength   = 50
	maxDisplayName = 80
	maxBio         = 280
)

var (
	SexValues   = []string{"male", "female"}
	RoleValues  = []string{"athlete", "coach", "handler"}
	AgeClasses  = []string{"open", "subjunior", "junior", "master1", "master2", "master3", "master4"}
	Lifts       = []string{"squat", "bench", "deadlift"}
	nicknameRe  = regexp.MustCompile(`^[a-z0-9_-]{2,32}$`)
	unsafeNick  = regexp.MustCompile(`[^a-z0-9_-]`)
	folder      = cases.Fold()
	pythonSpace = func(r rune) bool { return unicode.IsSpace(r) || (r >= 0x1c && r <= 0x1f) }
)

func Number(v any) (float64, bool) {
	var text string
	switch typed := v.(type) {
	case value.Decimal:
		text = string(typed)
	case json.Number:
		text = string(typed)
	case float64:
		return typed, true
	case int:
		return float64(typed), true
	default:
		return 0, false
	}
	parsed, err := strconv.ParseFloat(text, 64)
	if err != nil {
		return 0, false
	}
	return parsed, true
}

func Positive(v any) (float64, bool) {
	number, ok := Number(v)
	if !ok || number <= 0 {
		return 0, false
	}
	return number, true
}

func FloatValue(f float64) json.Number { return json.Number(value.Float(f)) }

func truncate(text string, limit int) string {
	runes := []rune(text)
	if len(runes) > limit {
		return string(runes[:limit])
	}
	return text
}

func strip(text string) string { return strings.TrimFunc(text, pythonSpace) }

func Strip(text string) string { return strip(text) }

func Truncate(text string, limit int) string { return truncate(text, limit) }

func text(v any) string { return value.Str(v) }

func orText(candidates ...any) string {
	for _, candidate := range candidates {
		if value.Truthy(candidate) {
			return text(candidate)
		}
	}
	return ""
}

func SanitizeUsername(username string, now time.Time) string {
	sanitized := truncate(unsafeNick.ReplaceAllString(strings.ToLower(username), "_"), 32)
	if nicknameRe.MatchString(sanitized) {
		return sanitized
	}
	return "user_" + strconv.FormatInt(now.Unix(), 10)
}

func NicknameValid(nickname string) bool { return nicknameRe.MatchString(nickname) }

func Role(v any) string {
	if s, ok := v.(string); ok && slices.Contains(RoleValues, s) {
		return s
	}
	return ""
}

func Roles(raw any) []string {
	list, _ := raw.([]any)
	roles := []string{}
	for _, item := range list {
		if role := Role(item); role != "" && !slices.Contains(roles, role) {
			roles = append(roles, role)
		}
	}
	return roles
}

func Federations(raw any) []string {
	list, _ := raw.([]any)
	out := []string{}
	for _, item := range list {
		if s, ok := item.(string); ok {
			if trimmed := strip(s); trimmed != "" && !slices.Contains(out, trimmed) {
				out = append(out, trimmed)
			}
		}
	}
	return out
}

func TrainingMaxes(raw any) map[string]any {
	maxes, ok := raw.(map[string]any)
	if !ok {
		return nil
	}
	out := map[string]any{}
	for _, lift := range Lifts {
		kg, ok := Positive(maxes[lift+"_kg"])
		if !ok {
			return nil
		}
		out[lift+"_kg"] = FloatValue(kg)
	}
	return out
}

func NormalizeTag(raw any) (string, bool) {
	s, ok := raw.(string)
	if !ok {
		return "", false
	}
	collapsed := collapseSpace(norm.NFKC.String(s))
	length := len([]rune(collapsed))
	if length == 0 || length > MaxTagLength {
		return "", false
	}
	return collapsed, true
}

func collapseSpace(s string) string {
	var out strings.Builder
	pending := false
	for _, r := range s {
		if pythonSpace(r) {
			pending = true
			continue
		}
		if pending && out.Len() > 0 {
			out.WriteByte(' ')
		}
		pending = false
		out.WriteRune(r)
	}
	return out.String()
}

func TagKey(tag string) string { return folder.String(tag) }

type Tag struct {
	Name       string
	Approved   bool
	ProposedBy string
}

func NormalizeTags(raw any) []Tag {
	list, ok := raw.([]any)
	if !ok {
		return []Tag{}
	}
	seen := map[string]bool{}
	out := []Tag{}
	for _, item := range list {
		var tag Tag
		switch typed := item.(type) {
		case map[string]any:
			name, ok := NormalizeTag(text(orNone(typed["tag"])))
			if !ok {
				continue
			}
			tag = Tag{Name: name, Approved: value.Truthy(typed["approved"]), ProposedBy: orText(typed["proposed_by"])}
		case string:
			name, ok := NormalizeTag(typed)
			if !ok {
				continue
			}
			tag = Tag{Name: name, Approved: true}
		default:
			continue
		}
		key := TagKey(tag.Name)
		if seen[key] {
			continue
		}
		seen[key] = true
		out = append(out, tag)
	}
	if len(out) > MaxTags {
		out = out[:MaxTags]
	}
	return out
}

func orNone(v any) any {
	if value.Truthy(v) {
		return v
	}
	return ""
}

type Settings struct {
	PK                    string
	IdentityProvider      string
	IdentitySub           string
	IdentityIssuer        string
	Username              string
	DiscordID             string
	DiscordUsername       string
	AvatarURL             any
	Nickname              string
	ProfileVisibility     string
	DisplayName           string
	Bio                   string
	PublicSummary         bool
	RankingCountry        any
	RankingRegion         any
	AgeClass              string
	Tags                  []Tag
	Sex                   any
	BodyweightKG          any
	TrainingMaxes         any
	MaxesDate             any
	MaxesEstimated        map[string]any
	Federations           []string
	Roles                 []string
	ActiveRole            string
	AthleteBasicsComplete bool
	ProfileComplete       bool
	CreatedAt             string
	UpdatedAt             string
	MappedPK              string
}

func strOrNil(v any) any {
	if s, ok := v.(string); ok {
		return s
	}
	return nil
}

func trimmedOrNil(v any) any {
	if s, ok := v.(string); ok {
		if trimmed := strip(s); trimmed != "" {
			return trimmed
		}
	}
	return nil
}

func Normalize(raw map[string]any, now time.Time, stamp func(time.Time) string) Settings {
	discordUsername := orText(raw["discord_username"], raw["username"])
	username := SanitizeUsername(orText(raw["username"], discordUsername, raw["nickname"], "user"), now)
	nickname := orText(raw["nickname"], username)
	roles := Roles(raw["roles"])
	activeRole := Role(raw["active_role"])
	if activeRole == "" {
		activeRole = "athlete"
		if len(roles) > 0 {
			activeRole = roles[0]
		}
	}
	displayName := truncate(strip(orText(raw["display_name"])), maxDisplayName)
	if displayName == "" {
		displayName = orText(discordUsername, nickname)
	}
	settings := Settings{
		PK:                    orText(raw["pk"], username),
		Username:              username,
		DiscordID:             orText(raw["discord_id"]),
		DiscordUsername:       discordUsername,
		AvatarURL:             strOrNil(raw["avatar_url"]),
		Nickname:              nickname,
		ProfileVisibility:     "private",
		DisplayName:           displayName,
		Bio:                   truncate(strip(orText(raw["bio"])), maxBio),
		PublicSummary:         raw["public_training_summary_enabled"] == true,
		RankingCountry:        trimmedOrNil(raw["ranking_country"]),
		RankingRegion:         trimmedOrNil(raw["ranking_region"]),
		AgeClass:              "open",
		Tags:                  NormalizeTags(raw["tags"]),
		MaxesDate:             raw["maxes_date"],
		MaxesEstimated:        map[string]any{},
		Federations:           Federations(raw["federations"]),
		Roles:                 roles,
		ActiveRole:            activeRole,
		AthleteBasicsComplete: value.Truthy(raw["athlete_basics_complete"]),
		ProfileComplete:       value.Truthy(raw["profile_complete"]),
		CreatedAt:             orStamp(raw["created_at"], now, stamp),
		UpdatedAt:             orStamp(raw["updated_at"], now, stamp),
	}
	if raw["profile_visibility"] == "public" {
		settings.ProfileVisibility = "public"
	}
	if age, ok := raw["age_class"].(string); ok && slices.Contains(AgeClasses, age) {
		settings.AgeClass = age
	}
	if sex, ok := raw["sex"].(string); ok && slices.Contains(SexValues, sex) {
		settings.Sex = sex
	}
	if bodyweight, ok := Positive(raw["bodyweight_kg"]); ok {
		settings.BodyweightKG = FloatValue(bodyweight)
	}
	if maxes := TrainingMaxes(raw["training_maxes"]); maxes != nil {
		settings.TrainingMaxes = maxes
	}
	estimated, _ := raw["training_maxes_estimated"].(map[string]any)
	for _, lift := range Lifts {
		settings.MaxesEstimated[lift] = estimated[lift] == true
	}
	if provider, ok := raw["identity_provider"].(string); ok && (provider == "discord" || provider == "authentik") && value.Truthy(raw["identity_sub"]) {
		settings.IdentityProvider = provider
		settings.IdentitySub = text(raw["identity_sub"])
	}
	if value.Truthy(raw["mapped_pk"]) {
		settings.MappedPK = text(raw["mapped_pk"])
	}
	return settings
}

func orStamp(v any, now time.Time, stamp func(time.Time) string) string {
	if value.Truthy(v) {
		return text(v)
	}
	return stamp(now)
}

func (s Settings) Map() map[string]any {
	tags := make([]any, len(s.Tags))
	for i, tag := range s.Tags {
		tags[i] = map[string]any{"tag": tag.Name, "approved": tag.Approved, "proposed_by": tag.ProposedBy}
	}
	out := map[string]any{
		"pk":                              s.PK,
		"username":                        s.Username,
		"discord_id":                      s.DiscordID,
		"discord_username":                s.DiscordUsername,
		"avatar_url":                      s.AvatarURL,
		"nickname":                        s.Nickname,
		"profile_visibility":              s.ProfileVisibility,
		"display_name":                    s.DisplayName,
		"bio":                             s.Bio,
		"public_training_summary_enabled": s.PublicSummary,
		"ranking_country":                 s.RankingCountry,
		"ranking_region":                  s.RankingRegion,
		"age_class":                       s.AgeClass,
		"tags":                            tags,
		"sex":                             s.Sex,
		"bodyweight_kg":                   s.BodyweightKG,
		"training_maxes":                  s.TrainingMaxes,
		"maxes_date":                      s.MaxesDate,
		"training_maxes_estimated":        s.MaxesEstimated,
		"federations":                     anyList(s.Federations),
		"roles":                           anyList(s.Roles),
		"active_role":                     s.ActiveRole,
		"athlete_basics_complete":         s.AthleteBasicsComplete,
		"profile_complete":                s.ProfileComplete,
		"created_at":                      s.CreatedAt,
		"updated_at":                      s.UpdatedAt,
	}
	if s.IdentityProvider != "" {
		out["identity_provider"] = s.IdentityProvider
		out["identity_sub"] = s.IdentitySub
	}
	if s.IdentityIssuer != "" {
		out["identity_issuer"] = s.IdentityIssuer
	}
	if s.MappedPK != "" {
		out["mapped_pk"] = s.MappedPK
	}
	return out
}

const (
	ShapeFull    = "full"
	ShapeProfile = "profile"
	ShapeBasic   = "basic"
)

func (s Settings) Shape(shape string) map[string]any {
	out := s.Map()
	switch shape {
	case ShapeProfile, ShapeBasic:
		for _, key := range []string{"maxes_date", "training_maxes_estimated", "identity_provider", "identity_sub", "identity_issuer"} {
			delete(out, key)
		}
		if shape == ShapeBasic {
			delete(out, "tags")
		}
	}
	return out
}

func anyList(values []string) []any {
	out := make([]any, len(values))
	for i, v := range values {
		out[i] = v
	}
	return out
}

type OnboardingState struct {
	Roles                 []string
	ActiveRole            string
	AthleteBasicsComplete bool
	ProfileComplete       bool
}

type Onboarding struct {
	IsOnboarded      bool
	NextStep         string
	State            OnboardingState
	HasAthleteBasics bool
}

func DeriveOnboarding(raw map[string]any) Onboarding {
	roles := Roles(raw["roles"])
	active := Role(raw["active_role"])
	if active == "" {
		active = "athlete"
		if len(roles) > 0 {
			active = roles[0]
		}
	}
	state := OnboardingState{Roles: roles, ActiveRole: active, AthleteBasicsComplete: value.Truthy(raw["athlete_basics_complete"]), ProfileComplete: value.Truthy(raw["profile_complete"])}
	_, hasBodyweight := Positive(raw["bodyweight_kg"])
	sex, _ := raw["sex"].(string)
	basics := hasBodyweight && TrainingMaxes(raw["training_maxes"]) != nil && slices.Contains(SexValues, sex)
	next := "done"
	switch {
	case len(roles) == 0:
		next = "role"
	case !state.ProfileComplete:
		next = "profile"
	case slices.Contains(roles, "athlete") && !basics:
		next = "athlete_basics"
	}
	return Onboarding{IsOnboarded: next == "done", NextStep: next, State: state, HasAthleteBasics: basics}
}

func (o Onboarding) Map() map[string]any {
	return map[string]any{
		"is_onboarded":       o.IsOnboarded,
		"next_step":          o.NextStep,
		"has_athlete_basics": o.HasAthleteBasics,
		"state": map[string]any{
			"roles":                   anyList(o.State.Roles),
			"active_role":             o.State.ActiveRole,
			"athlete_basics_complete": o.State.AthleteBasicsComplete,
			"profile_complete":        o.State.ProfileComplete,
		},
	}
}
