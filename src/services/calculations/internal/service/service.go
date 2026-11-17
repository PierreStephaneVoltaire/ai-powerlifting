package service

import (
	"context"
	"encoding/json"
	"fmt"
	"math"
	"slices"
	"time"

	"powerlifting/calculations/internal/apperr"
	"powerlifting/calculations/internal/auth"
	"powerlifting/calculations/internal/calc"
	"powerlifting/calculations/internal/contract"
)

type Accessor interface {
	Fetch(context.Context, string, map[string]any, auth.Caller) (map[string]any, error)
}
type Service struct {
	Registry *contract.Registry
	Access   Accessor
	Now      func() time.Time
}

func New(registry *contract.Registry, access Accessor) *Service {
	return &Service{Registry: registry, Access: access, Now: time.Now}
}
func (s *Service) Call(ctx context.Context, name string, args map[string]any, caller auth.Caller) (any, error) {
	if caller.Generation != nil && caller.ActiveJob() == "" {
		return nil, apperr.GenerationWithoutTurn()
	}
	op, ok := s.Registry.Get(name)
	if !ok {
		return nil, apperr.UnknownOperation()
	}
	for key := range args {
		if slices.Contains([]string{"_person_pk", "_access", "_if_job_id"}, key) {
			return nil, apperr.Forbidden("Reserved authorization fields cannot be supplied")
		}
	}
	access, err := s.Access.Fetch(ctx, name, args, caller)
	if err != nil {
		return nil, err
	}
	if op.InternalOnly && !caller.IsBackend() {
		return nil, apperr.Forbidden("Operation is internal to the gateway")
	}
	scoped, err := auth.Scope(op, args, caller, access)
	if err != nil {
		return nil, err
	}
	if err = op.ValidateInput(scoped); err != nil {
		return nil, apperr.Validation(err.Error())
	}
	if caller.Nested && caller.ActiveJob() == "" {
		return nil, apperr.NestedWithoutExecution()
	}
	result, err := s.calculate(name, scoped)
	if err != nil {
		return nil, apperr.Validation(err.Error())
	}
	if err = op.ValidateResult(result); err != nil {
		return nil, apperr.InvalidResult()
	}
	if caller.Nested || caller.ActiveJob() == "" {
		return result, nil
	}
	return map[string]any{"status": "succeeded", "result": result}, nil
}
func (s *Service) calculate(name string, a map[string]any) (any, error) {
	n := func(k string) float64 {
		switch v := a[k].(type) {
		case float64:
			return v
		case json.Number:
			value, _ := v.Float64()
			return value
		}
		return 0
	}
	switch name {
	case "lb_to_kg":
		v := n("lb")
		return map[string]any{"lb": v, "kg": calc.Round(v/2.20462, 2)}, nil
	case "kg_to_lb":
		v := n("kg")
		return map[string]any{"kg": v, "lb": calc.Round(v*2.20462, 1)}, nil
	case "pct_of_max":
		max, pct := n("max_kg"), n("pct")
		raw := max * (pct / 100)
		return map[string]any{"max_kg": max, "pct": pct, "raw_kg": calc.Round(raw, 2), "rounded_2_5_kg": math.RoundToEven(raw/2.5) * 2.5, "lb": calc.Round(raw*2.20462, 1)}, nil
	case "ipf_weight_classes":
		sex := a["sex"].(string)
		classes := []any{59, 66, 74, 83, 93, 105, 120, "120+"}
		if sex == "F" {
			classes = []any{47, 52, 57, 63, 69, 76, 84, "84+"}
		}
		return map[string]any{"sex": sex, "classes_kg": classes, "operator_class_kg": nil}, nil
	case "calculate_dots":
		value, err := calc.Dots(n("total_kg"), n("bodyweight_kg"), a["sex"].(string))
		return map[string]any{"dots": value}, err
	case "estimate_1rm":
		var rpe *int
		if _, ok := a["rpe"]; ok {
			x := int(n("rpe"))
			rpe = &x
		}
		return calc.Estimate1RM(n("weight_kg"), int(n("reps")), rpe), nil
	case "days_until":
		target, err := time.Parse("2006-01-02", a["target_date"].(string))
		if err != nil {
			return nil, err
		}
		now := s.Now()
		today := time.Date(now.Year(), now.Month(), now.Day(), 0, 0, 0, 0, time.UTC)
		days := int((target.Unix() - today.Unix()) / 86400)
		label, ok := a["label"].(string)
		if !ok {
			label = "target"
		}
		var elapsed any
		if days < 0 {
			elapsed = -days
			days = 0
		}
		return map[string]any{"label": label, "target_date": a["target_date"], "today": today.Format("2006-01-02"), "days_remaining": days, "weeks_remaining": days / 7, "days_elapsed_since": elapsed, "is_past": elapsed != nil}, nil
	}
	return nil, fmt.Errorf("unknown calculation %s", name)
}
