package auth

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"time"

	"powerlifting/analytics-export/internal/apperr"
)

const accessTimeout = 10 * time.Second

type Access struct {
	Client     *http.Client
	ProfileURL string
}

func NewAccess(profileURL string) *Access {
	return &Access{Client: &http.Client{Timeout: accessTimeout}, ProfileURL: profileURL}
}

func (a *Access) Fetch(ctx context.Context, operation string, arguments map[string]any, caller Caller) (map[string]any, error) {
	body, err := json.Marshal(map[string]any{"operation": operation, "arguments": arguments})
	if err != nil {
		return nil, apperr.AccessUnavailable()
	}
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, a.ProfileURL+"/operations/access_context", bytes.NewReader(body))
	if err != nil {
		return nil, apperr.AccessUnavailable()
	}
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Person-Pk", caller.Person)
	request.Header.Set("X-Athlete-Pk", caller.Athlete)
	response, err := a.Client.Do(request)
	if err != nil {
		return nil, apperr.AccessUnavailable()
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return nil, apperr.AccessDenied(response.StatusCode)
	}
	var access map[string]any
	if err := json.NewDecoder(response.Body).Decode(&access); err != nil {
		return nil, apperr.AccessUnavailable()
	}
	return access, nil
}
