package grpcapi

import (
	"context"
	"slices"
	"strings"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/health"
	healthpb "google.golang.org/grpc/health/grpc_health_v1"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/reflection"
	"google.golang.org/grpc/status"

	reportsv1 "powerlifting/analytics-ai/gen/reports"
	"powerlifting/analytics-ai/internal/auth"
	"powerlifting/analytics-ai/internal/service"
)

const guarded = "/powerlifting.analytics_ai.v1.Reports/"

func first(md metadata.MD, name string) string {
	if values := md.Get(name); len(values) > 0 {
		return values[0]
	}
	return ""
}

func callerOf(ctx context.Context) auth.Caller {
	md, _ := metadata.FromIncomingContext(ctx)
	return auth.Caller{Person: first(md, "x-person-pk"), Athlete: first(md, "x-athlete-pk"), Source: first(md, "x-pl-source-principal")}
}

func Guard(allowed []string) grpc.UnaryServerInterceptor {
	return func(ctx context.Context, request any, info *grpc.UnaryServerInfo, next grpc.UnaryHandler) (any, error) {
		if !strings.HasPrefix(info.FullMethod, guarded) {
			return next(ctx, request)
		}
		caller := callerOf(ctx)
		if caller.Athlete == "" || caller.Person == "" {
			return nil, status.Error(codes.Unauthenticated, "x-athlete-pk and x-person-pk metadata are required")
		}
		account := auth.ServiceAccount(caller.Source)
		if account == "" {
			return nil, status.Error(codes.Unauthenticated, "x-pl-source-principal metadata is required")
		}
		if !slices.Contains(allowed, account) {
			return nil, status.Error(codes.PermissionDenied, "Calling service is not allowed")
		}
		return next(ctx, request)
	}
}

type Server struct {
	reportsv1.UnimplementedReportsServer
	Service *service.Service
	Now     func() time.Time
}

func (s *Server) Regenerate(ctx context.Context, ref *reportsv1.BlockRef) (*reportsv1.RegenerateResult, error) {
	caller := callerOf(ctx)
	if ref.AthletePk == "" || ref.AthletePk != caller.Athlete {
		return nil, status.Error(codes.PermissionDenied, "athlete_pk does not match x-athlete-pk")
	}
	if ref.BlockKey == "" {
		return nil, status.Error(codes.InvalidArgument, "block_key is required")
	}
	correlation, evaluation := s.Service.Regenerate(ctx, caller, ref.BlockKey)
	return &reportsv1.RegenerateResult{
		CorrelationRegenerated: correlation,
		EvaluationRegenerated:  evaluation,
		GeneratedAt:            s.Now().UTC().Format(time.RFC3339),
	}, nil
}

func New(server *Server, allowed []string) *grpc.Server {
	grpcServer := grpc.NewServer(grpc.UnaryInterceptor(Guard(allowed)))
	reportsv1.RegisterReportsServer(grpcServer, server)
	healthServer := health.NewServer()
	healthServer.SetServingStatus("", healthpb.HealthCheckResponse_SERVING)
	healthServer.SetServingStatus(strings.Trim(guarded, "/"), healthpb.HealthCheckResponse_SERVING)
	healthpb.RegisterHealthServer(grpcServer, healthServer)
	reflection.Register(grpcServer)
	return grpcServer
}
