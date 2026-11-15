package activities

import (
	"context"
	"encoding/json"
	"log/slog"
	"time"

	"github.com/dapr/durabletask-go/workflow"

	"powerlifting/assistant/internal/access"
	"powerlifting/assistant/internal/audit"
	"powerlifting/assistant/internal/config"
	"powerlifting/assistant/internal/llm"
	"powerlifting/assistant/internal/store"
	"powerlifting/assistant/internal/token"
	"powerlifting/assistant/internal/tools"
)

type Deps struct {
	Config config.Config
	Store  *store.Store
	Access *access.Client
	Audit  *audit.Recorder
	LLM    *llm.Client
	MCP    *tools.MCPClient
	Signer *token.Signer
	Log    *slog.Logger
	Slots  chan struct{}
	Now    func() time.Time
}

func (d *Deps) acquire(ctx context.Context) (func(), error) {
	select {
	case d.Slots <- struct{}{}:
		return func() { <-d.Slots }, nil
	case <-ctx.Done():
		return nil, ctx.Err()
	}
}

func (d *Deps) bearer(subject Subject) (token.Issued, error) {
	return d.Signer.Mint(token.Subject{
		PersonPK:       subject.Person,
		AthletePK:      subject.Athlete,
		ConversationID: subject.ConversationID,
		WorkflowID:     subject.WorkflowID,
		Scope:          subject.Scope,
	})
}

func wrap[I, O any](fn func(context.Context, I) (O, error)) workflow.Activity {
	return func(ctx workflow.ActivityContext) (any, error) {
		var input I
		if err := ctx.GetInput(&input); err != nil {
			return nil, err
		}
		return fn(ctx.Context(), input)
	}
}

func Register(registry *workflow.Registry, d *Deps) error {
	entries := map[string]workflow.Activity{
		NameResolveIdentity: wrap(d.ResolveIdentity),
		NameMintToken:       wrap(d.MintToken),
		NameGuard:           wrap(d.Guard),
		NameDecide:          wrap(d.Decide),
		NameRetrieve:        wrap(d.Retrieve),
		NameListTools:       wrap(d.ListTools),
		NameModelCall:       wrap(d.ModelCall),
		NameToolCall:        wrap(d.ToolCall),
		NamePropose:         wrap(d.Propose),
		NameExpireProposal:  wrap(d.ExpireProposal),
		NameCommit:          wrap(d.Commit),
		NameDeliver:         wrap(d.Deliver),
	}
	for name, activity := range entries {
		if err := registry.AddActivityN(name, activity); err != nil {
			return err
		}
	}
	return nil
}

func mustJSON(value any) json.RawMessage {
	raw, err := json.Marshal(value)
	if err != nil {
		return json.RawMessage("null")
	}
	return raw
}
