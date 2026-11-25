package payload

import (
	"fmt"
	"path/filepath"
	"strings"
)

func ImportedName(meta map[string]any) string {
	name := text(meta["name"])
	description := strings.Split(strings.TrimSpace(text(meta["description"])), "\n")[0]
	if len([]rune(description)) > 80 {
		words := strings.Fields(description)
		selected := ""
		for _, word := range words {
			candidate := strings.TrimSpace(selected + " " + word)
			if len([]rune(candidate))+1 > 80 {
				break
			}
			selected = candidate
		}
		if selected == "" {
			description = "…"
		} else {
			description = selected + "…"
		}
	}
	filename := strings.ReplaceAll(text(meta["source_filename"]), "\\", "/")
	if filename != "" {
		filename = strings.TrimSuffix(filepath.Base(filename), filepath.Ext(filename))
	}
	filename = strings.ReplaceAll(filename, "_", " ")
	for _, candidate := range []string{name, description, filename} {
		cleaned := strings.Join(strings.Fields(candidate), " ")
		switch strings.ToLower(cleaned) {
		case "", "…", "imported template", "reusable template", "template", "untitled":
			continue
		}
		return cleaned
	}
	if weeks := meta["estimated_weeks"]; weeks != nil && text(weeks) != "0" && text(weeks) != "" {
		return fmt.Sprintf("%v-Week Training Program", weeks)
	}
	return "Training Program"
}
