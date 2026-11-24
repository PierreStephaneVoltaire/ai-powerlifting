package profile

import (
	"bytes"
	"os"
	"reflect"
	"strings"
	"testing"
)

func TestOptionsMatchSharedDefinitions(t *testing.T) {
	data, err := os.ReadFile("../../../runtime/lift_profile_options.json")
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(data, optionData) {
		t.Fatal("embedded options differ from shared definitions")
	}
}

func TestCleanAndPreserveVideos(t *testing.T) {
	data, err := os.ReadFile("../../../runtime/lift_profile_options.json")
	if err != nil {
		t.Fatal(err)
	}
	defs, err := Parse(data)
	if err != nil {
		t.Fatal(err)
	}
	input := []any{map[string]any{"lift": "deadlift", "options": map[string]any{"stance": "sumo", "hip_height": "high", "grip": "invalid"}, "volume_tolerance": "extreme", "notes": strings.Repeat("é", 1001), "form_videos": map[string]any{"front": "untrusted"}}, map[string]any{"lift": "curl"}}
	stored := []any{map[string]any{"lift": "deadlift", "form_videos": map[string]any{"side": "original"}}}
	result := defs.Normalize(input, stored)
	if len(result) != 1 {
		t.Fatalf("got %d profiles", len(result))
	}
	got := result[0].(map[string]any)
	if !reflect.DeepEqual(got["options"], map[string]any{"stance": "sumo", "hip_height": "low"}) || got["volume_tolerance"] != "moderate" || len([]rune(got["notes"].(string))) != 1000 || !reflect.DeepEqual(got["form_videos"], map[string]any{"side": "original"}) {
		t.Fatalf("unexpected profile: %#v", got)
	}
}

func TestDescribeAndMissing(t *testing.T) {
	data, err := os.ReadFile("../../../runtime/lift_profile_options.json")
	if err != nil {
		t.Fatal(err)
	}
	defs, err := Parse(data)
	if err != nil {
		t.Fatal(err)
	}
	clean := defs.Clean(map[string]any{"lift": "squat", "options": map[string]any{"bar_position": "low", "stance": "shoulder_width"}, "volume_tolerance": "high"})
	description := defs.Describe(clean)
	if !reflect.DeepEqual(description["technique"], map[string]any{"Bar position": "Low", "Stance": "Shoulder width"}) || description["volume_tolerance"] != "high" {
		t.Fatalf("unexpected description: %#v", description)
	}
	missing := defs.Missing(clean)
	if len(missing) != 9 || missing[0] != "Hand width" || missing[8] != "Rep range you recover from" {
		t.Fatalf("unexpected missing fields: %#v", missing)
	}
}

func TestSuggestRetainsSelectionsAndRejectsInvalidOptions(t *testing.T) {
	data, err := os.ReadFile("../../../runtime/lift_profile_options.json")
	if err != nil {
		t.Fatal(err)
	}
	defs, err := Parse(data)
	if err != nil {
		t.Fatal(err)
	}
	got := defs.Suggest("bench", map[string]any{"arch": "max"}, map[string]any{"grip_width": "wide", "arch": nil, "touch_point": "invalid", "leg_drive": "timed", "volume_tolerance": "low"})
	if !reflect.DeepEqual(got["options"], map[string]any{"grip_width": "wide", "arch": "max", "leg_drive": "timed"}) || !reflect.DeepEqual(got["changed"], []string{"grip_width", "leg_drive"}) || got["volume_tolerance"] != "low" {
		t.Fatalf("unexpected suggestion: %#v", got)
	}
}

func TestSuggestSchemaContainsEveryField(t *testing.T) {
	data, err := os.ReadFile("../../../runtime/lift_profile_options.json")
	if err != nil {
		t.Fatal(err)
	}
	defs, err := Parse(data)
	if err != nil {
		t.Fatal(err)
	}
	function := defs.SuggestSchema("bench")["function"].(map[string]any)
	parameters := function["parameters"].(map[string]any)
	properties := parameters["properties"].(map[string]any)
	if len(properties) != len(defs["bench"])+1 || properties["grip_width"] == nil || properties["volume_tolerance"] == nil {
		t.Fatalf("unexpected properties: %#v", properties)
	}
}
