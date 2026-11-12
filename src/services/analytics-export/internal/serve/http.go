package serve

import (
	"context"
	"encoding/json"
	"io"
	"log/slog"
	"net/http"
	"strconv"
	"time"

	"github.com/danielgtaylor/huma/v2"
	"github.com/danielgtaylor/huma/v2/adapters/humachi"
	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"

	"powerlifting/analytics-export/internal/apperr"
	"powerlifting/analytics-export/internal/auth"
	"powerlifting/analytics-export/internal/contract"
	"powerlifting/analytics-export/internal/service"
)

const (
	requestTimeout = 180 * time.Second
	maxBodyBytes   = 8 * 1024 * 1024
	serviceName    = "pl-" + contract.Domain
)

type Headers struct {
	PersonPk          string `header:"X-Person-Pk" required:"false" doc:"Authenticated Person partition key."`
	AthletePk         string `header:"X-Athlete-Pk" required:"false" doc:"Athlete the request is scoped to."`
	SourcePrincipal   string `header:"X-PL-Source-Principal" required:"false" doc:"Calling workload principal, set by the mesh."`
	JobID             string `header:"X-If-Job-Id" required:"false" doc:"Active IF job."`
	TurnID            string `header:"X-If-Turn-Id" required:"false" doc:"Active native turn."`
	Nested            string `header:"X-PL-Nested-Operation" required:"false" doc:"true when called from inside another operation."`
	GenerationID      string `header:"X-If-Generation-Id" required:"false" doc:"Generation identifier."`
	GenerationAttempt string `header:"X-If-Generation-Attempt" required:"false" doc:"Generation attempt number."`
}

func (h Headers) caller() auth.Caller {
	caller := auth.Caller{
		Person:  h.PersonPk,
		Athlete: h.AthletePk,
		Source:  h.SourcePrincipal,
		JobID:   h.JobID,
		TurnID:  h.TurnID,
		Nested:  h.Nested == "true",
	}
	if h.GenerationID != "" {
		attempt, _ := strconv.ParseInt(h.GenerationAttempt, 10, 64)
		caller.Generation = &auth.Generation{ID: h.GenerationID, Attempt: attempt}
	}
	return caller
}

type callInput struct {
	Headers
	RawBody []byte
}

type callOutput struct {
	Body any
}

type mcpOutput struct {
	Status int
	Body   any
}

type healthOutput struct {
	Body struct {
		Status string `json:"status"`
		Domain string `json:"domain"`
	}
}

func Handler(svc *service.Service, log *slog.Logger) http.Handler {
	huma.NewError = func(status int, message string, _ ...error) huma.StatusError {
		return &apperr.Error{Status: status, Code: "http", Message: message}
	}
	router := chi.NewRouter()
	router.Use(middleware.Recoverer, middleware.Timeout(requestTimeout), accessLog(log))
	config := huma.DefaultConfig(serviceName, "1.0.0")
	config.Info.Description = "Block analysis and lifetime report exports."
	config.DocsRenderer = huma.DocsRendererSwaggerUI
	config.CreateHooks = nil
	config.DefaultFormat = "application/json"
	api := humachi.New(router, config)

	huma.Register(api, huma.Operation{
		OperationID: "health",
		Method:      http.MethodGet,
		Path:        "/health",
		Summary:     "Liveness and readiness probe",
	}, func(context.Context, *struct{}) (*healthOutput, error) {
		output := &healthOutput{}
		output.Body.Status, output.Body.Domain = "ok", contract.Domain
		return output, nil
	})

	for _, operation := range svc.Registry.All() {
		registerOperation(api, svc, operation)
	}
	registerMCP(api, svc)
	router.Post("/operations/{name}", unknownOperation(svc))
	return router
}

func schemaOf(raw map[string]any) *huma.Schema {
	encoded, _ := json.Marshal(raw)
	schema := &huma.Schema{}
	if err := json.Unmarshal(encoded, schema); err != nil {
		return &huma.Schema{}
	}
	return schema
}

func registerOperation(api huma.API, svc *service.Service, operation *contract.Operation) {
	name := operation.Name
	huma.Register(api, huma.Operation{
		OperationID:  name,
		Method:       http.MethodPost,
		Path:         "/operations/" + name,
		Summary:      name,
		Description:  operation.Description,
		Tags:         []string{contract.Domain},
		MaxBodyBytes: maxBodyBytes,
		Responses: map[string]*huma.Response{
			"200": {
				Description: "Operation result.",
				Content:     map[string]*huma.MediaType{"application/json": {Schema: schemaOf(operation.ResultSchema)}},
			},
		},
	}, func(ctx context.Context, input *callInput) (*callOutput, error) {
		var arguments map[string]any
		if err := json.Unmarshal(input.RawBody, &arguments); err != nil || arguments == nil {
			return nil, apperr.Body()
		}
		result, err := svc.Call(ctx, name, arguments, input.caller())
		if err != nil {
			return nil, asStatusError(err)
		}
		return &callOutput{Body: result}, nil
	})
	documentBody(api, "/operations/"+name, schemaOf(operation.InputSchema))
}

func documentBody(api huma.API, path string, schema *huma.Schema) {
	api.OpenAPI().Paths[path].Post.RequestBody = &huma.RequestBody{
		Required: true,
		Content:  map[string]*huma.MediaType{"application/json": {Schema: schema}},
	}
}

func unknownOperation(svc *service.Service) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		caller := auth.FromHeaders(r.Header)
		var arguments map[string]any
		body, _ := io.ReadAll(http.MaxBytesReader(w, r.Body, maxBodyBytes))
		var failure error = apperr.Body()
		if json.Unmarshal(body, &arguments) == nil && arguments != nil {
			_, failure = svc.Call(r.Context(), chi.URLParam(r, "name"), arguments, caller)
		}
		typed := asStatusError(failure).(*apperr.Error)
		payload, _ := json.Marshal(typed)
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(typed.Status)
		_, _ = w.Write(payload)
	}
}

func asStatusError(err error) error {
	if _, ok := err.(*apperr.Error); ok {
		return err
	}
	return apperr.Internal(err.Error())
}

func accessLog(log *slog.Logger) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			started := time.Now()
			wrapped := middleware.NewWrapResponseWriter(w, r.ProtoMajor)
			next.ServeHTTP(wrapped, r)
			log.Info("request", "method", r.Method, "path", r.URL.Path, "status", wrapped.Status(), "duration_ms", time.Since(started).Milliseconds())
		})
	}
}
