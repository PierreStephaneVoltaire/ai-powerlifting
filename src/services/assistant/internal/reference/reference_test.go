package reference

import (
	"context"
	"errors"
	"fmt"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/credentials"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"math"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"sync"
	"testing"
	"time"
)

func TestSplitPassagesBoundsAndOverlaps(t *testing.T) {
	text := strings.Repeat("αβγδ εζηθ ", 100)
	passages := splitPassages(text, 80, 12)
	if len(passages) < 2 {
		t.Fatalf("got %d passages", len(passages))
	}
	for _, passage := range passages {
		if len([]rune(passage)) > 80 {
			t.Fatalf("passage is too long: %d", len([]rune(passage)))
		}
	}
	if !strings.Contains(passages[1], strings.TrimSpace(passages[0])[len([]rune(passages[0]))-5:]) {
		t.Fatal("adjacent passages do not overlap")
	}
}

func TestValidateVectorRequiresFiniteExpectedDimensions(t *testing.T) {
	for _, test := range []struct {
		name    string
		vector  []float32
		wantErr bool
	}{
		{name: "valid", vector: []float32{0.25, 0.75}},
		{name: "empty", vector: nil, wantErr: true},
		{name: "wrong dimension", vector: []float32{1}, wantErr: true},
		{name: "nan", vector: []float32{float32(math.NaN()), 0}, wantErr: true},
		{name: "infinite", vector: []float32{float32(math.Inf(1)), 0}, wantErr: true},
	} {
		t.Run(test.name, func(t *testing.T) {
			err := validateVector(test.vector, 2)
			if (err != nil) != test.wantErr {
				t.Fatalf("validateVector() error = %v, wantErr %t", err, test.wantErr)
			}
		})
	}
}

func TestDatabaseIsolationAndConcurrentBootstrap(t *testing.T) {
	dsn := os.Getenv("REFERENCE_TEST_DATABASE_URL")
	if dsn == "" {
		t.Skip("REFERENCE_TEST_DATABASE_URL is not set")
	}
	ctx := context.Background()
	admin, err := pgx.Connect(ctx, dsn)
	if err != nil {
		t.Fatal(err)
	}
	defer admin.Close(ctx)
	name := fmt.Sprintf("reference_test_%d", time.Now().UnixNano())
	if _, err := admin.Exec(ctx, `CREATE DATABASE `+pgx.Identifier{name}.Sanitize()); err != nil {
		t.Fatal(err)
	}
	defer admin.Exec(ctx, `DROP DATABASE `+pgx.Identifier{name}.Sanitize())
	config, err := pgxpool.ParseConfig(dsn)
	if err != nil {
		t.Fatal(err)
	}
	config.ConnConfig.Database = name
	pool, err := pgxpool.NewWithConfig(ctx, config)
	if err != nil {
		t.Fatal(err)
	}
	defer pool.Close()
	if _, err := pool.Exec(ctx, `CREATE EXTENSION vector`); err != nil {
		t.Fatal(err)
	}
	store := &Store{config: Config{Pool: pool, EmbedDim: 2, Collections: []Collection{{Name: "rules", Prefix: "rules/", Scope: "federation:*"}}, Embed: func(context.Context, string) ([]float32, error) { return []float32{1, 0}, nil }}}
	var wg sync.WaitGroup
	errs := make(chan error, 4)
	for range 4 {
		wg.Add(1)
		go func() { defer wg.Done(); errs <- store.bootstrap(ctx) }()
	}
	wg.Wait()
	close(errs)
	for err := range errs {
		if err != nil {
			t.Fatal(err)
		}
	}
	_, err = pool.Exec(ctx, `INSERT INTO reference.documents (collection,source_key,version_id,scope,effective_date) VALUES ('rules','a','1','federation:a','2020-01-01'),('rules','b','1','federation:b','2020-01-01'),('rules','future','1','federation:a','2030-01-01'); INSERT INTO reference.passages (collection,source_key,version_id,scope,passage_no,text,page,effective_date,embedding) VALUES ('rules','a','1','federation:a',0,'creatine rule',1,'2020-01-01','[0,1]'),('rules','b','1','federation:b',0,'creatine rule',1,'2020-01-01','[1,0]'),('rules','future','1','federation:a',0,'creatine rule',1,'2030-01-01','[1,0]')`)
	if err != nil {
		t.Fatal(err)
	}
	got, err := store.Search(ctx, SearchRequest{Collection: "rules", Scope: "federation:a", Query: "creatine", EffectiveDate: "2025-01-01", Limit: 1})
	if err != nil || len(got) != 1 || got[0].SourceKey != "a" {
		t.Fatalf("search = %+v, %v", got, err)
	}
	if _, err := store.Search(ctx, SearchRequest{Collection: "rules", Scope: "federation:a", Query: "x", EffectiveDate: "invalid"}); err == nil {
		t.Fatal("invalid date accepted")
	}
}

func TestVersionListingUsesBothMarkers(t *testing.T) {
	var calls int
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		calls++
		w.Header().Set("Content-Type", "application/xml")
		if calls == 1 {
			fmt.Fprint(w, `<ListVersionsResult><IsTruncated>true</IsTruncated><NextKeyMarker>same.pdf</NextKeyMarker><NextVersionIdMarker>v2</NextVersionIdMarker><Version><Key>same.pdf</Key><VersionId>v3</VersionId><IsLatest>true</IsLatest></Version></ListVersionsResult>`)
			return
		}
		if r.URL.Query().Get("key-marker") != "same.pdf" || r.URL.Query().Get("version-id-marker") != "v2" {
			t.Errorf("wrong markers: %s", r.URL.RawQuery)
		}
		fmt.Fprint(w, `<ListVersionsResult><IsTruncated>false</IsTruncated><Version><Key>other.pdf</Key><VersionId>v1</VersionId><IsLatest>true</IsLatest></Version></ListVersionsResult>`)
	}))
	defer server.Close()
	client := s3.New(s3.Options{Region: "us-east-1", BaseEndpoint: aws.String(server.URL), UsePathStyle: true, Credentials: credentials.NewStaticCredentialsProvider("test", "test", "")})
	store := &Store{config: Config{S3: client, Bucket: "test"}}
	got, err := store.currentPDFs(context.Background(), Collection{Prefix: ""})
	if err != nil || calls != 2 || got["same.pdf"] != "v3" || got["other.pdf"] != "v1" {
		t.Fatalf("listing = %v, calls %d, error %v", got, calls, err)
	}
}

func TestRetryBootstrapRecoversAndHonorsCancellation(t *testing.T) {
	attempts := 0
	err := retryBootstrap(context.Background(), func(context.Context) error {
		attempts++
		if attempts < 3 {
			return errors.New("temporary")
		}
		return nil
	}, time.Millisecond)
	if err != nil || attempts != 3 {
		t.Fatalf("attempts=%d error=%v", attempts, err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	attempts = 0
	err = retryBootstrap(ctx, func(context.Context) error { attempts++; cancel(); return errors.New("temporary") }, time.Hour)
	if !errors.Is(err, context.Canceled) || attempts != 1 {
		t.Fatalf("attempts=%d error=%v", attempts, err)
	}
}
