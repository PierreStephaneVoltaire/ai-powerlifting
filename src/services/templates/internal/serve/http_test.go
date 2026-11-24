package serve

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"testing"

	"powerlifting/templates/internal/auth"
	"powerlifting/templates/internal/cache"
	"powerlifting/templates/internal/contract"
	"powerlifting/templates/internal/execution"
	"powerlifting/templates/internal/library"
	"powerlifting/templates/internal/service"
)

type allowAccess struct{}

func (allowAccess) Fetch(_ context.Context, _ string, _ map[string]any, c auth.Caller) (map[string]any, error) {
	return map[string]any{"person_pk": c.Person}, nil
}

type fakeDomain struct{}
type fakeSources struct{}
type captureDomain struct{ request map[string]any }

func (d *captureDomain) Call(_ context.Context, domain, operation string, args map[string]any, _ auth.Caller) (map[string]any, error) {
	if domain != "program" || operation != "block_transition" {
		return nil, errors.New("unexpected operation")
	}
	d.request = args
	return map[string]any{"program": map[string]any{"sk": "program#v002", "meta": map[string]any{"version_label": "2.0"}}, "next_block_id": "next"}, nil
}

func (fakeSources) ProgramContext(context.Context, string) (map[string]any, error) {
	return map[string]any{"current_maxes": map[string]any{}}, nil
}
func (fakeSources) Program(context.Context, string, string) (map[string]any, error) {
	return map[string]any{"sk": "program#v001", "meta": map[string]any{}, "sessions": []any{}, "current_maxes": map[string]any{"squat": float64(200)}}, nil
}
func (fakeSources) Glossary(context.Context, string) ([]map[string]any, error) {
	return []map[string]any{}, nil
}

func (fakeDomain) Call(_ context.Context, domain, operation string, _ map[string]any, _ auth.Caller) (map[string]any, error) {
	if domain == "program" && operation == "block_transition" {
		return map[string]any{"program": map[string]any{"sk": "program#v002", "meta": map[string]any{"version_label": "2.0"}}, "next_block_id": "next"}, nil
	}
	if domain == "program" || domain == "glossary" {
		return nil, errors.New("additional read permission denied")
	}
	return map[string]any{"exercises": []any{}}, nil
}

func (fakeDomain) Value(context.Context, string, string, map[string]any, auth.Caller) (any, error) {
	return []any{}, nil
}

type noPromptCache struct{}

func (noPromptCache) Lookup(context.Context, string, string, cache.Request) (map[string]any, string, bool) {
	return nil, "", false
}
func (noPromptCache) Remember(context.Context, string, string, cache.Request, map[string]any) {}

type memory struct{ items map[string]map[string]any }

func (m *memory) Get(_ context.Context, pk, sk string) (map[string]any, error) {
	return m.items[pk+"/"+sk], nil
}
func (m *memory) Commit(_ context.Context, item map[string]any, remove bool, claim *library.ImportClaim, index map[string]any, revision string) error {
	current := m.items[index["pk"].(string)+"/template#index"]
	if current != nil && stringValueForTest(current["index_revision"]) != revision {
		return libraryConflictForTest()
	}
	key := item["pk"].(string) + "/" + item["sk"].(string)
	if remove {
		delete(m.items, key)
	} else {
		m.items[key] = copyForTest(item)
	}
	m.items[index["pk"].(string)+"/template#index"] = copyForTest(index)

	return nil
}
func stringValueForTest(v any) string { s, _ := v.(string); return s }
func copyForTest(item map[string]any) map[string]any {
	raw, _ := json.Marshal(item)
	var out map[string]any
	json.Unmarshal(raw, &out)
	return out
}
func libraryConflictForTest() error { return library.ErrConflict }
func TestCreateAndReadTemplate(t *testing.T) {
	registry, err := contract.Load()
	if err != nil {
		t.Fatal(err)
	}
	db := &memory{items: map[string]map[string]any{}}
	handler := Handler(&service.Service{Registry: registry, Access: allowAccess{}, Domain: fakeDomain{}, Sources: fakeSources{}, Library: library.Library{Backend: db}}, slog.New(slog.NewTextHandler(io.Discard, nil)))
	call := func(op, body string) *httptest.ResponseRecorder {
		r := httptest.NewRequest(http.MethodPost, "/operations/"+op, bytes.NewBufferString(body))
		r.Header.Set("Content-Type", "application/json")
		r.Header.Set("X-Person-Pk", "alice")
		r.Header.Set("X-Athlete-Pk", "athlete")
		w := httptest.NewRecorder()
		handler.ServeHTTP(w, r)
		return w
	}
	created := call("template_create_blank", `{"name":"Test"}`)
	if created.Code != http.StatusOK {
		t.Fatalf("create: %d %s", created.Code, created.Body.String())
	}
	var data map[string]any
	if err := json.Unmarshal(created.Body.Bytes(), &data); err != nil {
		t.Fatal(err)
	}
	payload, _ := json.Marshal(map[string]any{"sk": data["sk"]})
	got := call("template_get", string(payload))
	if got.Code != http.StatusOK {
		t.Fatalf("get: %d %s", got.Code, got.Body.String())
	}
	var template map[string]any
	if err := json.Unmarshal(got.Body.Bytes(), &template); err != nil {
		t.Fatal(err)
	}
	if template["is_owner"] != true {
		t.Fatalf("missing ownership: %#v", template)
	}
	fromBlock := call("template_create_from_block", `{"name":"From block"}`)
	if fromBlock.Code != http.StatusOK {
		t.Fatalf("create from block without extra read grants: %d %s", fromBlock.Code, fromBlock.Body.String())
	}
	preview := call("template_apply", string(payload))
	if preview.Code != http.StatusOK {
		t.Fatalf("preview: %d %s", preview.Code, preview.Body.String())
	}
	var result map[string]any
	if err := json.Unmarshal(preview.Body.Bytes(), &result); err != nil {
		t.Fatal(err)
	}
	if result["status"] != "ready" {
		t.Fatalf("preview result: %#v", result)
	}
	confirm := call("template_apply_confirm", string(payload))
	if confirm.Code != http.StatusOK {
		t.Fatalf("confirm: %d %s", confirm.Code, confirm.Body.String())
	}
	var applied map[string]any
	if err := json.Unmarshal(confirm.Body.Bytes(), &applied); err != nil {
		t.Fatal(err)
	}
	if applied["program_sk"] != "program#v002" || applied["block_id"] != "next" {
		t.Fatalf("confirm result: %#v", applied)
	}
}

func TestReportAndPatch(t *testing.T) {
	registry, err := contract.Load()
	if err != nil {
		t.Fatal(err)
	}
	db := &memory{items: map[string]map[string]any{"template_library/template#1": {"pk": "template_library", "sk": "template#1", "meta": map[string]any{"name": "Test", "author_pk": "alice", "published": false}, "sessions": []any{map[string]any{"week_number": 1, "day_of_week": "Monday", "day_index": 1, "exercises": []any{}}}}}}
	handler := Handler(&service.Service{Registry: registry, Access: allowAccess{}, Domain: fakeDomain{}, Sources: fakeSources{}, Library: library.Library{Backend: db}}, slog.New(slog.NewTextHandler(io.Discard, nil)))
	call := func(op, body string) *httptest.ResponseRecorder {
		request := httptest.NewRequest(http.MethodPost, "/operations/"+op, bytes.NewBufferString(body))
		request.Header.Set("Content-Type", "application/json")
		request.Header.Set("X-Person-Pk", "alice")
		request.Header.Set("X-Athlete-Pk", "athlete")
		response := httptest.NewRecorder()
		handler.ServeHTTP(response, request)
		return response
	}
	report := call("template_report", `{"sk":"template#1"}`)
	if report.Code != http.StatusOK {
		t.Fatalf("report: %d %s", report.Code, report.Body.String())
	}
	patch := call("template_patch", `{"sk":"template#1","operations":[{"op":"set_session_weekdays","weekdays":{"1":"Friday"}}],"apply":true}`)
	if patch.Code != http.StatusOK {
		t.Fatalf("patch: %d %s", patch.Code, patch.Body.String())
	}
	if db.items["template_library/template#1"]["sessions"].([]any)[0].(map[string]any)["day_of_week"] != "Friday" {
		t.Fatalf("patch was not saved: %#v", db.items)
	}
}

type claimCheck bool

func (c claimCheck) VerifyClaim(_ context.Context, claim library.ImportClaim) (bool, error) {
	return bool(c) && claim.Athlete == "athlete" && claim.ImportID == "import-1" && claim.ClaimID == "claim-1", nil
}

func TestImportCreationRequiresWorkloadAndActiveClaim(t *testing.T) {
	registry, err := contract.Load()
	if err != nil {
		t.Fatal(err)
	}
	db := &memory{items: map[string]map[string]any{}}
	svc := &service.Service{Registry: registry, Access: allowAccess{}, Claims: claimCheck(true), Library: library.Library{Backend: db}}
	handler := Handler(svc, slog.New(slog.NewTextHandler(io.Discard, nil)))
	call := func(source, claim string) *httptest.ResponseRecorder {
		body := map[string]any{"import_id": "import-1", "claim_id": claim, "template": map[string]any{"meta": map[string]any{"name": "Imported"}}}
		raw, _ := json.Marshal(body)
		request := httptest.NewRequest(http.MethodPost, "/operations/template_create_from_import", bytes.NewReader(raw))
		request.Header.Set("Content-Type", "application/json")
		request.Header.Set("X-Person-Pk", "alice")
		request.Header.Set("X-Athlete-Pk", "athlete")
		request.Header.Set("X-PL-Source-Principal", source)
		response := httptest.NewRecorder()
		handler.ServeHTTP(response, request)
		return response
	}
	if got := call("spiffe://cluster.local/ns/powerlifting/sa/powerlifting-app-backend", "claim-1"); got.Code != http.StatusForbidden {
		t.Fatalf("wrong workload: %d %s", got.Code, got.Body.String())
	}
	source := "spiffe://cluster.local/ns/powerlifting/sa/pl-imports"
	if got := call(source, "bad"); got.Code != http.StatusForbidden {
		t.Fatalf("invalid claim: %d %s", got.Code, got.Body.String())
	}
	first := call(source, "claim-1")
	if first.Code != http.StatusOK {
		t.Fatalf("first: %d %s", first.Code, first.Body.String())
	}
	second := call(source, "claim-1")
	if second.Code != http.StatusOK || first.Body.String() != second.Body.String() {
		t.Fatalf("replay: %d %s, first %s", second.Code, second.Body.String(), first.Body.String())
	}
}

func TestEvaluationChallengeAndResume(t *testing.T) {
	registry, err := contract.Load()
	if err != nil {
		t.Fatal(err)
	}
	db := &memory{items: map[string]map[string]any{"template_library/template#1": {"pk": "template_library", "sk": "template#1", "meta": map[string]any{"name": "Test", "author_pk": "alice", "published": false}, "sessions": []any{}}}}
	svc := &service.Service{Registry: registry, Access: allowAccess{}, Domain: fakeDomain{}, Sources: fakeSources{}, Executions: execution.New(noPromptCache{}), Library: library.Library{Backend: db}}
	handler := Handler(svc, slog.New(slog.NewTextHandler(io.Discard, nil)))
	request := func(path, body, person string) *httptest.ResponseRecorder {
		r := httptest.NewRequest(http.MethodPost, path, bytes.NewBufferString(body))
		r.Header.Set("Content-Type", "application/json")
		r.Header.Set("X-Person-Pk", person)
		r.Header.Set("X-Athlete-Pk", "athlete")
		r.Header.Set("X-If-Turn-Id", "turn")
		w := httptest.NewRecorder()
		handler.ServeHTTP(w, r)
		return w
	}
	initial := request("/operations/template_evaluate", `{"sk":"template#1","context":"meet"}`, "alice")
	if initial.Code != http.StatusOK {
		t.Fatalf("evaluate: %d %s", initial.Code, initial.Body.String())
	}
	var challenge map[string]any
	if err := json.Unmarshal(initial.Body.Bytes(), &challenge); err != nil {
		t.Fatal(err)
	}
	if challenge["status"] != "needs_inference" {
		t.Fatalf("challenge: %#v", challenge)
	}
	resumeBody, _ := json.Marshal(map[string]any{"challenge_id": challenge["challenge_id"], "content": map[string]any{"stance": "monitor", "summary": "ok", "strengths": []any{}, "weaknesses": []any{}, "suggestions": []any{}}})
	path := "/executions/" + challenge["execution_id"].(string)
	wrong := request(path, string(resumeBody), "mallory")
	if wrong.Code != http.StatusForbidden {
		t.Fatalf("foreign resume: %d %s", wrong.Code, wrong.Body.String())
	}
	done := request(path, string(resumeBody), "alice")
	if done.Code != http.StatusOK {
		t.Fatalf("resume: %d %s", done.Code, done.Body.String())
	}
	var result map[string]any
	if err := json.Unmarshal(done.Body.Bytes(), &result); err != nil {
		t.Fatal(err)
	}
	if result["status"] != "succeeded" || db.items["template_library/template#1"]["meta"].(map[string]any)["program_context"] != "meet" {
		t.Fatalf("result %#v, db %#v", result, db.items)
	}
}

func TestConfirmKeepsBackfilledMaxesFromJSON(t *testing.T) {
	registry, err := contract.Load()
	if err != nil {
		t.Fatal(err)
	}
	db := &memory{items: map[string]map[string]any{"template_library/template#1": {"pk": "template_library", "sk": "template#1", "meta": map[string]any{"author_pk": "alice", "published": false}, "sessions": []any{}, "phases": []any{}}}}
	domain := &captureDomain{}
	handler := Handler(&service.Service{Registry: registry, Access: allowAccess{}, Domain: domain, Sources: fakeSources{}, Library: library.Library{Backend: db}}, slog.New(slog.NewTextHandler(io.Discard, nil)))
	r := httptest.NewRequest(http.MethodPost, "/operations/template_apply_confirm", bytes.NewBufferString(`{"sk":"template#1","backfilled_maxes":{"bench":95.5}}`))
	r.Header.Set("Content-Type", "application/json")
	r.Header.Set("X-Person-Pk", "alice")
	r.Header.Set("X-Athlete-Pk", "athlete")
	w := httptest.NewRecorder()
	handler.ServeHTTP(w, r)
	if w.Code != http.StatusOK {
		t.Fatalf("confirm: %d %s", w.Code, w.Body.String())
	}
	maxes, _ := domain.request["start_maxes_kg"].(map[string]any)
	if maxes["bench"] != 95.5 {
		t.Fatalf("backfilled max missing: %#v", maxes)
	}
}
