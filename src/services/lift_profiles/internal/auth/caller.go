package auth

import (
	"net/http"
	"strings"
)

const backendAccount = "/sa/powerlifting-app-backend"

type Caller struct {
	Person  string
	Athlete string
	Source  string
	JobID   string
	TurnID  string
	Nested  bool
}

func Identity(header http.Header) Caller {
	return Caller{
		Person:  header.Get("X-Person-Pk"),
		Athlete: header.Get("X-Athlete-Pk"),
		Source:  header.Get("X-PL-Source-Principal"),
	}
}

func FromHeaders(header http.Header) Caller {
	caller := Identity(header)
	caller.JobID = header.Get("X-IF-Job-Id")
	caller.TurnID = header.Get("X-IF-Turn-Id")
	caller.Nested = header.Get("X-PL-Nested-Operation") == "true"
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
