package llm

import (
	"context"
	"errors"
)

func (c *Client) EmbedPrivateBatch(ctx context.Context, model string, inputs []string) ([][]float32, error) {
	if len(inputs) == 0 {
		return nil, errors.New("private embedding batch is empty")
	}
	var payload struct {
		Data []struct {
			Index     *int      `json:"index"`
			Embedding []float32 `json:"embedding"`
		} `json:"data"`
	}
	body := map[string]any{"model": model, "input": inputs, "cache": map[string]bool{"no-store": true, "no-cache": true}, "no-log": true}
	if err := c.post(ctx, "/v1/embeddings", body, Metadata{}, true, &payload); err != nil {
		return nil, errors.New("private embedding request failed")
	}
	if len(payload.Data) != len(inputs) {
		return nil, errors.New("private embedding batch has missing vectors")
	}
	vectors := make([][]float32, len(inputs))
	for _, item := range payload.Data {
		if item.Index == nil || *item.Index < 0 || *item.Index >= len(inputs) || vectors[*item.Index] != nil || len(item.Embedding) == 0 {
			return nil, errors.New("private embedding batch has invalid vectors")
		}
		vectors[*item.Index] = item.Embedding
	}
	return vectors, nil
}
