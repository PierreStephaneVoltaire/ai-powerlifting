package workflow

import (
	"time"

	"github.com/dapr/durabletask-go/workflow"

	"powerlifting/assistant/internal/domainjobs"
)

const NameDomainJob = "DomainJob"

func (w *Workflows) DomainJob(ctx *workflow.WorkflowContext) (any, error) {
	var id string
	if err := ctx.GetInput(&id); err != nil {
		return nil, err
	}
	deadline := ctx.CurrentTimeUTC().Add(domainjobs.Deadline)
	kind := "dispatch"
	for sequence := 0; ; sequence++ {
		if !ctx.CurrentTimeUTC().Before(deadline) {
			kind = "expire"
		}
		if kind == "poll" {
			if err := ctx.CreateTimer(500 * time.Millisecond).Await(nil); err != nil {
				return nil, err
			}
		}
		step, err := call[domainjobs.StepOutput](ctx, domainjobs.ActivityName, domainjobs.StepInput{ID: id, Sequence: sequence, Kind: kind}, quickRetry)
		if err != nil {
			return nil, err
		}
		if step.Next == "" || domainjobs.Terminal(step.Status) {
			return step.Status, nil
		}
		kind = step.Next
	}
}
