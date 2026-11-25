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

type DomainClient struct {
	URLTemplate string
	Client      *http.Client
}

func (d DomainClient) Call(ctx context.Context, domain, operation string, caller auth.Caller, args map[string]any) (map[string]any, error) {
	if !strings.Contains(d.URLTemplate, "{domain}") {
		return nil, fmt.Errorf("invalid service URL template")
	}
	body, err := json.Marshal(args)
	if err != nil {
		return nil, err
	}
	url := strings.TrimRight(strings.ReplaceAll(d.URLTemplate, "{domain}", domain), "/") + "/operations/" + operation
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(body))
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
	client := d.Client
	if client == nil {
		client = &http.Client{Timeout: 60 * time.Second}
	}
	response, err := client.Do(request)
	if err != nil {
		return nil, err
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("%s returned HTTP %d", domain, response.StatusCode)
	}
	var result map[string]any
	decoder := json.NewDecoder(io.LimitReader(response.Body, 64<<20))
	decoder.UseNumber()
	if err := decoder.Decode(&result); err != nil {
		return nil, err
	}
	return result, nil
}
