package store

import (
	"errors"
	"testing"
)

func TestProposalStateMachine(t *testing.T) {
	valid := []struct {
		from  State
		event Event
		to    State
	}{
		{StatePending, EventApprove, StateApproved},
		{StatePending, EventReject, StateRejected},
		{StatePending, EventExpire, StateExpired},
		{StatePending, EventCancel, StateCancelled},
		{StateApproved, EventBeginCommit, StateCommitting},
		{StateCommitting, EventBeginCommit, StateCommitting},
		{StateCommitting, EventCommit, StateCommitted},
		{StateCommitting, EventStale, StateStale},
		{StateCommitting, EventFail, StateFailed},
	}
	for _, test := range valid {
		got, err := Next(test.from, test.event)
		if err != nil || got != test.to {
			t.Errorf("%s+%s: got %s %v", test.from, test.event, got, err)
		}
	}
	invalid := []struct {
		from  State
		event Event
	}{
		{StatePending, EventCommit},
		{StatePending, EventBeginCommit},
		{StateApproved, EventApprove},
		{StateApproved, EventReject},
		{StateRejected, EventApprove},
		{StateExpired, EventApprove},
		{StateCommitted, EventBeginCommit},
		{StateStale, EventCommit},
	}
	for _, test := range invalid {
		if _, err := Next(test.from, test.event); !errors.Is(err, ErrInvalidTransition) {
			t.Errorf("%s+%s allowed", test.from, test.event)
		}
	}
	for _, state := range []State{StateRejected, StateExpired, StateCancelled, StateCommitted, StateStale, StateFailed} {
		if !state.Terminal() {
			t.Errorf("%s should be terminal", state)
		}
	}
	if StatePending.Terminal() || StateApproved.Terminal() || StateCommitting.Terminal() {
		t.Error("non-terminal state marked terminal")
	}
}
