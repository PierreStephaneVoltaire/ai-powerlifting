package store

import (
	"errors"
	"strings"
)

var ErrBadConversationID = errors.New("conversation id is malformed")

type ConversationRef struct {
	ID      string
	Athlete string
	Kind    string
	Shared  bool
	Owner   string
	Scope   string
}

func ParseConversationID(id string) (ConversationRef, error) {
	parts := strings.Split(id, ":")
	if len(parts) < 4 || parts[0] != "powerlifting" || parts[1] == "" {
		return ConversationRef{}, ErrBadConversationID
	}
	ref := ConversationRef{ID: id, Athlete: parts[1], Kind: parts[2]}
	switch ref.Kind {
	case "discord":
		if len(parts) != 4 || parts[3] == "" {
			return ConversationRef{}, ErrBadConversationID
		}
		ref.Shared = true
		ref.Scope = parts[3]
	case "web":
		if len(parts) < 5 || parts[3] == "" || parts[4] == "" {
			return ConversationRef{}, ErrBadConversationID
		}
		ref.Owner = parts[3]
		ref.Scope = strings.Join(parts[4:], ":")
	default:
		return ConversationRef{}, ErrBadConversationID
	}
	return ref, nil
}
