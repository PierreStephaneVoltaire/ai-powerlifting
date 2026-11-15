package workflow

import (
	"context"
	"errors"

	dw "github.com/dapr/durabletask-go/workflow"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"

	"github.com/dapr/durabletask-go/api"
	"powerlifting/assistant/internal/activities"
)

type EngineStatus struct {
	Status string
	Error  string
}

type Engine struct {
	client *dw.Client
	conn   *grpc.ClientConn
}

type apiToken string

func (t apiToken) GetRequestMetadata(context.Context, ...string) (map[string]string, error) {
	return map[string]string{"dapr-api-token": string(t)}, nil
}

func (apiToken) RequireTransportSecurity() bool { return false }

func Connect(endpoint, token string) (*Engine, error) {
	options := []grpc.DialOption{grpc.WithTransportCredentials(insecure.NewCredentials())}
	if token != "" {
		options = append(options, grpc.WithPerRPCCredentials(apiToken(token)))
	}
	conn, err := grpc.NewClient(endpoint, options...)
	if err != nil {
		return nil, err
	}
	return &Engine{client: dw.NewClient(conn), conn: conn}, nil
}

func (e *Engine) Close() error {
	return e.conn.Close()
}

func (e *Engine) StartWorker(ctx context.Context, registry *dw.Registry) error {
	return e.client.StartWorker(ctx, registry)
}

func (e *Engine) Schedule(ctx context.Context, id string, input TurnInput) error {
	_, err := e.client.ScheduleWorkflow(ctx, NameConversationTurn, dw.WithInstanceID(id), dw.WithInput(input))
	return err
}

func (e *Engine) Status(ctx context.Context, id string) (EngineStatus, error) {
	metadata, err := e.client.FetchWorkflowMetadata(ctx, id)
	if err != nil {
		if errors.Is(err, api.ErrInstanceNotFound) {
			return EngineStatus{Status: "uncertain", Error: "workflow instance not found"}, nil
		}
		return EngineStatus{}, err
	}
	status := EngineStatus{}
	if metadata.FailureDetails != nil {
		status.Error = metadata.FailureDetails.ErrorMessage
	}
	switch metadata.RuntimeStatus {
	case dw.StatusPending:
		status.Status = "queued"
	case dw.StatusCompleted:
		status.Status = "succeeded"
	case dw.StatusFailed:
		status.Status = "failed"
	case dw.StatusTerminated, dw.StatusCanceled:
		status.Status = "cancelled"
	case dw.StatusStalled:
		status.Status = "uncertain"
	default:
		status.Status = "running"
	}
	return status, nil
}

func (e *Engine) Terminate(ctx context.Context, id string) error {
	return e.client.TerminateWorkflow(ctx, id, dw.WithRecursiveTerminate(true))
}

func (e *Engine) RaiseApproval(ctx context.Context, workflowID, proposalID string, event activities.ApprovalEvent) error {
	return e.client.RaiseEvent(ctx, workflowID, activities.ApprovalEventName(proposalID), dw.WithEventPayload(event))
}
