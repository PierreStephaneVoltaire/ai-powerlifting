package activities

import (
	"context"
	"errors"
	"slices"

	"powerlifting/assistant/internal/llm"
	"powerlifting/assistant/internal/tools"
)

func (d *Deps) ModelCall(ctx context.Context, in ModelCallInput) (llm.ChatResponse, error) {
	release, err := d.acquire(ctx)
	if err != nil {
		return llm.ChatResponse{}, err
	}
	defer release()
	return d.LLM.Chat(ctx, llm.ChatRequest{Model: in.Model, Messages: in.Messages, Tools: in.Tools, MaxTokens: in.MaxTokens})
}

func (d *Deps) ListTools(ctx context.Context, in ListToolsInput) (ListToolsOutput, error) {
	if len(in.Subject.Scope) == 0 {
		return ListToolsOutput{}, nil
	}
	issued, err := d.bearer(in.Subject)
	if err != nil {
		return ListToolsOutput{}, err
	}
	listed, err := d.MCP.List(ctx, issued.Token)
	if err != nil {
		return ListToolsOutput{}, err
	}
	var allowed []tools.Tool
	for _, tool := range listed {
		if slices.Contains(in.Subject.Scope, tool.Name) {
			allowed = append(allowed, tool)
		}
	}
	return ListToolsOutput{Tools: allowed}, nil
}

func (d *Deps) ToolCall(ctx context.Context, in ToolCallInput) (ToolCallOutput, error) {
	subject := in.Subject
	deny := func(reason string) (ToolCallOutput, error) {
		_ = d.Audit.Tool(ctx, subject.Person, subject.Athlete, subject.ConversationID, subject.WorkflowID, "", in.Name, "deny", map[string]any{"reason": reason})
		return ToolCallOutput{Denied: true, IsError: true, Text: "tool not permitted: " + reason}, nil
	}
	if !slices.Contains(subject.Scope, in.Name) {
		return deny("outside the allowed scope")
	}
	if tools.IsMutating(in.Name) && !in.AllowMutation {
		return deny("writes require an approved proposal")
	}
	issued, err := d.bearer(subject)
	if err != nil {
		return ToolCallOutput{}, err
	}
	release, err := d.acquire(ctx)
	if err != nil {
		return ToolCallOutput{}, err
	}
	defer release()
	result, err := d.MCP.Call(ctx, issued.Token, in.Name, in.Arguments)
	if err != nil {
		_ = d.Audit.Tool(ctx, subject.Person, subject.Athlete, subject.ConversationID, subject.WorkflowID, issued.JTI, in.Name, "error", map[string]any{"error": err.Error()})
		return ToolCallOutput{}, err
	}
	decision := "ok"
	if result.IsError {
		decision = "tool_error"
	}
	if err := d.Audit.Tool(ctx, subject.Person, subject.Athlete, subject.ConversationID, subject.WorkflowID, issued.JTI, in.Name, decision, nil); err != nil {
		return ToolCallOutput{}, errors.Join(errors.New("audit write failed"), err)
	}
	return ToolCallOutput{Text: result.Text, IsError: result.IsError, JTI: issued.JTI}, nil
}
