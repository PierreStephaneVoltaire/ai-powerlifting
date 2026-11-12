package httpapi

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"strings"

	"github.com/danielgtaylor/huma/v2"
	"github.com/danielgtaylor/huma/v2/adapters/humachi"
	"github.com/go-chi/chi/v5"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"

	"powerlifting/analytics-ai/internal/apperr"
	"powerlifting/analytics-ai/internal/auth"
	"powerlifting/analytics-ai/internal/contract"
	"powerlifting/analytics-ai/internal/pyjson"
	"powerlifting/analytics-ai/internal/service"
)

const maxBodyBytes = 32 << 20

type Headers struct {
	Person            string `header:"X-Person-Pk" doc:"Verified acting Person partition key."`
	Athlete           string `header:"X-Athlete-Pk" doc:"Athlete partition key whose data is addressed."`
	Source            string `header:"X-PL-Source-Principal" doc:"Calling service principal, set by the mesh."`
	JobID             string `header:"X-IF-Job-Id" doc:"Coach job id for a native execution callback."`
	TurnID            string `header:"X-IF-Turn-Id" doc:"Coach turn id; takes precedence over the job id."`
	Nested            string `header:"X-PL-Nested-Operation" doc:"Set to true when called from inside an active execution."`
	GenerationID      string `header:"X-IF-Generation-Id" doc:"Report generation the coach job belongs to."`
	GenerationAttempt string `header:"X-IF-Generation-Attempt" doc:"Attempt number of the report generation."`
}

func (h Headers) caller() auth.Caller {
	header := http.Header{}
	for name, value := range map[string]string{
		"X-Person-Pk": h.Person, "X-Athlete-Pk": h.Athlete, "X-PL-Source-Principal": h.Source, "X-IF-Job-Id": h.JobID, "X-IF-Turn-Id": h.TurnID,
		"X-PL-Nested-Operation": h.Nested, "X-IF-Generation-Id": h.GenerationID, "X-IF-Generation-Attempt": h.GenerationAttempt,
	} {
		header.Set(name, value)
	}
	return auth.FromHeaders(header)
}

type operationInput struct {
	Headers
	RawBody []byte `contentType:"application/json"`
}

type executionInput struct {
	Headers
	ID      string `path:"execution_id" doc:"Execution id returned by a needs_inference response."`
	RawBody []byte `contentType:"application/json"`
}

type generationInput struct {
	Headers
	ID string `path:"generation_id" doc:"Report generation id."`
}

type mcpInput struct {
	Headers
	RawBody []byte `contentType:"application/json"`
}

type output struct {
	Status int
	Body   any
}

type API struct {
	Service *service.Service
	Domain  string
}

func objectBody(raw []byte) (map[string]any, error) {
	value, err := pyjson.Decode(raw)
	if err != nil {
		return nil, apperr.Body()
	}
	object, isObject := value.(map[string]any)
	if !isObject {
		return nil, apperr.Body()
	}
	return object, nil
}

func asError(err error) error {
	var failure *apperr.Error
	if errors.As(err, &failure) {
		return failure
	}
	if st, ok := status.FromError(err); ok && st.Code() != codes.OK {
		switch st.Code() {
		case codes.NotFound:
			return apperr.NotFound("%s", st.Message())
		case codes.InvalidArgument:
			return apperr.Validation(st.Message())
		case codes.PermissionDenied, codes.Unauthenticated:
			return apperr.Forbidden(st.Message())
		case codes.Unavailable, codes.DeadlineExceeded:
			return &apperr.Error{Status: http.StatusServiceUnavailable, Code: "upstream_unavailable", Message: st.Message()}
		}
	}
	slog.Error("request failed", "error", err)
	return apperr.Internal(err.Error())
}

func (a *API) call(ctx context.Context, name string, raw []byte, caller auth.Caller) (output, error) {
	arguments, err := objectBody(raw)
	if err != nil {
		return output{}, err
	}
	response, err := a.Service.Call(ctx, name, arguments, caller)
	if err != nil {
		return output{}, asError(err)
	}
	return output{Status: response.Status, Body: response.Body}, nil
}

func New(api *API) http.Handler {
	router := chi.NewRouter()
	config := huma.DefaultConfig("Powerlifting "+api.Domain, "1.0.0")
	config.DocsPath = "/docs"
	config.DocsRenderer = huma.DocsRendererSwaggerUI
	config.OpenAPIPath = "/openapi"
	config.CreateHooks = nil
	documented := humachi.New(router, config)

	huma.Register(documented, huma.Operation{OperationID: "health", Method: http.MethodGet, Path: "/health", Summary: "Liveness probe", Tags: []string{"service"}},
		func(context.Context, *struct{}) (*output, error) {
			return &output{Status: http.StatusOK, Body: map[string]any{"status": "ok", "domain": api.Domain}}, nil
		})

	for _, operation := range api.Service.Registry.All() {
		registerOperation(documented, api, operation)
	}

	huma.Register(documented, huma.Operation{
		OperationID: "domain_resume", Method: http.MethodPost, Path: "/executions/{execution_id}", Tags: []string{"execution"}, SkipValidateBody: true,
		Summary:     "Answer a pending inference challenge and resume the execution",
		Description: "Body: {\"challenge_id\": string, \"content\": JSON answer validated against the challenge tool schema}. Omit challenge_id to only poll.",
	}, func(ctx context.Context, input *executionInput) (*output, error) {
		arguments, err := objectBody(input.RawBody)
		if err != nil {
			return nil, err
		}
		response, err := api.Service.Resume(ctx, input.ID, arguments, input.caller())
		if err != nil {
			return nil, asError(err)
		}
		return &output{Status: response.Status, Body: response.Body}, nil
	})

	huma.Register(documented, huma.Operation{
		OperationID: "generation_status", Method: http.MethodGet, Path: "/generations/{generation_id}", Tags: []string{"execution"},
		Summary: "Report generation status and result",
	}, func(ctx context.Context, input *generationInput) (*output, error) {
		body, err := api.Service.GenerationStatus(ctx, input.ID, input.caller())
		if err != nil {
			return nil, asError(err)
		}
		return &output{Status: http.StatusOK, Body: body}, nil
	})

	huma.Register(documented, huma.Operation{
		OperationID: "mcp", Method: http.MethodPost, Path: "/mcp", Tags: []string{"mcp"}, SkipValidateBody: true,
		Summary: "MCP JSON-RPC endpoint exposing the non-internal operations as tools",
	}, func(ctx context.Context, input *mcpInput) (*output, error) {
		status, body := api.mcp(ctx, input.RawBody, input.caller())
		return &output{Status: status, Body: body}, nil
	})

	patchDocumentation(documented, api.Service.Registry.All())
	router.Post("/operations/{name}", func(w http.ResponseWriter, r *http.Request) {
		raw, err := io.ReadAll(http.MaxBytesReader(w, r.Body, maxBodyBytes))
		if err != nil {
			write(w, http.StatusRequestEntityTooLarge, apperr.Validation("Request body too large"))
			return
		}
		result, err := api.call(r.Context(), chi.URLParam(r, "name"), raw, auth.FromHeaders(r.Header))
		if err != nil {
			var failure *apperr.Error
			errors.As(err, &failure)
			write(w, failure.Status, failure)
			return
		}
		write(w, result.Status, result.Body)
	})
	return router
}

func write(w http.ResponseWriter, status int, body any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(body)
}

func registerOperation(documented huma.API, api *API, operation *contract.Operation) {
	huma.Register(documented, huma.Operation{
		OperationID: operation.Name, Method: http.MethodPost, Path: "/operations/" + operation.Name, Tags: []string{"operations", operation.Execution}, SkipValidateBody: true,
		Summary: firstSentence(operation.Description), Description: operation.Description,
	}, func(ctx context.Context, input *operationInput) (*output, error) {
		result, err := api.call(ctx, operation.Name, input.RawBody, input.caller())
		if err != nil {
			return nil, err
		}
		return &result, nil
	})
}

func firstSentence(text string) string {
	if index := strings.Index(text, ". "); index > 0 {
		return text[:index+1]
	}
	return text
}
