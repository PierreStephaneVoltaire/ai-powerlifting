package execution

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"log/slog"
	"sync"
	"time"

	"powerlifting/analytics-ai/internal/apperr"
	"powerlifting/analytics-ai/internal/cache"
	"powerlifting/analytics-ai/internal/contract"
	"powerlifting/analytics-ai/internal/pyjson"
)

const (
	Instruction = "Use a native Specialist child to answer these messages. Return its structured result using domain_resume. Do not submit another IF job."

	StatusSucceeded      = "succeeded"
	StatusNeedsInference = "needs_inference"
	StatusRunning        = "running"

	timeoutMessage = "Native delegation response timed out; reconcile this operation before retrying"
	unavailable    = "Domain execution unavailable; do not replay mutations"
	staleChallenge = "Challenge is stale or already answered"
)

type Challenge struct {
	ID             string `json:"challenge_id"`
	Messages       []any  `json:"messages"`
	Tools          []any  `json:"tools"`
	ResponseFormat any    `json:"response_format"`
	Instruction    string `json:"instruction"`
}

type Meta struct {
	JobID             string
	Athlete           string
	Person            string
	Operation         string
	GenerationID      string
	GenerationAttempt int
}

type Outcome struct {
	Status      string
	Result      any
	ExecutionID string
	Challenge   *Challenge
}

type Inferer func(ctx context.Context, request cache.Request) (map[string]any, error)

type Run func(ctx context.Context, infer Inferer) (any, error)

type Finish func(ctx context.Context, meta Meta, result any, err error)

type Manager struct {
	Prompts    cache.Prompts
	Deadline   time.Duration
	PollWindow time.Duration

	mu         sync.Mutex
	executions map[string]*execution
}

type execution struct {
	id        string
	meta      Meta
	deadline  time.Time
	notify    chan struct{}
	done      chan struct{}
	mu        sync.Mutex
	challenge *Challenge
	answer    chan map[string]any
	fatal     string
	result    any
	err       error
}

func New(prompts cache.Prompts) *Manager {
	return &Manager{Prompts: prompts, Deadline: 900 * time.Second, PollWindow: 2 * time.Second, executions: map[string]*execution{}}
}

func newID() string {
	raw := make([]byte, 16)
	_, _ = rand.Read(raw)
	return hex.EncodeToString(raw)
}

func (m *Manager) purge() {
	now := time.Now()
	for id, candidate := range m.executions {
		select {
		case <-candidate.done:
			if now.After(candidate.deadline) {
				delete(m.executions, id)
			}
		default:
		}
	}
}

func (m *Manager) Start(ctx context.Context, meta Meta, run Run, finish Finish) (Outcome, error) {
	current := &execution{
		id:       newID(),
		meta:     meta,
		deadline: time.Now().Add(m.Deadline),
		notify:   make(chan struct{}, 1),
		done:     make(chan struct{}),
	}
	m.mu.Lock()
	m.purge()
	m.executions[current.id] = current
	m.mu.Unlock()
	runCtx, cancel := context.WithDeadline(context.WithoutCancel(ctx), current.deadline)
	go func() {
		defer cancel()
		result, err := run(runCtx, func(ctx context.Context, request cache.Request) (map[string]any, error) {
			return m.infer(ctx, current, request)
		})
		current.mu.Lock()
		fatal := current.fatal
		current.mu.Unlock()
		if fatal != "" {
			err = apperr.Uncertain(fatal)
		}
		finish(context.WithoutCancel(ctx), meta, result, err)
		current.mu.Lock()
		current.result, current.err = result, err
		current.mu.Unlock()
		close(current.done)
		current.signal()
	}()
	return m.poll(ctx, current)
}

func (e *execution) signal() {
	select {
	case e.notify <- struct{}{}:
	default:
	}
}

func (m *Manager) infer(ctx context.Context, current *execution, request cache.Request) (map[string]any, error) {
	started := time.Now()
	hash, _ := request.Hash()
	if response, hit := m.Prompts.Exact(ctx, current.meta.Athlete, current.meta.Operation, request); hit {
		m.log(current, "exact", hash, started)
		return response, nil
	}
	answers := make(chan map[string]any, 1)
	current.mu.Lock()
	current.answer = answers
	current.challenge = &Challenge{ID: newID(), Messages: request.Messages, Tools: request.Tools, ResponseFormat: request.ResponseFormat, Instruction: Instruction}
	current.mu.Unlock()
	current.signal()
	select {
	case response := <-answers:
		m.Prompts.Remember(ctx, current.meta.Athlete, current.meta.Operation, request, response)
		m.log(current, "none", hash, started)
		return response, nil
	case <-ctx.Done():
		current.mu.Lock()
		current.challenge, current.answer = nil, nil
		current.fatal = timeoutMessage
		current.mu.Unlock()
		return nil, errors.New(timeoutMessage)
	}
}

func (m *Manager) log(current *execution, layer, hash string, started time.Time) {
	slog.Info("ai_request", "operation", current.meta.Operation, "athlete", current.meta.Athlete, "person", current.meta.Person,
		"job_id", current.meta.JobID, "cache_layer", layer, "request_hash", hash, "latency_ms", time.Now().Sub(started).Milliseconds())
}

func (m *Manager) poll(ctx context.Context, current *execution) (Outcome, error) {
	timer := time.NewTimer(m.PollWindow)
	defer timer.Stop()
	for {
		select {
		case <-current.done:
			m.mu.Lock()
			delete(m.executions, current.id)
			m.mu.Unlock()
			if current.err != nil {
				return Outcome{}, current.err
			}
			return Outcome{Status: StatusSucceeded, Result: current.result}, nil
		default:
		}
		current.mu.Lock()
		challenge := current.challenge
		current.mu.Unlock()
		if challenge != nil {
			return Outcome{Status: StatusNeedsInference, ExecutionID: current.id, Challenge: challenge}, nil
		}
		select {
		case <-current.notify:
		case <-current.done:
		case <-timer.C:
			return Outcome{Status: StatusRunning, ExecutionID: current.id}, nil
		case <-ctx.Done():
			return Outcome{Status: StatusRunning, ExecutionID: current.id}, nil
		}
	}
}

func (m *Manager) find(id string) *execution {
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.executions[id]
}

func (m *Manager) Lookup(id string) (Meta, bool) {
	current := m.find(id)
	if current == nil {
		return Meta{}, false
	}
	return current.meta, true
}

func (m *Manager) Resume(ctx context.Context, id, jobID, athlete, challengeID string, content any) (Outcome, error) {
	current := m.find(id)
	if current == nil || current.meta.JobID != jobID || current.meta.Athlete != athlete {
		return Outcome{}, apperr.Uncertain(unavailable)
	}
	if challengeID != "" {
		if err := current.accept(challengeID, content); err != nil {
			return Outcome{}, err
		}
	}
	return m.poll(ctx, current)
}

func schemaOf(challenge *Challenge) map[string]any {
	if len(challenge.Tools) > 0 {
		tool, _ := challenge.Tools[0].(map[string]any)
		function, _ := tool["function"].(map[string]any)
		schema, _ := function["parameters"].(map[string]any)
		return schema
	}
	format, _ := challenge.ResponseFormat.(map[string]any)
	wrapper, _ := format["json_schema"].(map[string]any)
	schema, _ := wrapper["schema"].(map[string]any)
	return schema
}

func (e *execution) accept(challengeID string, content any) error {
	e.mu.Lock()
	defer e.mu.Unlock()
	challenge := e.challenge
	if challenge == nil || challenge.ID != challengeID {
		return apperr.Uncertain(staleChallenge)
	}
	text, isText := content.(string)
	if !isText {
		encoded, err := pyjson.Encode(content)
		if err != nil {
			return apperr.Validation(err.Error())
		}
		text = string(encoded)
	}
	parsed, err := pyjson.Decode([]byte(text))
	if err != nil {
		return apperr.Validation("Answer is not valid JSON: " + err.Error())
	}
	if schema := schemaOf(challenge); schema != nil {
		if err := contract.ValidateAgainst(schema, parsed); err != nil {
			return apperr.Validation(err.Error())
		}
	}
	message := map[string]any{"role": "assistant", "content": text}
	finish := "stop"
	if len(challenge.Tools) > 0 {
		tool, _ := challenge.Tools[0].(map[string]any)
		function, _ := tool["function"].(map[string]any)
		message["tool_calls"] = []any{map[string]any{"id": newID(), "type": "function", "function": map[string]any{"name": function["name"], "arguments": text}}}
		finish = "tool_calls"
	}
	e.challenge = nil
	e.answer <- map[string]any{"choices": []any{map[string]any{"message": message, "finish_reason": finish}}}
	return nil
}
