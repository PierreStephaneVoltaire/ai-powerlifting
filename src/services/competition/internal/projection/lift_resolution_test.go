package projection

import "testing"

func TestResolveLiftFollowsTheAnalyticsRules(t *testing.T) {
	glossary := GlossaryFromItems([]any{
		map[string]any{"name": "Back Squat", "lift_transfer": map[string]any{"squat": 0.95, "bench": 0.0, "deadlift": 0.2}},
		map[string]any{"name": "Close Grip Bench", "lift_transfer": map[string]any{"bench": 0.89}},
		map[string]any{"name": "Tied", "lift_transfer": map[string]any{"squat": 0.9, "bench": 0.9}},
		map[string]any{"name": "Clamped", "lift_transfer": map[string]any{"deadlift": 7.0}},
		map[string]any{"name": "Pause Bench", "archived": true, "lift_transfer": map[string]any{"bench": 0.95}},
		map[string]any{"name": "Pause Bench", "lift_transfer": map[string]any{"deadlift": 0.95}},
		map[string]any{"name": "No Transfer"},
	})
	cases := []struct {
		name string
		want Lift
		ok   bool
	}{
		{"Squat", Squat, true},
		{"Squats", Squat, true},
		{"Bench", Bench, true},
		{"Bench Press", Bench, true},
		{"Bench Press (Paused)", Bench, true},
		{"Deadlift", Deadlift, true},
		{"Back Squat", Squat, true},
		{"Close Grip Bench", 0, false},
		{"Tied", Bench, true},
		{"Clamped", Deadlift, true},
		{"Pause Bench", Deadlift, true},
		{"No Transfer", 0, false},
		{"Leg Press", 0, false},
	}
	for _, tc := range cases {
		got, ok := glossary.ResolveLift(NormalizeName(tc.name))
		if ok != tc.ok || (ok && got != tc.want) {
			t.Errorf("%s: got %v %v, want %v %v", tc.name, got, ok, tc.want, tc.ok)
		}
	}
	if _, ok := (Glossary{}).ResolveLift("back squat"); ok {
		t.Error("an empty glossary resolves only the canonical lifts")
	}
}

func progressionSessions(t *testing.T, names map[int]string) []Session {
	t.Helper()
	var sessions []Session
	for week := 1; week <= 5; week++ {
		date := day(t, "2027-02-01").AddDate(0, 0, (week-1)*7)
		number := int64(week)
		sessions = append(sessions, Session{
			Date: &date, WeekNumber: &number, Completed: true,
			Exercises: []Exercise{{Key: NormalizeName(names[week]), Kg: 100 + float64(week)*5, Reps: 5, Sets: 3}},
		})
	}
	return sessions
}

func TestProgressionRateResolvesTheMainLiftNames(t *testing.T) {
	reference := day(t, "2027-03-10")
	cases := []struct {
		name     string
		lift     Lift
		glossary Glossary
		names    map[int]string
		ok       bool
	}{
		{"bench press", Bench, Glossary{}, map[int]string{1: "Bench Press", 2: "Bench Press", 3: "Bench Press", 4: "Bench Press", 5: "Bench Press"}, true},
		{"mixed bench naming", Bench, Glossary{}, map[int]string{1: "Bench", 2: "Bench Press", 3: "bench press (pause)", 4: "Bench", 5: "Bench Press"}, true},
		{"squat plural", Squat, Glossary{}, map[int]string{1: "Squats", 2: "Squat", 3: "Squat", 4: "Squat", 5: "Squat"}, true},
		{"glossary squat variant", Squat, GlossaryFromItems([]any{map[string]any{"name": "Back Squat", "lift_transfer": map[string]any{"squat": 1.0}}}), map[int]string{1: "Back Squat", 2: "Back Squat", 3: "Squat", 4: "Back Squat", 5: "Back Squat"}, true},
		{"unknown variant without glossary", Squat, Glossary{}, map[int]string{1: "Back Squat", 2: "Back Squat", 3: "Back Squat", 4: "Back Squat", 5: "Back Squat"}, false},
		{"wrong lift", Deadlift, Glossary{}, map[int]string{1: "Bench Press", 2: "Bench Press", 3: "Bench Press", 4: "Bench Press", 5: "Bench Press"}, false},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			result, ok := progressionRate(progressionSessions(t, tc.names), tc.lift, tc.glossary, "2027-02-01", reference)
			if ok != tc.ok {
				t.Fatalf("got ok=%v", ok)
			}
			if ok && result.slope <= 0 {
				t.Fatalf("slope %v", result.slope)
			}
		})
	}
}
