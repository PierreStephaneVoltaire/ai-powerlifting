package grpcsrv

import (
	"context"
	"net"
	"strings"
	"testing"
	"time"

	"github.com/xuri/excelize/v2"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials/insecure"
	healthpb "google.golang.org/grpc/health/grpc_health_v1"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"
	"google.golang.org/grpc/test/bufconn"
	"google.golang.org/protobuf/types/known/structpb"

	exportv1 "powerlifting/analytics-export/gen/export"
	"powerlifting/analytics-export/internal/store"
)

func start(t *testing.T) (*grpc.ClientConn, *store.Memory) {
	t.Helper()
	objects := store.NewMemory()
	server := New([]string{"pl-analytics-ai"}, &Exports{Store: objects, Now: func() time.Time { return time.Date(2026, 1, 2, 3, 4, 5, 0, time.UTC) }})
	listener := bufconn.Listen(1 << 20)
	go func() { _ = server.Serve(listener) }()
	t.Cleanup(server.Stop)
	conn, err := grpc.NewClient("passthrough:///bufnet",
		grpc.WithContextDialer(func(context.Context, string) (net.Conn, error) { return listener.Dial() }),
		grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { conn.Close() })
	return conn, objects
}

func outgoing(pairs ...string) context.Context {
	return metadata.AppendToOutgoingContext(context.Background(), pairs...)
}

func request(t *testing.T) *exportv1.LifetimeReport {
	t.Helper()
	report, err := structpb.NewStruct(map[string]any{"block_count": 1, "data_limits": []any{"few blocks"}})
	if err != nil {
		t.Fatal(err)
	}
	narrative, _ := structpb.NewStruct(map[string]any{"summary": "steady"})
	return &exportv1.LifetimeReport{Athlete: "athlete_1", GeneratedAt: "2026-01-02T03:04:05Z", BlockKeys: []string{"b1"}, Report: report, Narrative: narrative}
}

func TestGuardRejectsBadCallers(t *testing.T) {
	conn, objects := start(t)
	client := exportv1.NewExportsClient(conn)
	cases := []struct {
		name string
		ctx  context.Context
		code codes.Code
	}{
		{"no metadata", context.Background(), codes.Unauthenticated},
		{"no person", outgoing("x-athlete-pk", "athlete_1", "x-pl-source-principal", "cluster.local/ns/pl/sa/pl-analytics-ai"), codes.Unauthenticated},
		{"no athlete", outgoing("x-person-pk", "p", "x-pl-source-principal", "cluster.local/ns/pl/sa/pl-analytics-ai"), codes.Unauthenticated},
		{"no principal", outgoing("x-person-pk", "p", "x-athlete-pk", "athlete_1"), codes.Unauthenticated},
		{"principal without account", outgoing("x-person-pk", "p", "x-athlete-pk", "athlete_1", "x-pl-source-principal", "cluster.local/ns/pl"), codes.Unauthenticated},
		{"other account", outgoing("x-person-pk", "p", "x-athlete-pk", "athlete_1", "x-pl-source-principal", "cluster.local/ns/pl/sa/pl-rankings"), codes.PermissionDenied},
		{"athlete mismatch", outgoing("x-person-pk", "p", "x-athlete-pk", "athlete_2", "x-pl-source-principal", "cluster.local/ns/pl/sa/pl-analytics-ai"), codes.PermissionDenied},
	}
	for _, c := range cases {
		if _, err := client.SaveLifetimeReport(c.ctx, request(t)); status.Code(err) != c.code {
			t.Errorf("%s: code %v, want %v (%v)", c.name, status.Code(err), c.code, err)
		}
	}
	if len(objects.Objects) != 0 {
		t.Fatalf("rejected calls wrote %d objects", len(objects.Objects))
	}
}

func TestSaveLifetimeReportWritesLatestAndStamped(t *testing.T) {
	conn, objects := start(t)
	ctx := outgoing("x-person-pk", "p", "x-athlete-pk", "athlete_1", "x-pl-source-principal", "spiffe://cluster.local/ns/pl/sa/pl-analytics-ai")
	result, err := exportv1.NewExportsClient(conn).SaveLifetimeReport(ctx, request(t))
	if err != nil {
		t.Fatal(err)
	}
	if result.GetMarkdownKey() != "lifetime/athlete_1/20260102T030405Z.md" || result.GetXlsxKey() != "lifetime/athlete_1/20260102T030405Z.xlsx" {
		t.Fatalf("keys %v", result)
	}
	for _, key := range []string{"lifetime/athlete_1/latest.md", "lifetime/athlete_1/latest.xlsx", result.GetMarkdownKey(), result.GetXlsxKey()} {
		if len(objects.Objects[key]) == 0 {
			t.Errorf("missing %s", key)
		}
	}
	if !strings.Contains(string(objects.Objects["lifetime/athlete_1/latest.md"]), "| Summary | steady |") {
		t.Fatalf("markdown %s", objects.Objects["lifetime/athlete_1/latest.md"])
	}
	file, err := excelize.OpenReader(strings.NewReader(string(objects.Objects["lifetime/athlete_1/latest.xlsx"])))
	if err != nil {
		t.Fatal(err)
	}
	defer file.Close()
	if value, _ := file.GetCellValue("Overview", "B2"); value != "athlete_1" {
		t.Fatalf("Overview!B2 = %q", value)
	}
}

func TestHealthIsOpen(t *testing.T) {
	conn, _ := start(t)
	response, err := healthpb.NewHealthClient(conn).Check(context.Background(), &healthpb.HealthCheckRequest{})
	if err != nil || response.GetStatus() != healthpb.HealthCheckResponse_SERVING {
		t.Fatalf("health %v %v", response, err)
	}
}
