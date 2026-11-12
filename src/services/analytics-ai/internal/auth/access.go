package auth

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"time"

	"powerlifting/analytics-ai/internal/apperr"
)

const accessTimeout = 10 * time.Second

type Access map[string]any

func (a Access) String(key string) string {
	value, _ := a[key].(string)
	return value
}

type AccessClient interface {
	Fetch(ctx context.Context, operation string, arguments map[string]any, caller Caller) (Access, error)
}

type ProfileClient struct {
	URL  string
	HTTP *http.Client
}

func (p ProfileClient) Fetch(ctx context.Context, operation string, arguments map[string]any, caller Caller) (Access, error) {
	body, err := json.Marshal(map[string]any{"operation": operation, "arguments": arguments})
	if err != nil {
		return nil, apperr.AccessUnavailable()
	}
	ctx, cancel := context.WithTimeout(ctx, accessTimeout)
	defer cancel()
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, p.URL+"/operations/access_context", bytes.NewReader(body))
	if err != nil {
		return nil, apperr.AccessUnavailable()
	}
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Person-Pk", caller.Person)
	request.Header.Set("X-Athlete-Pk", caller.Athlete)
	response, err := p.HTTP.Do(request)
	if err != nil {
		return nil, apperr.AccessUnavailable()
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return nil, apperr.AccessDenied(response.StatusCode)
	}
	var access Access
	if err := json.NewDecoder(response.Body).Decode(&access); err != nil {
		return nil, apperr.AccessUnavailable()
	}
	return access, nil
}
