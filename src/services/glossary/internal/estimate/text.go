package estimate

import (
	"errors"
	"strings"
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

func parseText(raw any) (Text, error) {
	args, _ := raw.(map[string]any)
	generated := Text{Description: compact(args["description"], 900), HowToPerform: compact(args["how_to_perform"], 1200), WhyDoIt: compact(args["why_do_it"], 900)}
	if generated == (Text{}) {
		return Text{}, errors.New("text is empty")
	}
	return generated, nil
}
