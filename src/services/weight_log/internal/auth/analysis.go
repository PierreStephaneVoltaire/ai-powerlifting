package auth

func AnalysisAthlete(access map[string]any) string {
	if athlete, _ := access["athlete_pk"].(string); athlete != "" {
		return athlete
	}
	own, _ := access["own_athlete_pk"].(string)
	return own
}
