package fakedb

import (
	"testing"

	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
)

func s(v string) types.AttributeValue { return &types.AttributeValueMemberS{Value: v} }
func n(v string) types.AttributeValue { return &types.AttributeValueMemberN{Value: v} }

func TestConditionExpressions(t *testing.T) {
	item := attrs{"pk": s("a"), "state": s("approved"), "revision": n("2"), "ids": &types.AttributeValueMemberSS{Value: []string{"x", "y"}}}
	e := env{names: map[string]string{"#state": "state"}, values: map[string]types.AttributeValue{":ok": s("approved"), ":two": n("2.0"), ":x": s("x"), ":z": s("z"), ":p": s("ap")}}
	cases := map[string]bool{
		"attribute_exists(pk)":                                      true,
		"attribute_not_exists(missing)":                             true,
		"#state = :ok AND revision = :two":                          true,
		"#state <> :ok OR attribute_not_exists(pk)":                 false,
		"contains(ids, :x) AND NOT contains(ids, :z)":               true,
		"begins_with(#state, :p)":                                   true,
		"(revision = :two OR #state = :z) AND attribute_exists(pk)": true,
	}
	for expression, want := range cases {
		got, err := evalCondition(expression, e, item)
		if err != nil || got != want {
			t.Errorf("%s: got %v err %v", expression, got, err)
		}
	}
}

func TestUpdateExpressions(t *testing.T) {
	item := attrs{"pk": s("a"), "entries": &types.AttributeValueMemberL{Value: []types.AttributeValue{s("old")}}}
	e := env{names: map[string]string{"#v": "version"}, values: map[string]types.AttributeValue{
		":empty": &types.AttributeValueMemberL{}, ":entry": &types.AttributeValueMemberL{Value: []types.AttributeValue{s("new")}},
		":version": s("current"), ":ids": &types.AttributeValueMemberSS{Value: []string{"id1"}}, ":fallback": s("fb"),
	}}
	if err := applyUpdate("SET entries = list_append(if_not_exists(entries, :empty), :entry), #v = :version, other = if_not_exists(other, :fallback) ADD ids :ids", e, item); err != nil {
		t.Fatal(err)
	}
	if got := len(item["entries"].(*types.AttributeValueMemberL).Value); got != 2 {
		t.Fatalf("entries %d", got)
	}
	if item["version"].(*types.AttributeValueMemberS).Value != "current" || item["other"].(*types.AttributeValueMemberS).Value != "fb" {
		t.Fatalf("%v", item)
	}
	if ids := item["ids"].(*types.AttributeValueMemberSS).Value; len(ids) != 1 || ids[0] != "id1" {
		t.Fatalf("ids %v", ids)
	}
}
