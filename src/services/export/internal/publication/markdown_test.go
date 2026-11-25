package publication

import "testing"

func TestMarkdownViewRemovesPrivateMetadataWithoutProfileGrant(t *testing.T) {
	program := map[string]any{"meta": map[string]any{"program_name": "My plan", "sex": "female", "training_notes": "note", "block_notes": []any{map[string]any{"private": true, "text": "secret"}, map[string]any{"text": "shared"}}}, "settings": map[string]any{"sex": "female", "secret": "hidden"}}
	access := Access{"permissions": []string{"program:read"}, "granted_permissions": []string{"program:read"}}
	view := MarkdownView(program, access)
	meta := view["meta"].(map[string]any)
	if _, ok := meta["sex"]; ok {
		t.Fatal("sex leaked without profile permission")
	}
	if len(meta["block_notes"].([]any)) != 1 {
		t.Fatalf("private note leaked: %#v", meta)
	}
	if len(view["settings"].(map[string]any)) != 0 {
		t.Fatalf("settings leaked: %#v", view["settings"])
	}
}
