package markdown

import (
	"fmt"
	"strings"

	"powerlifting/export/internal/values"
)

func aiText(value any) string { return values.Str2(value) }

func aiReports(correlation, evaluation M) string {
	var out strings.Builder
	if len(correlation) > 0 {
		out.WriteString("\n\n### ROI Correlation\n\n")
		if truthy(correlation["insufficient_data"]) {
			out.WriteString("Insufficient data: " + aiText(firstNonBlank(correlation["insufficient_data_reason"], "Not enough training data to analyze.")))
		} else {
			if value := aiText(correlation["summary"]); value != "" {
				out.WriteString(value + "\n\n")
			}
			findings := maps(correlation["findings"])
			if len(findings) == 0 {
				out.WriteString("No correlation findings reported.")
			}
			for _, finding := range findings {
				parts := []string{}
				if driver := aiText(firstNonBlank(finding["driver"], finding["exercise"])); driver != "" {
					parts = append(parts, driver)
				}
				if lift := aiText(finding["lift"]); lift != "" {
					parts = append(parts, "→ "+lift)
				}
				direction := aiText(firstNonBlank(finding["effect"], finding["correlation_direction"]))
				strength := aiText(firstNonBlank(finding["confidence"], finding["strength"]))
				if direction != "" && strength != "" {
					parts = append(parts, "("+strength+" "+direction+")")
				}
				detail := []string{}
				for _, key := range []string{"evidence", "mechanism", "reasoning"} {
					if value := aiText(finding[key]); value != "" {
						detail = append(detail, value)
					}
				}
				if len(detail) > 0 {
					parts = append(parts, "— "+strings.Join(detail, " "))
				}
				if action := aiText(finding["action"]); action != "" {
					parts = append(parts, "Action: "+action)
				}
				out.WriteString("- " + strings.Join(parts, " ") + "\n")
			}
		}
	}
	if len(evaluation) > 0 {
		out.WriteString("\n\n### Program Evaluation\n\n")
		if truthy(evaluation["insufficient_data"]) {
			out.WriteString("Insufficient data: " + aiText(firstNonBlank(evaluation["insufficient_data_reason"], "Not enough training data to evaluate.")))
			return strings.TrimRight(out.String(), "\n")
		}
		if value := aiText(evaluation["stance"]); value != "" {
			out.WriteString("**Stance:** " + value + "\n")
		}
		if value := aiText(evaluation["summary"]); value != "" {
			out.WriteString(value + "\n")
		}
		if value := aiText(evaluation["conclusion"]); value != "" {
			out.WriteString("**Conclusion:** " + value + "\n")
		}
		for _, section := range []struct{ label, key string }{{"What's working", "what_is_working"}, {"What's not working", "what_is_not_working"}, {"Monitoring focus", "monitoring_focus"}} {
			values, _ := evaluation[section.key].([]any)
			if len(values) > 0 {
				out.WriteString("\n**" + section.label + ":**\n")
				for _, value := range values {
					out.WriteString("- " + aiText(value) + "\n")
				}
			}
		}
		for _, item := range maps(evaluation["goal_status"]) {
			out.WriteString(fmt.Sprintf("\n- %s — %s", aiText(item["goal"]), aiText(item["status"])))
			if reason := aiText(item["reason"]); reason != "" {
				out.WriteString(" (" + reason + ")")
			}
		}
		strategy, _ := evaluation["weight_class_strategy"].(map[string]any)
		if recommendation := aiText(strategy["recommendation"]); recommendation != "" {
			out.WriteString("\n\n**Weight Class Strategy:** " + recommendation)
			if value := aiText(strategy["recommended_weight_class_kg"]); value != "" {
				out.WriteString(" — " + value + " kg")
			}
		}
		for _, item := range maps(strategy["viable_options"]) {
			out.WriteString(fmt.Sprintf("\n- %s kg (%s) — %s", aiText(item["weight_class_kg"]), aiText(item["suitability"]), aiText(item["reason"])))
		}
		changes := maps(evaluation["small_changes"])
		if len(changes) > 0 {
			out.WriteString("\n\n**Recommended Changes:**\n")
		}
		for _, item := range changes {
			out.WriteString("- " + aiText(item["change"]))
			if value := aiText(item["why"]); value != "" {
				out.WriteString(" — " + value)
			}
			if value := aiText(item["risk"]); value != "" {
				out.WriteString(" [Risk: " + value + "]")
			}
			if value := aiText(item["priority"]); value != "" {
				out.WriteString(" (Priority: " + value + ")")
			}
			out.WriteString("\n")
		}
	}
	return strings.TrimRight(out.String(), "\n")
}
