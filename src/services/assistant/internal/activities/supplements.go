package activities

import "regexp"

var capsuleDose = regexp.MustCompile(`(?i)(^|[^a-z])(caps?(ules?)?|pills?|tablets?|tabs?|softgels?)($|[^a-z])`)

func validateSupplementCompounds(arguments map[string]any) string {
	phases, _ := arguments["phases"].([]any)
	for _, raw := range phases {
		phase, _ := raw.(map[string]any)
		items, _ := phase["items"].([]any)
		for _, raw := range items {
			item, _ := raw.(map[string]any)
			dose, _ := item["dose"].(string)
			if capsuleDose.MatchString(dose) {
				return "supplement items must be individual compounds with total daily amounts and units, not capsule or pill counts. Expand verified product labels, scale to the actual daily intake, combine the same compound across products, and put product contributions in notes. Do not invent unverified ingredient amounts."
			}
		}
	}
	return ""
}
