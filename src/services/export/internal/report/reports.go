package report

func CachedReports(sessionBlock string, window map[string]any, sessions []any, access map[string]any) []string {
	if sessionBlock != "current" || len(window) == 0 {
		return nil
	}
	if access != nil {
		allowed := false
		switch permissions := access["permissions"].(type) {
		case []any:
			for _, p := range permissions {
				if p == "analytics:read" {
					allowed = true
				}
			}
		case []string:
			for _, p := range permissions {
				if p == "analytics:read" {
					allowed = true
				}
			}
		}
		if !allowed {
			return nil
		}
	}
	start, _ := number(window["week_start"])
	if start == 0 {
		start = 1
	}
	end, _ := number(window["week_end"])
	reports := []string{}
	if end-start+1 >= 4 {
		reports = append(reports, "analytics.correlation")
	}
	completed := 0
	for _, raw := range sessions {
		session, ok := raw.(map[string]any)
		if !ok {
			continue
		}
		done, _ := session["completed"].(bool)
		block, _ := session["block"].(string)
		if done && (block == "" || block == "current") {
			completed++
		}
	}
	if window["window_key"] == "block" && completed >= 4 {
		reports = append(reports, "analytics.block_evaluation")
	}
	return reports
}
