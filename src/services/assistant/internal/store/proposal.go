package store

import (
	"errors"
	"fmt"
)

type State string

const (
	StatePending    State = "pending"
	StateApproved   State = "approved"
	StateRejected   State = "rejected"
	StateExpired    State = "expired"
	StateCancelled  State = "cancelled"
	StateCommitting State = "committing"
	StateCommitted  State = "committed"
	StateStale      State = "stale"
	StateFailed     State = "failed"
)

type Event string

const (
	EventApprove     Event = "approve"
	EventReject      Event = "reject"
	EventExpire      Event = "expire"
	EventCancel      Event = "cancel"
	EventBeginCommit Event = "begin_commit"
	EventCommit      Event = "commit"
	EventStale       Event = "stale"
	EventFail        Event = "fail"
)

var ErrInvalidTransition = errors.New("invalid proposal transition")

var transitions = map[State]map[Event]State{
	StatePending: {
		EventApprove: StateApproved,
		EventReject:  StateRejected,
		EventExpire:  StateExpired,
		EventCancel:  StateCancelled,
	},
	StateApproved: {
		EventBeginCommit: StateCommitting,
		EventCancel:      StateCancelled,
	},
	StateCommitting: {
		EventBeginCommit: StateCommitting,
		EventCommit:      StateCommitted,
		EventStale:       StateStale,
		EventFail:        StateFailed,
	},
}

func Next(state State, event Event) (State, error) {
	next, ok := transitions[state][event]
	if !ok {
		return state, fmt.Errorf("%w: %s on %s", ErrInvalidTransition, event, state)
	}
	return next, nil
}

func (s State) Terminal() bool {
	switch s {
	case StateRejected, StateExpired, StateCancelled, StateCommitted, StateStale, StateFailed:
		return true
	}
	return false
}
