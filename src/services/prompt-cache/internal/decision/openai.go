package decision

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strings"
)

const instructions = "Can the stored response be reused unchanged for the new request? same = answers it as is; contextual = the ask or its data differs so the answer would change; temporal = the answer depends on the date and the date moved; none = unrelated."

var choices = []map[string]string{
	{"value": Same, "description": "The stored response answers the new request as is."},
	{"value": Contextual, "description": "The ask or its data differs so the answer would change."},
	{"value": Temporal, "description": "The answer depends on the date and the date moved."},
	{"value": None, "description": "The stored request is unrelated."},
}

type OpenAI struct {
	URL           string
	Key           string
	Model         string
	MinConfidence float64
	HTTP          *http.Client
}

type answer struct {
	Type       string  `json:"type"`
	Name       string  `json:"name"`
	Choice     string  `json:"choice"`
	Confidence float64 `json:"confidence"`
}

type reply struct {
	Answers []answer `json:"answers"`
}

func questionName(entryID string) string {
	return "candidate_" + entryID
}

func (o OpenAI) body(input Input) ([]byte, error) {
	candidates := make([]map[string]any, len(input.Candidates))
	questions := make([]map[string]any, len(input.Candidates))
	for index, candidate := range input.Candidates {
		candidates[index] = map[string]any{"entry_id": candidate.EntryID, "request": candidate.Request, "response": candidate.Response, "context": candidate.Context}
		questions[index] = map[string]any{"type": "choice", "name": questionName(candidate.EntryID), "instructions": instructions, "choices": choices}
	}
	payload := map[string]any{"new": map[string]any{"request": input.Request, "context": input.Context}, "candidates": candidates}
	return json.Marshal(map[string]any{
		"model":            o.Model,
		"input":            []any{map[string]any{"role": "user", "content": []any{map[string]any{"type": "input_json", "json": payload}}}},
		"questions":        questions,
		"prompt_cache_key": input.Athlete + ":" + input.Operation,
	})
}

func (o OpenAI) Decide(ctx context.Context, input Input) (Verdict, error) {
	if o.Key == "" || len(input.Candidates) == 0 {
		return Verdict{Reason: None}, nil
	}
	body, err := o.body(input)
	if err != nil {
		return Verdict{}, err
	}
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, o.URL, bytes.NewReader(body))
	if err != nil {
		return Verdict{}, err
	}
	request.Header.Set("Authorization", "Bearer "+o.Key)
	request.Header.Set("Content-Type", "application/json")
	response, err := o.HTTP.Do(request)
	if err != nil {
		return Verdict{}, err
	}
	defer response.Body.Close()
	raw, err := io.ReadAll(io.LimitReader(response.Body, 4<<20))
	if err != nil {
		return Verdict{}, err
	}
	if response.StatusCode != http.StatusOK {
		return Verdict{}, fmt.Errorf("decisions status %d", response.StatusCode)
	}
	var parsed reply
	if err := json.Unmarshal(raw, &parsed); err != nil {
		return Verdict{}, err
	}
	return o.verdict(input, parsed)
}

func (o OpenAI) verdict(input Input, parsed reply) (Verdict, error) {
	byName := map[string]answer{}
	for _, item := range parsed.Answers {
		byName[item.Name] = item
	}
	best := Verdict{Reason: None}
	answered := false
	for _, candidate := range input.Candidates {
		item, ok := byName[questionName(candidate.EntryID)]
		if !ok || item.Type != "choice" {
			continue
		}
		answered = true
		choice := strings.TrimSpace(item.Choice)
		if choice == Same && item.Confidence >= o.MinConfidence {
			return Verdict{EntryID: candidate.EntryID, Reason: Same, Confidence: item.Confidence}, nil
		}
		if choice == Same {
			choice = None
		}
		if best.Reason == None && (choice == Contextual || choice == Temporal) {
			best = Verdict{Reason: choice, Confidence: item.Confidence}
		}
	}
	if !answered {
		return Verdict{}, errors.New("no usable decision answers")
	}
	return best, nil
}
