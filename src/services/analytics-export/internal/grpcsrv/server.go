package grpcsrv

import (
	"context"
	"net"
	"strings"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/health"
	healthpb "google.golang.org/grpc/health/grpc_health_v1"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/reflection"
	"google.golang.org/grpc/status"

	exportv1 "powerlifting/analytics-export/gen/export"
	"powerlifting/analytics-export/internal/auth"
	"powerlifting/analytics-export/internal/render"
	"powerlifting/analytics-export/internal/store"
)

const maxMessageBytes = 16 * 1024 * 1024

type principal struct{ athlete, person string }

type principalKey struct{}

func first(md metadata.MD, name string) string {
	if values := md.Get(name); len(values) > 0 {
		return values[0]
	}
	return ""
}

func Guard(allowed []string) grpc.UnaryServerInterceptor {
	return func(ctx context.Context, request any, info *grpc.UnaryServerInfo, next grpc.UnaryHandler) (any, error) {
		if !strings.HasPrefix(info.FullMethod, "/"+exportv1.Exports_ServiceDesc.ServiceName+"/") {
			return next(ctx, request)
		}
		md, _ := metadata.FromIncomingContext(ctx)
		who := principal{athlete: first(md, "x-athlete-pk"), person: first(md, "x-person-pk")}
		if who.athlete == "" || who.person == "" {
			return nil, status.Error(codes.Unauthenticated, "x-athlete-pk and x-person-pk metadata are required")
		}
		account := auth.ServiceAccount(first(md, "x-pl-source-principal"))
		if account == "" {
			return nil, status.Error(codes.Unauthenticated, "x-pl-source-principal metadata is required")
		}
		for _, name := range allowed {
			if name == account {
				return next(context.WithValue(ctx, principalKey{}, who), request)
			}
		}
		return nil, status.Error(codes.PermissionDenied, "Calling service is not allowed")
	}
}

type Exports struct {
	exportv1.UnimplementedExportsServer
	Store store.Store
	Now   func() time.Time
}

func (e *Exports) SaveLifetimeReport(ctx context.Context, request *exportv1.LifetimeReport) (*exportv1.SaveResult, error) {
	who, _ := ctx.Value(principalKey{}).(principal)
	if request.GetAthlete() == "" || request.GetAthlete() != who.athlete {
		return nil, status.Error(codes.PermissionDenied, "athlete does not match x-athlete-pk")
	}
	report := render.Lifetime{
		Athlete:     request.GetAthlete(),
		GeneratedAt: request.GetGeneratedAt(),
		BlockKeys:   request.GetBlockKeys(),
		Report:      request.GetReport().AsMap(),
		Narrative:   request.GetNarrative().AsMap(),
	}
	workbook, err := report.Workbook()
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}
	files := []struct {
		extension, contentType string
		content                []byte
	}{
		{"md", render.MarkdownType, []byte(report.Markdown())},
		{"xlsx", render.XLSXType, workbook},
	}
	stamp := e.Now()
	keys := map[string]string{}
	for _, file := range files {
		stamped := store.StampedKey(request.GetAthlete(), stamp, file.extension)
		for _, key := range []string{stamped, store.LatestKey(request.GetAthlete(), file.extension)} {
			if err := e.Store.Put(ctx, key, file.contentType, file.content); err != nil {
				return nil, status.Error(codes.Unavailable, "store write failed: "+err.Error())
			}
		}
		keys[file.extension] = stamped
	}
	return &exportv1.SaveResult{MarkdownKey: keys["md"], XlsxKey: keys["xlsx"]}, nil
}

func New(allowed []string, exports *Exports) *grpc.Server {
	server := grpc.NewServer(
		grpc.UnaryInterceptor(Guard(allowed)),
		grpc.MaxRecvMsgSize(maxMessageBytes),
	)
	exportv1.RegisterExportsServer(server, exports)
	checks := health.NewServer()
	checks.SetServingStatus(exportv1.Exports_ServiceDesc.ServiceName, healthpb.HealthCheckResponse_SERVING)
	healthpb.RegisterHealthServer(server, checks)
	reflection.Register(server)
	return server
}

func Serve(server *grpc.Server, address string) error {
	listener, err := net.Listen("tcp", address)
	if err != nil {
		return err
	}
	return server.Serve(listener)
}
