package store

import (
	"context"
	"errors"
	"sort"
	"strings"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/feature/dynamodb/attributevalue"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
)

func (d Repository) query(ctx context.Context, table, partition, prefix string) ([]map[string]any, error) {
	items := []map[string]any{}
	var cursor map[string]types.AttributeValue
	for {
		input := &dynamodb.QueryInput{TableName: aws.String(table), KeyConditionExpression: aws.String("pk = :pk AND begins_with(sk, :prefix)"), ExpressionAttributeValues: map[string]types.AttributeValue{":pk": &types.AttributeValueMemberS{Value: partition}, ":prefix": &types.AttributeValueMemberS{Value: prefix}}, ExclusiveStartKey: cursor}
		page, err := d.Client.Query(ctx, input)
		if err != nil {
			return nil, err
		}
		for _, raw := range page.Items {
			var item map[string]any
			if err = attributevalue.UnmarshalMap(raw, &item); err != nil {
				return nil, err
			}
			items = append(items, item)
		}
		cursor = page.LastEvaluatedKey
		if len(cursor) == 0 {
			return items, nil
		}
	}
}

func (d Repository) get(ctx context.Context, table, partition, sortKey string) (map[string]any, error) {
	result, err := d.Client.GetItem(ctx, &dynamodb.GetItemInput{TableName: aws.String(table), Key: key(partition, sortKey), ConsistentRead: aws.Bool(true)})
	if err != nil {
		return nil, err
	}
	if len(result.Item) == 0 {
		return nil, nil
	}
	var item map[string]any
	if err = attributevalue.UnmarshalMap(result.Item, &item); err != nil {
		return nil, err
	}
	return item, nil
}

func (d Repository) program(ctx context.Context, athlete string) (string, map[string]any, error) {
	pointer, err := d.get(ctx, d.HealthTable, athlete, "program#current")
	if err != nil {
		return "", nil, err
	}
	selected, _ := pointer["ref_sk"].(string)
	if selected == "" {
		return "", nil, errors.New("program not found")
	}
	program, err := d.get(ctx, d.HealthTable, athlete, selected)
	if err != nil {
		return "", nil, err
	}
	if program == nil {
		return "", nil, errors.New("program not found")
	}
	return selected, program, nil
}

func (d Repository) ProgramContext(ctx context.Context, athlete string) (map[string]any, error) {
	_, program, err := d.program(ctx, athlete)
	if err != nil {
		return nil, err
	}
	return map[string]any{"current_maxes": program["current_maxes"], "lift_profiles": program["lift_profiles"]}, nil
}

func (d Repository) Program(ctx context.Context, athlete string) (map[string]any, error) {
	sk, program, err := d.program(ctx, athlete)
	if err != nil {
		return nil, err
	}
	sessions, err := d.query(ctx, d.SessionsTable, athlete, "session#"+sk+"#")
	if err != nil {
		return nil, err
	}
	sort.SliceStable(sessions, func(i, j int) bool {
		leftDate, _ := sessions[i]["date"].(string)
		rightDate, _ := sessions[j]["date"].(string)
		if leftDate != rightDate {
			return leftDate < rightDate
		}
		for _, key := range []string{"same_day_ordinal", "source_index"} {
			left, _ := sessions[i][key].(float64)
			right, _ := sessions[j][key].(float64)
			if left != right {
				return left < right
			}
		}
		left, _ := sessions[i]["sk"].(string)
		right, _ := sessions[j]["sk"].(string)
		return left < right
	})
	result := make([]any, 0, len(sessions))
	for _, session := range sessions {
		if _, exists := session["id"]; !exists {
			session["id"] = session["session_id"]
		}
		for _, key := range []string{"pk", "sk", "entity_type", "source_pk", "source_table", "program_sk", "program_version", "program_version_number", "source_index", "same_day_ordinal", "phase_ref", "session_id"} {
			delete(session, key)
		}
		result = append(result, session)
	}
	delete(program, "pk")
	program["sk"] = sk
	program["sessions"] = result
	return program, nil
}

var definitionFields = []string{"name", "category", "fatigue_category", "equipment", "video_url", "lift_transfer", "description", "how_to_perform", "why_do_it", "primary_muscles", "secondary_muscles", "tertiary_muscles"}
var personalFields = []string{"fatigue_profile", "fatigue_profile_source", "fatigue_profile_reasoning", "e1rm_estimate", "archived"}

func mergeExercise(catalog, overlay map[string]any, id string) map[string]any {
	result := map[string]any{}
	for _, field := range definitionFields {
		for _, source := range []map[string]any{catalog, overlay} {
			if value, ok := source[field]; ok {
				result[field] = value
			}
		}
	}
	for _, field := range personalFields {
		if value, ok := overlay[field]; ok {
			result[field] = value
		}
	}
	identifier := overlay["id"]
	if identifier == nil {
		identifier = catalog["id"]
	}
	if identifier == nil {
		identifier = id
	}
	result["id"] = identifier
	if value, ok := overlay["custom"]; ok {
		result["custom"] = value
	}
	if catalog != nil {
		if value, ok := catalog["generic_status"]; ok {
			result["generic_status"] = value
		}
		if generic, ok := catalog["fatigue_profile"]; ok {
			result["generic_fatigue_profile"] = generic
			if _, personal := overlay["fatigue_profile"]; !personal {
				result["fatigue_profile"] = generic
				for _, field := range []string{"fatigue_profile_source", "fatigue_profile_reasoning"} {
					if value, ok := catalog[field]; ok {
						result[field] = value
					}
				}
			}
		}
	}
	_, result["fatigue_profile_personalized"] = overlay["fatigue_profile"]
	return result
}

func (d Repository) Glossary(ctx context.Context, athlete string) ([]map[string]any, error) {
	catalog, err := d.query(ctx, d.GlossaryTable, "CATALOG", "EXERCISE#")
	if err != nil {
		return nil, err
	}
	overlays, err := d.query(ctx, d.GlossaryTable, "ATHLETE#"+athlete, "EXERCISE#")
	if err != nil {
		return nil, err
	}
	index := func(items []map[string]any) map[string]map[string]any {
		result := map[string]map[string]any{}
		for _, item := range items {
			sk, _ := item["sk"].(string)
			if strings.HasPrefix(sk, "EXERCISE#") {
				result[strings.TrimPrefix(sk, "EXERCISE#")] = item
			}
		}
		return result
	}
	byCatalog, byOverlay := index(catalog), index(overlays)
	ids := map[string]bool{}
	for id := range byCatalog {
		ids[id] = true
	}
	for id := range byOverlay {
		ids[id] = true
	}
	sorted := make([]string, 0, len(ids))
	for id := range ids {
		sorted = append(sorted, id)
	}
	sort.Strings(sorted)
	result := []map[string]any{}
	for _, id := range sorted {
		if byOverlay[id]["hidden"] == true {
			continue
		}
		result = append(result, mergeExercise(byCatalog[id], byOverlay[id], id))
	}
	sort.SliceStable(result, func(i, j int) bool {
		a, _ := result[i]["name"].(string)
		b, _ := result[j]["name"].(string)
		return strings.ToLower(a) < strings.ToLower(b)
	})
	return result, nil
}
