package data

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

	"powerlifting/export/internal/auth"
)

type ProgramClient struct {
	URL    string
	Client *http.Client
}

func NewProgramClient(url string) *ProgramClient {
	return &ProgramClient{URL: strings.TrimRight(url, "/"), Client: &http.Client{Timeout: 30 * time.Second}}
}

func (p *ProgramClient) Get(ctx context.Context, caller auth.Caller, selection map[string]any) (map[string]any, error) {
	arguments := map[string]any{"pk": caller.Athlete}
	for _, key := range []string{"block", "window_start", "window_end"} {
		if value, ok := selection[key]; ok {
			arguments[key] = value
		}
	}
	body, err := json.Marshal(arguments)
	if err != nil {
		return nil, err
	}
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, p.URL+"/operations/program_get", bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Person-Pk", caller.Person)
	request.Header.Set("X-Athlete-Pk", caller.Athlete)
	response, err := p.Client.Do(request)
	if err != nil {
		return nil, fmt.Errorf("load program: %w", err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("program service returned HTTP %d", response.StatusCode)
	}
	var program map[string]any
	decoder := json.NewDecoder(io.LimitReader(response.Body, 64<<20))
	decoder.UseNumber()
	if err = decoder.Decode(&program); err != nil {
		return nil, fmt.Errorf("decode program: %w", err)
	}
	if program == nil {
		return nil, fmt.Errorf("program service returned null")
	}
	return program, nil
}
