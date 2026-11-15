package main

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
)

type fakeClient struct {
	calls []*dynamodb.TransactWriteItemsInput
	err   error
}

func (f *fakeClient) TransactWriteItems(_ context.Context, in *dynamodb.TransactWriteItemsInput, _ ...func(*dynamodb.Options)) (*dynamodb.TransactWriteItemsOutput, error) {
	f.calls = append(f.calls, in)
	return &dynamodb.TransactWriteItemsOutput{}, f.err
}

func newCatalog(c transactor) *catalog {
	return &catalog{client: c, table: "t", now: func() time.Time { return time.Date(2026, 1, 2, 3, 4, 5, 0, time.UTC) }}
}

func s(v string) *types.AttributeValueMemberS { return &types.AttributeValueMemberS{Value: v} }

func customImage() map[string]types.AttributeValue {
	return map[string]types.AttributeValue{
		"pk":              s("ATHLETE#sir"),
		"sk":              s("EXERCISE#abc"),
		"name":            s("  Pause   Squat "),
		"custom":          &types.AttributeValueMemberBOOL{Value: true},
		"category":        s("squat"),
		"fatigue_profile": &types.AttributeValueMemberM{Value: map[string]types.AttributeValue{}},
		"e1rm_estimate":   s("200"),
		"video_url":       &types.AttributeValueMemberNULL{Value: true},
	}
}

func TestNameKey(t *testing.T) {
	if got := nameKey("  Pause \t Squat\n"); got != "pause squat" {
		t.Fatalf("got %q", got)
	}
}

func TestEnsureWritesCatalogAndNameKey(t *testing.T) {
	f := &fakeClient{}
	if err := newCatalog(f).ensure(context.Background(), customImage()); err != nil {
		t.Fatal(err)
	}
	if len(f.calls) != 1 || len(f.calls[0].TransactItems) != 2 {
		t.Fatalf("unexpected calls %+v", f.calls)
	}
	item := f.calls[0].TransactItems[0].Put.Item
	if item["pk"].(*types.AttributeValueMemberS).Value != "CATALOG" || item["sk"].(*types.AttributeValueMemberS).Value != "EXERCISE#abc" {
		t.Fatalf("bad keys %+v", item)
	}
	want := map[string]string{"id": "abc", "name_key": "pause squat", "generic_status": "pending", "generic_pending": "1", "created_by": "sir", "created_at": "2026-01-02T03:04:05Z", "updated_at": "2026-01-02T03:04:05Z", "category": "squat"}
	for k, v := range want {
		if got := item[k].(*types.AttributeValueMemberS).Value; got != v {
			t.Errorf("%s = %q want %q", k, got, v)
		}
	}
	for _, k := range []string{"fatigue_profile", "e1rm_estimate", "custom", "video_url"} {
		if _, ok := item[k]; ok {
			t.Errorf("%s must not be copied", k)
		}
	}
	nameItem := f.calls[0].TransactItems[1].Put.Item
	if nameItem["pk"].(*types.AttributeValueMemberS).Value != "CATALOG_NAME" || nameItem["sk"].(*types.AttributeValueMemberS).Value != "pause squat" || nameItem["id"].(*types.AttributeValueMemberS).Value != "abc" {
		t.Fatalf("bad name item %+v", nameItem)
	}
	for _, ti := range f.calls[0].TransactItems {
		if *ti.Put.ConditionExpression != "attribute_not_exists(pk)" {
			t.Fatal("missing condition")
		}
	}
}

func TestEnsureSkipsNonCustom(t *testing.T) {
	f := &fakeClient{}
	img := customImage()
	img["custom"] = &types.AttributeValueMemberBOOL{Value: false}
	if err := newCatalog(f).ensure(context.Background(), img); err != nil || len(f.calls) != 0 {
		t.Fatalf("err=%v calls=%d", err, len(f.calls))
	}
	img = customImage()
	img["pk"] = s("CATALOG")
	if err := newCatalog(f).ensure(context.Background(), img); err != nil || len(f.calls) != 0 {
		t.Fatalf("err=%v calls=%d", err, len(f.calls))
	}
}

func TestConflictIsNoOp(t *testing.T) {
	code := "ConditionalCheckFailed"
	f := &fakeClient{err: &types.TransactionCanceledException{CancellationReasons: []types.CancellationReason{{Code: &code}, {Code: nil}}}}
	if err := newCatalog(f).ensure(context.Background(), customImage()); err != nil {
		t.Fatalf("conflict should be no-op, got %v", err)
	}
}

func TestOtherErrorPropagates(t *testing.T) {
	f := &fakeClient{err: errors.New("boom")}
	if err := newCatalog(f).ensure(context.Background(), customImage()); err == nil {
		t.Fatal("expected error")
	}
}

func dynImage() map[string]events.DynamoDBAttributeValue {
	return map[string]events.DynamoDBAttributeValue{
		"pk":     events.NewStringAttribute("ATHLETE#sir"),
		"sk":     events.NewStringAttribute("EXERCISE#abc"),
		"name":   events.NewStringAttribute("Pause Squat"),
		"custom": events.NewBooleanAttribute(true),
	}
}

func TestHandlerReportsBatchFailures(t *testing.T) {
	f := &fakeClient{err: errors.New("boom")}
	h := &handler{catalog: newCatalog(f)}
	ev := events.DynamoDBEvent{Records: []events.DynamoDBEventRecord{
		{EventName: "INSERT", Change: events.DynamoDBStreamRecord{SequenceNumber: "1", NewImage: dynImage()}},
		{EventName: "REMOVE", Change: events.DynamoDBStreamRecord{SequenceNumber: "2", NewImage: dynImage()}},
	}}
	resp, err := h.handle(context.Background(), ev)
	if err != nil {
		t.Fatal(err)
	}
	if len(resp.BatchItemFailures) != 1 || resp.BatchItemFailures[0].ItemIdentifier != "1" {
		t.Fatalf("got %+v", resp.BatchItemFailures)
	}
}

func TestHandlerSuccess(t *testing.T) {
	f := &fakeClient{}
	h := &handler{catalog: newCatalog(f)}
	ev := events.DynamoDBEvent{Records: []events.DynamoDBEventRecord{
		{EventName: "MODIFY", Change: events.DynamoDBStreamRecord{SequenceNumber: "1", NewImage: dynImage()}},
	}}
	resp, err := h.handle(context.Background(), ev)
	if err != nil || len(resp.BatchItemFailures) != 0 || len(f.calls) != 1 {
		t.Fatalf("resp=%+v err=%v calls=%d", resp, err, len(f.calls))
	}
}
