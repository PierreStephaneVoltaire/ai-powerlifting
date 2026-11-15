package service

import "context"

type AvatarSource interface {
	Avatar(ctx context.Context, userID string) string
}

type Analytics interface {
	EstimatedMaxes(ctx context.Context, person, athlete string) map[string]any
}

type AvatarStore interface {
	Put(ctx context.Context, key, contentType string, body []byte, metadata map[string]string) error
	Delete(ctx context.Context, key string) error
}
