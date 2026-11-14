package auth

import (
	"net/http"
	"strconv"
	"strings"
)

const backendAccount = "/sa/powerlifting-app-backend"

type Generation struct {
	ID      string
	Attempt int64
}

type Caller struct {
	Person     string
	Athlete    string
	Source     string
	JobID      string
	TurnID     string
	Nested     bool
	Generation *Generation
}

func Identity(headers http.Header) Caller {
	return Caller{
		Person:  headers.Get("X-Person-Pk"),
		Athlete: headers.Get("X-Athlete-Pk"),
		Source:  headers.Get("X-PL-Source-Principal"),
	}
}

func FromHeaders(headers http.Header) Caller {
	caller := Identity(headers)
	caller.JobID = headers.Get("X-If-Job-Id")
	caller.TurnID = headers.Get("X-If-Turn-Id")
	caller.Nested = headers.Get("X-PL-Nested-Operation") == "true"
	if id := headers.Get("X-If-Generation-Id"); id != "" {
		attempt, _ := strconv.ParseInt(headers.Get("X-If-Generation-Attempt"), 10, 64)
		caller.Generation = &Generation{ID: id, Attempt: attempt}
	}
	return caller
}

func (c Caller) ActiveJob() string {
	if c.TurnID != "" {
		return c.TurnID
	}
	return c.JobID
}

func (c Caller) IsBackend() bool {
	return strings.HasSuffix(strings.TrimPrefix(c.Source, "spiffe://"), backendAccount)
}

func ServiceAccount(source string) string {
	index := strings.LastIndex(source, "/sa/")
	if index < 0 {
		return ""
	}
	return source[index+len("/sa/"):]
}
