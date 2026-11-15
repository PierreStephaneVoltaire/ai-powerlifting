package activities

import (
	"context"
	"errors"
	"time"

	"powerlifting/assistant/internal/access"
	"powerlifting/assistant/internal/tools"
)

func (d *Deps) ResolveIdentity(ctx context.Context, in ResolveInput) (ResolveOutput, error) {
	identity, err := d.Access.Resolve(ctx, in.Person, in.Athlete)
	switch {
	case errors.Is(err, access.ErrDenied):
		_ = d.Audit.Access(ctx, in.Person, in.Athlete, in.ConversationID, in.WorkflowID, "deny", "no permissions or revoked")
		return ResolveOutput{Reason: "no active access to this Athlete"}, nil
	case err != nil:
		return ResolveOutput{}, err
	}
	if err := d.Audit.Access(ctx, in.Person, in.Athlete, in.ConversationID, in.WorkflowID, "allow", ""); err != nil {
		return ResolveOutput{}, err
	}
	if in.TurnID != "" {
		if err := d.Store.SetTurnStatus(ctx, in.TurnID, "running"); err != nil {
			return ResolveOutput{}, err
		}
	}
	return ResolveOutput{Allowed: true, Identity: identity}, nil
}

func (d *Deps) MintToken(ctx context.Context, in MintInput) (MintOutput, error) {
	surface, ok := tools.LookupSurface(in.Surface)
	if !ok {
		return MintOutput{}, errors.New("unknown surface")
	}
	scope := tools.Scope(surface, in.Identity.Permissions)
	subject := Subject{Person: in.Identity.Person, Athlete: in.Identity.Athlete, ConversationID: in.ConversationID, WorkflowID: in.WorkflowID, Scope: scope}
	if len(scope) == 0 {
		return MintOutput{Subject: subject}, nil
	}
	issued, err := d.bearer(subject)
	if err != nil {
		return MintOutput{}, err
	}
	if err := d.Audit.Tool(ctx, in.Identity.Person, in.Identity.Athlete, in.ConversationID, in.WorkflowID, issued.JTI, "", "token_scope", map[string]any{"surface": in.Surface, "scope": scope}); err != nil {
		return MintOutput{}, err
	}
	return MintOutput{Subject: subject, ExpiresAt: issued.ExpiresAt.Truncate(time.Second)}, nil
}
