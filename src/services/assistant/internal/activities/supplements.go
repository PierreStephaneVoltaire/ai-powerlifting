package activities

import "regexp"

var capsuleDose = regexp.MustCompile(`(?i)(^|[^a-z])(caps?(ules?)?|pills?|tablets?|tabs?|softgels?)($|[^a-z])`)
var reportingFiller = regexp.MustCompile(`(?i)\b(as reported|user[- ]reported|self[- ]reported|per (the )?user|reported by (the )?(user|athlete))\b`)

const supplementNotesError = "supplement notes must explain the compound's purpose and flag dose effectiveness using established evidence. Remove reporting filler such as 'as reported' or 'user-reported', product arithmetic and generic disclaimers. State uncertainty when an effective dose is not established."

func validateSupplementCompounds(arguments map[string]any) string {
	phases, _ := arguments["phases"].([]any)
	for _, raw := range phases {
		phase, _ := raw.(map[string]any)
		if notes, _ := phase["notes"].(string); reportingFiller.MatchString(notes) {
			return supplementNotesError
		}
		items, _ := phase["items"].([]any)
		for _, raw := range items {
			item, _ := raw.(map[string]any)
			dose, _ := item["dose"].(string)
			if capsuleDose.MatchString(dose) {
				return "supplement items must be individual compounds with total daily amounts and units, not capsule or pill counts. Expand verified product labels, scale to the actual daily intake, and combine the same compound across products. Notes explain purpose and dose effectiveness. Do not invent unverified ingredient amounts."
			}
			if notes, _ := item["notes"].(string); reportingFiller.MatchString(notes) {
				return supplementNotesError
			}
		}
	}
	return ""
}
