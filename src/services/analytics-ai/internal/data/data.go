package data

import (
	"context"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/metadata"
	"google.golang.org/protobuf/types/known/structpb"

	analyticsv1 "powerlifting/analytics-ai/gen/analytics"
	exportv1 "powerlifting/analytics-ai/gen/export"
)

const maxMessageBytes = 128 * 1024 * 1024

type Principal struct {
	Person  string
	Athlete string
}

func (p Principal) Outgoing(ctx context.Context) context.Context {
	return metadata.AppendToOutgoingContext(ctx, "x-person-pk", p.Person, "x-athlete-pk", p.Athlete)
}

type Source interface {
	Blocks(ctx context.Context, p Principal) ([]map[string]any, error)
	Bundle(ctx context.Context, p Principal, blockKey string) (map[string]any, error)
	Compare(ctx context.Context, p Principal, blockKeys []string) (map[string]any, error)
	Lifetime(ctx context.Context, p Principal) (map[string]any, error)
	Correlation(ctx context.Context, p Principal, blockKey string) (*analyticsv1.CorrelationInputsReply, error)
	Snapshot(ctx context.Context, p Principal) (*analyticsv1.Snapshot, error)
}

type Exporter interface {
	SaveLifetimeReport(ctx context.Context, p Principal, report LifetimeReport) error
}

type LifetimeReport struct {
	GeneratedAt string
	BlockKeys   []string
	Report      map[string]any
	Narrative   map[string]any
}

func Dial(target string) (*grpc.ClientConn, error) {
	return grpc.NewClient(target,
		grpc.WithTransportCredentials(insecure.NewCredentials()),
		grpc.WithDefaultCallOptions(grpc.MaxCallRecvMsgSize(maxMessageBytes), grpc.MaxCallSendMsgSize(maxMessageBytes)),
	)
}

type Analytics struct {
	Client analyticsv1.AnalyticsDataClient
}

func (a Analytics) Blocks(ctx context.Context, p Principal) ([]map[string]any, error) {
	reply, err := a.Client.ListBlocks(p.Outgoing(ctx), &analyticsv1.AthleteRef{AthletePk: p.Athlete})
	if err != nil {
		return nil, err
	}
	blocks := make([]map[string]any, 0, len(reply.Blocks))
	for _, block := range reply.Blocks {
		blocks = append(blocks, block.AsMap())
	}
	return blocks, nil
}

func (a Analytics) Bundle(ctx context.Context, p Principal, blockKey string) (map[string]any, error) {
	reply, err := a.Client.GetBlockBundle(p.Outgoing(ctx), &analyticsv1.BlockRef{AthletePk: p.Athlete, BlockKey: blockKey})
	if err != nil {
		return nil, err
	}
	return reply.GetBody().AsMap(), nil
}

func (a Analytics) Compare(ctx context.Context, p Principal, blockKeys []string) (map[string]any, error) {
	reply, err := a.Client.Compare(p.Outgoing(ctx), &analyticsv1.BlockKeys{AthletePk: p.Athlete, BlockKeys: blockKeys})
	if err != nil {
		return nil, err
	}
	return reply.GetBody().AsMap(), nil
}

func (a Analytics) Lifetime(ctx context.Context, p Principal) (map[string]any, error) {
	reply, err := a.Client.Lifetime(p.Outgoing(ctx), &analyticsv1.AthleteRef{AthletePk: p.Athlete})
	if err != nil {
		return nil, err
	}
	return reply.GetBody().AsMap(), nil
}

func (a Analytics) Correlation(ctx context.Context, p Principal, blockKey string) (*analyticsv1.CorrelationInputsReply, error) {
	return a.Client.CorrelationInputs(p.Outgoing(ctx), &analyticsv1.BlockRef{AthletePk: p.Athlete, BlockKey: blockKey})
}

func (a Analytics) Snapshot(ctx context.Context, p Principal) (*analyticsv1.Snapshot, error) {
	return a.Client.GetSnapshot(p.Outgoing(ctx), &analyticsv1.AthleteRef{AthletePk: p.Athlete})
}

type Export struct{ Client exportv1.ExportsClient }

func (e Export) SaveLifetimeReport(ctx context.Context, p Principal, report LifetimeReport) error {
	body, err := structpb.NewStruct(report.Report)
	if err != nil {
		return err
	}
	narrative, err := structpb.NewStruct(report.Narrative)
	if err != nil {
		return err
	}
	_, err = e.Client.SaveLifetimeReport(p.Outgoing(ctx), &exportv1.LifetimeReport{
		Athlete:     p.Athlete,
		GeneratedAt: report.GeneratedAt,
		BlockKeys:   report.BlockKeys,
		Report:      body,
		Narrative:   narrative,
	})
	return err
}
