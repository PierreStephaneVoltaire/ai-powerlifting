package visibility

import "slices"

type Participant struct {
	Person      string
	Permissions []string
	Resolved    bool
}

type Result struct {
	Allowed bool
	Lacking map[string][]string
}

func Check(required []string, participants []Participant) Result {
	result := Result{Allowed: true, Lacking: map[string][]string{}}
	for _, participant := range participants {
		for _, permission := range required {
			if !participant.Resolved || !slices.Contains(participant.Permissions, permission) {
				result.Lacking[participant.Person] = append(result.Lacking[participant.Person], permission)
			}
		}
	}
	if len(result.Lacking) > 0 {
		result.Allowed = false
	}
	return result
}

func Union(groups ...[]string) []string {
	seen := map[string]bool{}
	var merged []string
	for _, group := range groups {
		for _, permission := range group {
			if !seen[permission] {
				seen[permission] = true
				merged = append(merged, permission)
			}
		}
	}
	slices.Sort(merged)
	return merged
}
