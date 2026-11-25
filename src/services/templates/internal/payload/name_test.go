package payload

import "testing"

func TestImportedName(t *testing.T) {
	cases := []struct {
		meta map[string]any
		want string
	}{
		{map[string]any{"name": "Imported Template", "description": "Strength focus\nother"}, "Strength focus"},
		{map[string]any{"name": "template", "source_filename": `C:\Plans\strong_block.xlsx`}, "strong block"},
		{map[string]any{"name": "untitled", "estimated_weeks": 8}, "8-Week Training Program"},
	}
	for _, c := range cases {
		if got := ImportedName(c.meta); got != c.want {
			t.Errorf("ImportedName(%v) = %q, want %q", c.meta, got, c.want)
		}
	}
}
