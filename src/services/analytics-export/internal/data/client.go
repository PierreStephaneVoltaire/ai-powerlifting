package data

import (
	"context"
	"errors"

	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"

	analyticsv1 "powerlifting/analytics-export/gen/analytics"
	"powerlifting/analytics-export/internal/auth"
)

const maxMessageBytes = 128 * 1024 * 1024

var ErrNotFound = errors.New("block bundle not found")

type Client struct {
	conn   *grpc.ClientConn
	client analyticsv1.AnalyticsDataClient
}

func Dial(target string) (*Client, error) {
	conn, err := grpc.NewClient(target,
		grpc.WithTransportCredentials(insecure.NewCredentials()),
		grpc.WithDefaultCallOptions(grpc.MaxCallRecvMsgSize(maxMessageBytes)),
	)
	if err != nil {
		return nil, err
	}
	return &Client{conn: conn, client: analyticsv1.NewAnalyticsDataClient(conn)}, nil
}

func (c *Client) Close() error { return c.conn.Close() }

func (c *Client) BlockBundle(ctx context.Context, caller auth.Caller, blockKey string) (map[string]any, error) {
	ctx = metadata.AppendToOutgoingContext(ctx, "x-person-pk", caller.Person, "x-athlete-pk", caller.Athlete)
	report, err := c.client.GetBlockBundle(ctx, &analyticsv1.BlockRef{AthletePk: caller.Athlete, BlockKey: blockKey})
	if status.Code(err) == codes.NotFound {
		return nil, ErrNotFound
	}
	if err != nil {
		return nil, err
	}
	return report.GetBody().AsMap(), nil
}
