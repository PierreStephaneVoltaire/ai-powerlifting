package access

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"slices"
	"time"
)

const timeout = 10 * time.Second

var (
	ErrDenied      = errors.New("access denied")
	ErrUnavailable = errors.New("access context unavailable")
)

type Identity struct {
	Person          string   `json:"person"`
	Athlete         string   `json:"athlete"`
	Permissions     []string `json:"permissions"`
	CompetitionRead []string `json:"competition_read,omitempty"`
}

func (i Identity) Has(permission string) bool {
	return slices.Contains(i.Permissions, permission)
}

type Client struct {
	HTTP       *http.Client
	ProfileURL string
}

func New(profileURL string) *Client {
	return &Client{HTTP: &http.Client{Timeout: timeout}, ProfileURL: profileURL}
}

func (c *Client) Resolve(ctx context.Context, person, athlete string) (Identity, error) {
	return c.ResolveOperation(ctx, person, athlete, "access_context", map[string]any{})
}

func (c *Client) ResolveOperation(ctx context.Context, person, athlete, operation string, arguments map[string]any) (Identity, error) {
	if person == "" || athlete == "" {
		return Identity{}, ErrDenied
	}
	body, err := json.Marshal(map[string]any{"operation": operation, "arguments": arguments})
	if err != nil {
		return Identity{}, ErrUnavailable
	}
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, c.ProfileURL+"/operations/access_context", bytes.NewReader(body))
	if err != nil {
		return Identity{}, ErrUnavailable
	}
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Person-Pk", person)
	request.Header.Set("X-Athlete-Pk", athlete)
	response, err := c.HTTP.Do(request)
	if err != nil {
		return Identity{}, ErrUnavailable
	}
	defer response.Body.Close()
	switch {
	case response.StatusCode == http.StatusUnauthorized || response.StatusCode == http.StatusForbidden:
		return Identity{}, ErrDenied
	case response.StatusCode != http.StatusOK:
		return Identity{}, ErrUnavailable
	}
	var payload struct {
		Permissions      []string `json:"permissions"`
		CompetitionScope struct {
			Read []string `json:"read"`
		} `json:"competition_scope"`
	}
	if err := json.NewDecoder(response.Body).Decode(&payload); err != nil {
		return Identity{}, ErrUnavailable
	}
	if len(payload.Permissions) == 0 {
		return Identity{}, ErrDenied
	}
	return Identity{Person: person, Athlete: athlete, Permissions: payload.Permissions, CompetitionRead: payload.CompetitionScope.Read}, nil
}
