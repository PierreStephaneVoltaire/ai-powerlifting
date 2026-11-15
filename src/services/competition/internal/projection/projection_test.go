package projection

import (
	"testing"
	"time"
)

func day(t *testing.T, text string) Day {
	t.Helper()
	parsed, ok := ParseDay(text)
	if !ok {
		t.Fatalf("bad day %q", text)
	}
	return parsed
}

func TestNormalizeName(t *testing.T) {
	cases := map[string]string{
		"Squat": "squat", "Bench Press": "bench press", "Deadlifts": "deadlift", "Squat (Pause)": "squat",
		"  Romanian   Deadlift ": "romanian deadlift", "Glutes": "glute", "Press Machines": "press machine", "Boxes": "box",
		"Bench (close (grip)) Press": "bench press", "Stress": "stress",
	}
	for input, want := range cases {
		if got := NormalizeName(input); got != want {
			t.Errorf("%q: got %q want %q", input, got, want)
		}
	}
}

func TestMeetInsufficientReasons(t *testing.T) {
	reference, today := day(t, "2027-03-01"), day(t, "2027-03-01")
	cases := []struct {
		name    string
		program Program
		target  string
		reason  string
	}{
		{"no date", Program{}, "", "No competition date set"},
		{"bad date", Program{}, "soon", "Invalid competition date: soon"},
		{"past", Program{}, "2027-03-01", "Competition date is in the past"},
		{"no data", Program{}, "2027-04-01", "No session data to estimate maxes from"},
	}
	for _, tc := range cases {
		projected, reason := Meet(tc.program, tc.target, reference, today)
		if projected != nil || reason != tc.reason {
			t.Errorf("%s: got %v %q, want %q", tc.name, projected, reason, tc.reason)
		}
	}
}

func TestMeetNeedsProgressionEvenWithCompetitionMaxes(t *testing.T) {
	reference := day(t, "2027-03-01")
	competition, _ := CompetitionFromEntry(map[string]any{"user_status": "completed", "start_date": "2026-12-01", "results": map[string]any{"squat_kg": 200.0}})
	projected, reason := Meet(Program{Competitions: []Competition{competition}}, "2027-04-01", reference, reference)
	if projected != nil || reason != "Insufficient session data to estimate progression" {
		t.Fatalf("%v %q", projected, reason)
	}
}

func TestSessionMaxesNeedTwoLiftsWithThreeEstimatesEach(t *testing.T) {
	reference := day(t, "2027-03-01")
	date := day(t, "2027-02-20")
	build := func(names ...string) []Session {
		var sessions []Session
		for range 3 {
			for _, name := range names {
				sessions = append(sessions, Session{Date: &date, Completed: true, Exercises: []Exercise{{Key: NormalizeName(name), Kg: 100, Reps: 5, Sets: 3}}})
			}
		}
		return sessions
	}
	if !maxesFromSessions(build("Squat"), 42, reference).Empty() {
		t.Error("one lift is not enough")
	}
	maxes := maxesFromSessions(build("Squat", "Deadlift"), 42, reference)
	squat, ok := maxes.Get(Squat)
	if !ok || squat != 100/0.88 {
		t.Errorf("squat %v %v", squat, ok)
	}
	if _, ok := maxes.Get(Bench); ok {
		t.Error("bench must stay unset")
	}
	old := day(t, "2026-01-01")
	stale := build("Squat", "Deadlift")
	for index := range stale {
		stale[index].Date = &old
	}
	if !maxesFromSessions(stale, 42, reference).Empty() {
		t.Error("sessions outside the lookback must not count")
	}
}

func TestEstimateUsesTheRPETable(t *testing.T) {
	rpe := 8.0
	if value, ok := estimate(100, 5, &rpe); !ok || value != 100/0.815 {
		t.Errorf("%v %v", value, ok)
	}
	if value, ok := estimate(100, 5, nil); !ok || value != 100/0.88 {
		t.Errorf("%v %v", value, ok)
	}
	for name, call := range map[string]func() (float64, bool){
		"reps over ten": func() (float64, bool) { return estimate(100, 11, nil) },
		"rpe below six": func() (float64, bool) { low := 5.0; return estimate(100, 5, &low) },
		"no weight":     func() (float64, bool) { return estimate(0, 5, nil) },
	} {
		if _, ok := call(); ok {
			t.Errorf("%s must not estimate", name)
		}
	}
}

func TestCurrentWeek(t *testing.T) {
	today := day(t, "2027-03-01")
	future := day(t, "2027-04-01")
	week := func(value int64) *int64 { return &value }
	sessions := []Session{
		{Date: &today, WeekNumber: week(4), Completed: true},
		{Date: &future, WeekNumber: week(9)},
	}
	if got := currentWeek("2027-01-04", sessions, today); got != 4 {
		t.Errorf("started sessions decide the week, got %d", got)
	}
	if got := currentWeek("2027-01-04", sessions[1:], today); got != 9 {
		t.Errorf("only future sessions fall back to the minimum, got %d", got)
	}
	if got := currentWeek("2027-01-04", nil, today); got != 9 {
		t.Errorf("calendar fallback, got %d", got)
	}
	if got := currentWeek("", nil, today); got != 1 {
		t.Errorf("no start, got %d", got)
	}
	if got := currentWeek("2027-06-01", nil, today); got != 1 {
		t.Errorf("before the start, got %d", got)
	}
}

func TestSessionLoadingMatchesTheSessionStore(t *testing.T) {
	cases := []struct {
		name string
		item map[string]any
		want int64
	}{
		{"number", map[string]any{"week_number": 4.0}, 4},
		{"string number", map[string]any{"week_number": " 7 "}, 7},
		{"label", map[string]any{"week": "Block w12"}, 12},
		{"numeric week", map[string]any{"week": 3.0}, 3},
		{"negative falls back", map[string]any{"week_number": -2.0, "week": "W5"}, 5},
		{"nothing", map[string]any{}, 0},
	}
	for _, tc := range cases {
		if got := *SessionFromItem(tc.item).WeekNumber; got != tc.want {
			t.Errorf("%s: got %d want %d", tc.name, got, tc.want)
		}
	}
	session := SessionFromItem(map[string]any{"date": "2027-01-04", "status": "logged", "session_rpe": 8.0, "exercises": []any{
		map[string]any{"name": "Squat", "sets": 3.0, "reps": 5.0, "kg": 100.0, "set_statuses": []any{"completed", "failed", "skipped"}},
		"junk",
	}})
	if !session.Completed || session.SessionRPE == nil || len(session.Exercises) != 2 {
		t.Fatalf("%+v", session)
	}
	if exercise := session.Exercises[0]; exercise.ExecutedSets() != 2 || exercise.FailedSets() != 1 || exercise.ExecutedVolume() != 1000 {
		t.Fatalf("%+v", exercise)
	}
}

func TestSessionsAreOrderedLikeTheStore(t *testing.T) {
	items := []map[string]any{
		{"date": "2027-01-05", "sk": "b", "week_number": 2.0},
		{"date": "2027-01-04", "sk": "z", "same_day_ordinal": 2.0, "week_number": 1.0},
		{"date": "2027-01-04", "sk": "a", "same_day_ordinal": 2.0, "source_index": 5.0, "week_number": 3.0},
		{"date": "2027-01-04", "sk": "m", "same_day_ordinal": 1.0, "week_number": 4.0},
	}
	sessions := SessionsFromItems(items)
	var weeks []int64
	for _, session := range sessions {
		weeks = append(weeks, *session.WeekNumber)
	}
	if want := []int64{4, 1, 3, 2}; len(weeks) != 4 || weeks[0] != want[0] || weeks[1] != want[1] || weeks[2] != want[2] || weeks[3] != want[3] {
		t.Fatalf("%v", weeks)
	}
}

func TestCompetitionNormalisation(t *testing.T) {
	entries := []map[string]any{
		{"sk": "COMP#b", "user_status": "completed", "start_date": "2026-05-01"},
		{"sk": "COMP#a", "status": "confirmed", "date": "2026-05-01"},
		{"sk": "COMP#dir", "user_status": "available", "start_date": "2026-01-01"},
		{"sk": "COMP#none", "start_date": "2026-01-01"},
		{"sk": "COMP#c", "master_id": "aa", "user_status": "completed", "start_date": "2026-02-01"},
	}
	competitions := CompetitionsFromEntries(entries)
	if len(competitions) != 3 || competitions[0].DateText != "2026-02-01" || competitions[1].Status != "confirmed" || competitions[2].Status != "completed" {
		t.Fatalf("%+v", competitions)
	}
}

func TestCalibration(t *testing.T) {
	reference := day(t, "2027-01-01")
	build := func(date string, total float64) Competition {
		parsed := day(t, date)
		return Competition{DateText: date, Date: &parsed, Status: "completed", Results: map[string]any{"prr": map[string]any{"total": total}}}
	}
	one := calibrate([]Competition{build("2026-01-01", 1.0)}, reference)
	if one.Calibrated || one.Meets != 1 || one.MedianPRR == nil || one.LambdaMultiplier != nil {
		t.Fatalf("%+v", one)
	}
	many := calibrate([]Competition{build("2026-01-01", 1.3), build("2026-02-01", 1.2), build("2026-03-01", 1.1), build("2026-04-01", 0.5)}, reference)
	if !many.Calibrated || many.Meets != 4 || *many.MedianPRR != 1.1 || *many.LambdaMultiplier != 1.05 {
		t.Fatalf("%+v", many)
	}
	future := build("2027-06-01", 1.0)
	if calibrate([]Competition{future}, reference).Meets != 0 {
		t.Fatal("future meets are not history")
	}
}

func TestDeloadDetection(t *testing.T) {
	start := day(t, "2027-01-04")
	week := func(number int64, kg float64, rpe float64) Session {
		date := start.Add(time.Duration(number-1) * 7 * 24 * time.Hour)
		rpeValue := rpe
		return Session{Date: &date, WeekNumber: &number, Completed: true, SessionRPE: &rpeValue, Exercises: []Exercise{{Key: "squat", Kg: kg, Reps: 5, Sets: 4}}}
	}
	sessions := []Session{week(1, 100, 8), week(2, 100, 8), week(3, 60, 5), week(4, 100, 8), week(6, 100, 8)}
	loads := detectWeekLoads(sessions, "2027-01-04")
	if len(loads) != 6 || !loads[2].isDeload || loads[2].hasEffective || !loads[4].isBreak || loads[3].effectiveIndex != 2 {
		t.Fatalf("%+v", loads)
	}
	hard := []Session{week(1, 100, 8), week(2, 100, 8), week(3, 60, 8)}
	if detectWeekLoads(hard, "2027-01-04")[2].isDeload {
		t.Fatal("a light but hard week is not a deload")
	}
}
