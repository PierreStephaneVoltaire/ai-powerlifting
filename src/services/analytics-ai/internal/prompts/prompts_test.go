package prompts

import (
	"encoding/json"
	"os"
	"strings"
	"testing"
)

type fixtureProfile struct {
	Lift            string `json:"lift"`
	StyleNotes      string `json:"style_notes"`
	StickingPoints  string `json:"sticking_points"`
	PrimaryMuscle   string `json:"primary_muscle"`
	VolumeTolerance string `json:"volume_tolerance"`
}

type fixture struct {
	Weeks              int                 `json:"weeks"`
	WindowStart        string              `json:"window_start"`
	WeeksToPrimaryComp *float64            `json:"weeks_to_primary_comp"`
	LiftProfiles       []fixtureProfile    `json:"lift_profiles"`
	Measurements       map[string]*float64 `json:"athlete_measurements"`
	CaloricStatus      string              `json:"caloric_status"`
	Bodyweight         *struct {
		Latest    *float64 `json:"latest"`
		Direction string   `json:"direction"`
		Change    *float64 `json:"change"`
	} `json:"bodyweight_trend"`
	Weekly []struct {
		Week     int      `json:"week"`
		Squat    *float64 `json:"squat"`
		Bench    *float64 `json:"bench"`
		Deadlift *float64 `json:"deadlift"`
	} `json:"weekly_e1rm"`
	Accessory []struct {
		Week      int `json:"week"`
		Exercises []struct {
			Name     string  `json:"name"`
			VolumeKg float64 `json:"volume_kg"`
		} `json:"exercises"`
	} `json:"weekly_accessory"`
	ROI []struct {
		Exercise      string  `json:"exercise"`
		PearsonR      float64 `json:"pearson_r"`
		WeeksObserved int     `json:"weeks_observed"`
	} `json:"exercise_roi"`
}

var measurementOrder = []string{"height_cm", "arm_wingspan_cm", "leg_length_cm", "weight_class_kg", "current_body_weight_kg"}

func (f fixture) input() CorrelationInput {
	input := CorrelationInput{Weeks: f.Weeks, WindowStart: f.WindowStart, WeeksToPrimaryComp: f.WeeksToPrimaryComp, CaloricStatus: f.CaloricStatus}
	for _, profile := range f.LiftProfiles {
		input.LiftProfiles = append(input.LiftProfiles, LiftProfile(profile))
	}
	for _, name := range measurementOrder {
		if value, present := f.Measurements[name]; present {
			input.Measurements = append(input.Measurements, Measurement{name, value})
		}
	}
	if f.Bodyweight != nil {
		input.Bodyweight = &BodyweightTrend{f.Bodyweight.Latest, f.Bodyweight.Direction, f.Bodyweight.Change}
	}
	for _, row := range f.Weekly {
		input.E1rm = append(input.E1rm, WeekLifts{row.Week, row.Squat, row.Bench, row.Deadlift})
	}
	for _, week := range f.Accessory {
		entry := WeekAccessory{Week: week.Week}
		for _, exercise := range week.Exercises {
			entry.Exercises = append(entry.Exercises, Exercise{exercise.Name, exercise.VolumeKg})
		}
		input.Accessory = append(input.Accessory, entry)
	}
	for _, row := range f.ROI {
		input.ExerciseROI = append(input.ExerciseROI, ROIRow(row))
	}
	return input
}

func read(t *testing.T, path string) string {
	t.Helper()
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	return string(raw)
}

func TestCorrelationUserMatchesJinja(t *testing.T) {
	for _, name := range []string{"full", "bare", "down"} {
		var data fixture
		if err := json.Unmarshal([]byte(read(t, "testdata/correlation_user_"+name+"_input.json")), &data); err != nil {
			t.Fatal(err)
		}
		got, err := RenderCorrelationUser(data.input())
		if err != nil {
			t.Fatal(err)
		}
		if want := read(t, "testdata/correlation_user_"+name+".txt"); got != want {
			t.Errorf("%s render differs\n--- got ---\n%s\n--- want ---\n%s", name, got, want)
		}
	}
}

func TestSystemPromptsMatchJinjaLoader(t *testing.T) {
	cases := map[string]string{
		"correlation_system":            CorrelationSystem(),
		"program_evaluation_system":     ProgramEvaluationSystem(),
		"multi_block_comparison_system": MultiBlockSystem(),
	}
	for name, got := range cases {
		if want := read(t, "testdata/"+name+".txt"); got != want {
			t.Errorf("%s differs from the Python loader output", name)
		}
	}
}

func TestToolSchemasAreDefined(t *testing.T) {
	for _, name := range []string{"report_correlation_findings", "report_program_evaluation", "submit_multi_block_comparison"} {
		tool := Tool(name)
		function, _ := tool["function"].(map[string]any)
		if tool["type"] != "function" || function["name"] != name {
			t.Errorf("%s: unexpected tool %v", name, tool)
		}
	}
}

func TestTitleMatchesPython(t *testing.T) {
	for input, want := range map[string]string{"bench press": "Bench Press", "squat": "Squat", "it's": "It'S", "DEAD-lift": "Dead-Lift"} {
		if got := Title(input); got != want {
			t.Errorf("Title(%q) = %q want %q", input, got, want)
		}
	}
	if strings.TrimSpace(CorrelationSystem()) == "" {
		t.Fatal("empty system prompt")
	}
}
