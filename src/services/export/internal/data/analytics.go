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

type AnalyticsClient struct {
	URL    string
	Client *http.Client
}

func (a AnalyticsClient) Weekly(ctx context.Context, caller auth.Caller, arguments map[string]any) (map[string]any, error) {
	encoded, err := json.Marshal(arguments)
	if err != nil {
		return nil, err
	}
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, strings.TrimRight(a.URL, "/")+"/operations/weekly_analysis", bytes.NewReader(encoded))
	if err != nil {
		return nil, err
	}
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Person-Pk", caller.Person)
	request.Header.Set("X-Athlete-Pk", caller.Athlete)
	if job := caller.ActiveJob(); job != "" {
		request.Header.Set("X-If-Turn-Id", job)
		request.Header.Set("X-PL-Nested-Operation", "true")
	}
	client := a.Client
	if client == nil {
		client = &http.Client{Timeout: 60 * time.Second}
	}
	response, err := client.Do(request)
	if err != nil {
		return nil, err
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("analytics returned HTTP %d", response.StatusCode)
	}
	var result map[string]any
	if err := json.NewDecoder(io.LimitReader(response.Body, 64<<20)).Decode(&result); err != nil {
		return nil, err
	}
	return result, nil
}
