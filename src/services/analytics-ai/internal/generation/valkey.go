package generation

import (
	"context"
	"errors"
	"time"

	"github.com/redis/go-redis/v9"
)

const swapScript = `
if redis.call('GET', KEYS[1]) ~= ARGV[1] then return 0 end
if tonumber(ARGV[3]) > 0 then redis.call('SET', KEYS[1], ARGV[2], 'PX', ARGV[3]) else redis.call('SET', KEYS[1], ARGV[2]) end
return 1`

type Valkey struct{ Client redis.Cmdable }

func (v Valkey) Get(ctx context.Context, key string) (string, bool, error) {
	value, err := v.Client.Get(ctx, key).Result()
	if errors.Is(err, redis.Nil) {
		return "", false, nil
	}
	return value, err == nil, err
}

func (v Valkey) SetNX(ctx context.Context, key, value string, ttl time.Duration) (bool, error) {
	return v.Client.SetNX(ctx, key, value, ttl).Result()
}

func (v Valkey) Swap(ctx context.Context, key, previous, next string, ttl time.Duration) (bool, error) {
	swapped, err := v.Client.Eval(ctx, swapScript, []string{key}, previous, next, ttl.Milliseconds()).Int()
	return swapped == 1, err
}
