package domain

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"time"

	"powerlifting/templates/internal/auth"
)

type Client struct {
	URLTemplate string
	HTTP        *http.Client
}

type HTTPError struct {
	Domain, Operation string
	Status            int
}

func (e *HTTPError) Error() string {
	return fmt.Sprintf("%s %s returned %d", e.Domain, e.Operation, e.Status)
}

func (c Client) Call(ctx context.Context, domain, operation string, args map[string]any, caller auth.Caller) (map[string]any, error) {
	value, err := c.Value(ctx, domain, operation, args, caller)
	if err != nil {
		return nil, err
	}
	result, ok := value.(map[string]any)
	if !ok {
		return nil, fmt.Errorf("%s %s returned a non-object", domain, operation)
	}
	return result, nil
}

func (c Client) Value(ctx context.Context, domain, operation string, args map[string]any, caller auth.Caller) (any, error) {
	data, err := json.Marshal(args)
	if err != nil {
		return nil, err
	}
	target := strings.TrimRight(strings.ReplaceAll(c.URLTemplate, "{domain}", domain), "/") + "/operations/" + operation
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, target, bytes.NewReader(data))
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
	client := c.HTTP
	if client == nil {
		client = &http.Client{Timeout: 30 * time.Second}
	}
	response, err := client.Do(request)
	if err != nil {
		return nil, err
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return nil, &HTTPError{Domain: domain, Operation: operation, Status: response.StatusCode}
	}
	var result any
	if err = json.NewDecoder(response.Body).Decode(&result); err != nil {
		return nil, err
	}
	return result, nil
}
