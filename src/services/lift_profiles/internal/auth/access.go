package auth

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"time"

	"powerlifting/liftprofiles/internal/apperr"
)

const accessTimeout = 10 * time.Second

type AccessClient interface {
	Fetch(ctx context.Context, operation string, arguments map[string]any, caller Caller) error
}

type ProfileClient struct {
	URL  string
	HTTP *http.Client
}

func (p ProfileClient) Fetch(ctx context.Context, operation string, arguments map[string]any, caller Caller) error {
	body, err := json.Marshal(map[string]any{"operation": operation, "arguments": arguments})
	if err != nil {
		return apperr.AccessUnavailable()
	}
	ctx, cancel := context.WithTimeout(ctx, accessTimeout)
	defer cancel()
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, p.URL+"/operations/access_context", bytes.NewReader(body))
	if err != nil {
		return apperr.AccessUnavailable()
	}
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Person-Pk", caller.Person)
	request.Header.Set("X-Athlete-Pk", caller.Athlete)
	response, err := p.HTTP.Do(request)
	if err != nil {
		return apperr.AccessUnavailable()
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return apperr.AccessDenied(response.StatusCode)
	}
	return nil
}
