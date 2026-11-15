package activities

import "powerlifting/assistant/internal/store"

const retrievalLimit = 5

func retrievalQuery(in RetrieveInput, embedding []float32) store.RetrievalQuery {
	return store.RetrievalQuery{
		Athlete:     in.Identity.Athlete,
		Person:      in.Identity.Person,
		Permissions: in.Identity.Permissions,
		Embedding:   embedding,
		Limit:       retrievalLimit,
	}
}
