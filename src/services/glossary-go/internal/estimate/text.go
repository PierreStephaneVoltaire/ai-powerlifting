package estimate

import (
	"context"
	"errors"
	"strings"

	"powerlifting/glossary-go/internal/execution"
	"powerlifting/glossary-go/internal/exercise"
)

type Text struct{ Description, HowToPerform, WhyDoIt string }

func compact(value any, limit int) string {
	text, _ := value.(string)
	runes := []rune(strings.Join(strings.Fields(text), " "))
	if len(runes) > limit {
		runes = runes[:limit]
	}
	return strings.TrimRight(string(runes), " ")
}

func GenerateText(ctx context.Context, infer execution.Inferer, item exercise.Item, athlete Athlete) (Text, error) {
	data := struct {
		Exercise     exerciseView
		LiftProfiles []profileSummary
	}{view(item, ""), athlete.summaries()}
	args, err := ask(ctx, infer, render("glossary_text_system", nil), render("glossary_text_user", data), tool("generate_glossary_text"))
	if err != nil {
		return Text{}, err
	}
	generated := Text{Description: compact(args["description"], 900), HowToPerform: compact(args["how_to_perform"], 1200), WhyDoIt: compact(args["why_do_it"], 900)}
	if generated == (Text{}) {
		return Text{}, errors.New("glossary text generation returned empty content")
	}
	return generated, nil
}
