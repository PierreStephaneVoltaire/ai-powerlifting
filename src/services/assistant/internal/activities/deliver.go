package activities

import (
	"context"
	"errors"
	"slices"
	"sort"
	"strings"

	"powerlifting/assistant/internal/access"
	"powerlifting/assistant/internal/llm"
	"powerlifting/assistant/internal/store"
	"powerlifting/assistant/internal/tools"
	"powerlifting/assistant/internal/visibility"
)

const summaryRunes = 200

func requiredPermissions(operations []string) []string {
	seen := map[string]bool{}
	for _, name := range operations {
		if permission := tools.Permission(name); permission != "" {
			seen[permission] = true
		}
	}
	permissions := make([]string, 0, len(seen))
	for permission := range seen {
		permissions = append(permissions, permission)
	}
	sort.Strings(permissions)
	return permissions
}

func summarize(reply string) string {
	flat := strings.Join(strings.Fields(reply), " ")
	runes := []rune(flat)
	if len(runes) <= summaryRunes {
		return flat
	}
	return string(runes[:summaryRunes]) + "..."
}

const withheldNotice = "This result contains information that not everyone in this conversation may view, so it was not posted here."

type Resolver interface {
	Resolve(ctx context.Context, person, athlete string) (access.Identity, error)
}

func participantsFor(ctx context.Context, resolver Resolver, athlete string, people []string) []visibility.Participant {
	participants := make([]visibility.Participant, 0, len(people))
	for _, person := range people {
		identity, err := resolver.Resolve(ctx, person, athlete)
		switch {
		case err == nil:
			participants = append(participants, visibility.Participant{Person: person, Permissions: identity.Permissions, Resolved: true})
		case errors.Is(err, access.ErrDenied):
			participants = append(participants, visibility.Participant{Person: person, Resolved: true})
		default:
			participants = append(participants, visibility.Participant{Person: person})
		}
	}
	return participants
}

func (d *Deps) sharedViewGate(ctx context.Context, in DeliverInput, required []string) (visibility.Result, bool, error) {
	ref, err := store.ParseConversationID(in.ConversationID)
	if err != nil || !ref.Shared || len(required) == 0 {
		return visibility.Result{Allowed: true}, false, nil
	}
	people, err := d.Store.Participants(ctx, in.ConversationID)
	if err != nil {
		return visibility.Result{}, true, err
	}
	if !slices.Contains(people, in.Person) {
		people = append(people, in.Person)
	}
	return visibility.Check(required, participantsFor(ctx, d.Access, in.Athlete, people)), true, nil
}

func (d *Deps) Deliver(ctx context.Context, in DeliverInput) (DeliverOutput, error) {
	permissions := visibility.Union(requiredPermissions(in.UsedOperations), in.ExtraPermissions)
	reply := in.Reply
	withheld := false
	if in.Status == "succeeded" && strings.TrimSpace(reply) != "" {
		result, gated, err := d.sharedViewGate(ctx, in, permissions)
		if err != nil {
			return DeliverOutput{}, err
		}
		if gated && !result.Allowed {
			withheld = true
			_ = d.Audit.Record(ctx, store.AuditEntry{
				Kind: "visibility", PersonPK: in.Person, AthletePK: in.Athlete, ConversationID: in.ConversationID, WorkflowID: in.TurnID, Decision: "withheld",
				Detail: map[string]any{"required_permissions": permissions, "lacking": result.Lacking},
			})
			_ = d.Audit.Orchestration(ctx, store.OrchestrationEvent{
				Kind: "visibility_withheld", PersonPK: in.Person, ConversationID: in.ConversationID, WorkflowID: in.TurnID, Outcome: "withheld",
				Detail: map[string]any{"required_permissions": permissions, "lacking": result.Lacking},
			})
			reply = withheldNotice
			permissions = nil
		}
	}
	if err := d.Store.CompleteTurn(ctx, store.Completion{
		TurnID: in.TurnID, Status: in.Status, Reply: reply, Summary: summarize(reply), Error: in.Error, RequiredPermissions: permissions,
	}); err != nil {
		return DeliverOutput{}, err
	}
	output := DeliverOutput{Reply: reply, Withheld: withheld}
	if in.Status != "succeeded" || withheld {
		return output, nil
	}
	meta := llm.Metadata{UserID: in.Person, ConversationID: in.ConversationID, WorkflowID: in.TurnID, TurnID: in.TurnID, Role: "embed"}
	for kind, content := range map[string]string{"request": in.Request, "reply": reply} {
		if strings.TrimSpace(content) == "" {
			continue
		}
		embedding, err := d.LLM.Embed(ctx, d.Config.EmbedModel, content, meta)
		if err != nil || len(embedding) != d.Config.EmbedDim {
			d.Log.Warn("embedding skipped", "turn_id", in.TurnID, "kind", kind, "error", err)
			continue
		}
		if err := d.Store.InsertEmbedding(ctx, in.TurnID, in.ConversationID, in.Athlete, kind, content, permissions, embedding); err != nil {
			return DeliverOutput{}, err
		}
	}
	return output, nil
}
