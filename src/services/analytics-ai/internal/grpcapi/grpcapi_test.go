package grpcapi

import (
	"context"
	"net"
	"testing"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials/insecure"
	healthpb "google.golang.org/grpc/health/grpc_health_v1"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/reflection/grpc_reflection_v1"
	"google.golang.org/grpc/status"

	reportsv1 "powerlifting/analytics-ai/gen/reports"
)

func start(t *testing.T, allowed []string) *grpc.ClientConn {
	t.Helper()
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	server := New(&Server{Now: time.Now}, allowed)
	go func() { _ = server.Serve(listener) }()
	t.Cleanup(server.Stop)
	conn, err := grpc.NewClient(listener.Addr().String(), grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = conn.Close() })
	return conn
}

func call(conn *grpc.ClientConn, pairs ...string) error {
	ctx := context.Background()
	if len(pairs) > 0 {
		ctx = metadata.AppendToOutgoingContext(ctx, pairs...)
	}
	_, err := reportsv1.NewReportsClient(conn).Regenerate(ctx, &reportsv1.BlockRef{AthletePk: "athlete_1"})
	return err
}

func TestGuard(t *testing.T) {
	conn := start(t, []string{"pl-analytics"})
	allowed := "cluster.local/ns/pl/sa/pl-analytics"
	cases := []struct {
		name  string
		pairs []string
		code  codes.Code
	}{
		{"no metadata", nil, codes.Unauthenticated},
		{"person missing", []string{"x-athlete-pk", "athlete_1", "x-pl-source-principal", allowed}, codes.Unauthenticated},
		{"athlete missing", []string{"x-person-pk", "person_1", "x-pl-source-principal", allowed}, codes.Unauthenticated},
		{"source missing", []string{"x-person-pk", "person_1", "x-athlete-pk", "athlete_1"}, codes.Unauthenticated},
		{"source without account", []string{"x-person-pk", "person_1", "x-athlete-pk", "athlete_1", "x-pl-source-principal", "anonymous"}, codes.Unauthenticated},
		{"account not allowed", []string{"x-person-pk", "person_1", "x-athlete-pk", "athlete_1", "x-pl-source-principal", "cluster.local/ns/pl/sa/pl-analytics-export"}, codes.PermissionDenied},
		{"athlete mismatch passes the guard and is rejected by the handler", []string{"x-person-pk", "person_1", "x-athlete-pk", "athlete_2", "x-pl-source-principal", "spiffe://" + allowed}, codes.PermissionDenied},
		{"block key required once allowed", []string{"x-person-pk", "person_1", "x-athlete-pk", "athlete_1", "x-pl-source-principal", "spiffe://" + allowed}, codes.InvalidArgument},
	}
	for _, tc := range cases {
		if got := status.Code(call(conn, tc.pairs...)); got != tc.code {
			t.Errorf("%s: got %v want %v", tc.name, got, tc.code)
		}
	}
}

func TestHealthAndReflectionAreUnguarded(t *testing.T) {
	conn := start(t, []string{"pl-analytics"})
	health, err := healthpb.NewHealthClient(conn).Check(context.Background(), &healthpb.HealthCheckRequest{})
	if err != nil || health.Status != healthpb.HealthCheckResponse_SERVING {
		t.Fatalf("health: %v %v", health, err)
	}
	stream, err := grpc_reflection_v1.NewServerReflectionClient(conn).ServerReflectionInfo(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if err := stream.Send(&grpc_reflection_v1.ServerReflectionRequest{MessageRequest: &grpc_reflection_v1.ServerReflectionRequest_ListServices{ListServices: ""}}); err != nil {
		t.Fatal(err)
	}
	reply, err := stream.Recv()
	if err != nil {
		t.Fatal(err)
	}
	found := false
	for _, service := range reply.GetListServicesResponse().GetService() {
		found = found || service.GetName() == "powerlifting.analytics_ai.v1.Reports"
	}
	if !found {
		t.Fatalf("reflection must list the Reports service: %v", reply)
	}
}
