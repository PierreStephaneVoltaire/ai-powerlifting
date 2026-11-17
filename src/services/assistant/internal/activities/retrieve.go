package activities

import (
	"context"
	"fmt"
	"strings"

	"powerlifting/assistant/internal/llm"
)

func (d *Deps) Retrieve(ctx context.Context, in RetrieveInput) (RetrieveOutput, error) {
	query := strings.TrimSpace(in.Query)
	if query == "" {
		return RetrieveOutput{}, nil
	}
	embedding, err := d.LLM.Embed(ctx, d.Config.EmbedModel, query, llm.Metadata{UserID: in.Identity.Person, ConversationID: in.ConversationID, WorkflowID: in.WorkflowID, Role: "embed"})
	if err != nil {
		return RetrieveOutput{}, err
	}
	if len(embedding) != d.Config.EmbedDim {
		return RetrieveOutput{}, fmt.Errorf("embedding has %d dimensions, want %d", len(embedding), d.Config.EmbedDim)
	}
	snippets, err := d.Store.Retrieve(ctx, retrievalQuery(in, embedding))
	if err != nil {
		return RetrieveOutput{}, err
	}
	return RetrieveOutput{Snippets: snippets}, nil
}
