package people

import (
	"encoding/json"
	"testing"
	"time"

	"powerlifting/profile/internal/clock"
	"powerlifting/profile/internal/value"
)

var epoch = time.Date(2026, 11, 14, 12, 0, 0, 0, time.UTC)

func normalize(raw map[string]any) Settings { return Normalize(raw, epoch, clock.ISO) }

func TestNormalizeAppliesPythonDefaultsAndClamps(t *testing.T) {
	settings := normalize(map[string]any{
		"pk": "p", "username": "Weird User!", "bio": "  " + string(make([]byte, 0)) + "hello ", "age_class": "master9", "sex": "x",
		"bodyweight_kg": value.Decimal("0"), "roles": []any{"coach", "bogus", "coach"}, "active_role": "handler",
		"federations": []any{"IPF", " IPF ", "", 4}, "ranking_country": " Canada ", "ranking_region": "  ",
	})
	if settings.Username != "weird_user_" || settings.AgeClass != "open" || settings.Sex != nil || settings.BodyweightKG != nil {
		t.Fatalf("%+v", settings)
	}
	if len(settings.Roles) != 1 || settings.Roles[0] != "coach" || settings.ActiveRole != "handler" {
		t.Fatalf("roles %v active %s", settings.Roles, settings.ActiveRole)
	}
	if len(settings.Federations) != 1 || settings.RankingCountry != "Canada" || settings.RankingRegion != nil || settings.Bio != "hello" {
		t.Fatalf("%+v", settings)
	}
	if settings.CreatedAt != "2026-11-14T12:00:00+00:00" {
		t.Fatalf("missing created_at falls back to now: %s", settings.CreatedAt)
	}
}

func TestTrainingMaxesNeedAllThreePositiveLifts(t *testing.T) {
	complete := map[string]any{"squat_kg": json.Number("180"), "bench_kg": value.Decimal("120.5"), "deadlift_kg": 220.0}
	if maxes := TrainingMaxes(complete); maxes == nil || maxes["bench_kg"] != json.Number("120.5") || maxes["squat_kg"] != json.Number("180.0") {
		t.Fatalf("%v", maxes)
	}
	if TrainingMaxes(map[string]any{"squat_kg": 1, "bench_kg": 0, "deadlift_kg": 1}) != nil {
		t.Fatal("a zero lift invalidates the set")
	}
}

func TestTagNormalizationFollowsNFKCAndCasefoldDedupe(t *testing.T) {
	name, ok := NormalizeTag("  ＳＴＲＯＮＧ   Raw ")
	if !ok || name != "STRONG Raw" {
		t.Fatalf("%q %v", name, ok)
	}
	if _, ok := NormalizeTag("   "); ok {
		t.Fatal("blank tag accepted")
	}
	if _, ok := NormalizeTag(string(make([]rune, 51))); ok {
		t.Fatal("overlong tag accepted")
	}
	tags := NormalizeTags([]any{map[string]any{"tag": "Strong", "approved": true}, "STRONG", "Straße", "STRASSE", 5})
	if len(tags) != 2 || tags[0].Name != "Strong" || tags[1].Name != "Straße" {
		t.Fatalf("%+v", tags)
	}
}

func TestOnboardingStatusOrder(t *testing.T) {
	cases := []struct {
		item map[string]any
		want string
	}{
		{map[string]any{}, "role"},
		{map[string]any{"roles": []any{"athlete"}}, "profile"},
		{map[string]any{"roles": []any{"athlete"}, "profile_complete": true}, "athlete_basics"},
		{map[string]any{"roles": []any{"coach"}, "profile_complete": true}, "done"},
		{map[string]any{"roles": []any{"athlete"}, "profile_complete": true, "sex": "male", "bodyweight_kg": 80, "training_maxes": map[string]any{"squat_kg": 1, "bench_kg": 1, "deadlift_kg": 1}}, "done"},
	}
	for _, c := range cases {
		if got := DeriveOnboarding(c.item).NextStep; got != c.want {
			t.Errorf("%v: got %s want %s", c.item, got, c.want)
		}
	}
}

func TestSanitizeUsernameFallsBackToTimestamp(t *testing.T) {
	if got := SanitizeUsername("a", epoch); got != "user_1794657600" {
		t.Fatalf("%s", got)
	}
	if got := SanitizeUsername("Name With Spaces", epoch); got != "name_with_spaces" {
		t.Fatalf("%s", got)
	}
}
