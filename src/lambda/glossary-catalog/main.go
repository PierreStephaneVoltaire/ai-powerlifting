package main

import (
	"context"
	"log/slog"
	"os"
	"time"

	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-lambda-go/lambda"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
)

type handler struct {
	catalog *catalog
}

func (h *handler) handle(ctx context.Context, event events.DynamoDBEvent) (events.DynamoDBEventResponse, error) {
	failures := []events.DynamoDBBatchItemFailure{}
	for _, record := range event.Records {
		if record.EventName != string(events.DynamoDBOperationTypeInsert) && record.EventName != string(events.DynamoDBOperationTypeModify) {
			continue
		}
		if err := h.catalog.ensure(ctx, convertImage(record.Change.NewImage)); err != nil {
			slog.Error("catalog ensure failed", "sequence", record.Change.SequenceNumber, "error", err)
			failures = append(failures, events.DynamoDBBatchItemFailure{ItemIdentifier: record.Change.SequenceNumber})
		}
	}
	return events.DynamoDBEventResponse{BatchItemFailures: failures}, nil
}

func main() {
	table := os.Getenv("GLOSSARY_TABLE_NAME")
	if table == "" {
		slog.Error("GLOSSARY_TABLE_NAME is required")
		os.Exit(1)
	}
	cfg, err := config.LoadDefaultConfig(context.Background())
	if err != nil {
		slog.Error("load aws config", "error", err)
		os.Exit(1)
	}
	h := &handler{catalog: &catalog{client: dynamodb.NewFromConfig(cfg), table: table, now: time.Now}}
	lambda.Start(h.handle)
}
