package estimate

import (
	"context"
	"encoding/json"
	"fmt"
	"maps"
	"slices"

	"powerlifting/glossary/internal/execution"
	"powerlifting/glossary/internal/exercise"
)

const (
	AspectFatigue      = "fatigue"
	AspectE1RM         = "e1rm"
	AspectMuscles      = "muscles"
	AspectLiftTransfer = "lift_transfer"
	AspectText         = "text"
)

type Subject struct {
	ID      string
	Item    exercise.Item
	Aspects []string
	History []map[string]any
}

type Request struct {
	Subjects     []Subject
	Athlete      *Athlete
	CurrentMaxes map[string]any
}

type Estimate struct {
	Fatigue      *Fatigue
	E1RM         *E1RM
	Muscles      *Muscles
	LiftTransfer exercise.Item
	Text         *Text
}

type subjectView struct {
	ID       string
	Exercise exerciseView
	Aspects  []string
	History  string
}

type promptData struct {
	Fatigue, E1RM, Muscles, LiftTransfer, Text bool
	AthleteLines                               []string
	Subjects                                   []subjectView
}

func (r Request) wants(aspect string) bool {
	return slices.ContainsFunc(r.Subjects, func(subject Subject) bool { return slices.Contains(subject.Aspects, aspect) })
}

func (r Request) prompt() (promptData, error) {
	data := promptData{
		Fatigue: r.wants(AspectFatigue), E1RM: r.wants(AspectE1RM), Muscles: r.wants(AspectMuscles),
		LiftTransfer: r.wants(AspectLiftTransfer), Text: r.wants(AspectText),
	}
	if r.Athlete != nil {
		data.AthleteLines = r.Athlete.lines()
		if data.E1RM && len(r.CurrentMaxes) > 0 {
			maxes, err := json.Marshal(r.CurrentMaxes)
			if err != nil {
				return data, err
			}
			data.AthleteLines = append(data.AthleteLines, "", "Current competition maxes (kg): "+string(maxes))
		}
	}
	for _, subject := range r.Subjects {
		current := subjectView{ID: subject.ID, Aspects: subject.Aspects}
		prefix := ""
		if slices.Contains(subject.Aspects, AspectMuscles) {
			prefix = "Existing "
		}
		current.Exercise = view(subject.Item, prefix)
		if len(subject.History) > 0 {
			history, err := json.Marshal(subject.History)
			if err != nil {
				return data, err
			}
			current.History = string(history)
		}
		data.Subjects = append(data.Subjects, current)
	}
	return data, nil
}

func (r Request) tool() map[string]any {
	definition := tool("report_exercise_estimates")
	results := definition["function"].(map[string]any)["parameters"].(map[string]any)["properties"].(map[string]any)["results"].(map[string]any)
	entry := results["items"].(map[string]any)
	properties := entry["properties"].(map[string]any)
	for aspect := range maps.Clone(properties) {
		if aspect != "id" && !r.wants(aspect) {
			delete(properties, aspect)
		}
	}
	ids := make([]any, 0, len(r.Subjects))
	for _, subject := range r.Subjects {
		ids = append(ids, subject.ID)
	}
	properties["id"] = map[string]any{"type": "string", "enum": ids}
	return definition
}

func parseSubject(subject Subject, raw map[string]any) (Estimate, error) {
	var parsed Estimate
	for _, aspect := range subject.Aspects {
		value, present := raw[aspect]
		if !present {
			return Estimate{}, fmt.Errorf("%s missing", aspect)
		}
		var err error
		switch aspect {
		case AspectFatigue:
			var fatigue Fatigue
			fatigue, err = parseFatigue(value)
			parsed.Fatigue = &fatigue
		case AspectE1RM:
			var e1rm E1RM
			e1rm, err = parseE1RM(value)
			parsed.E1RM = &e1rm
		case AspectMuscles:
			var muscles Muscles
			muscles, err = parseMuscles(value)
			parsed.Muscles = &muscles
		case AspectLiftTransfer:
			parsed.LiftTransfer, err = parseLiftTransfer(value)
		case AspectText:
			var text Text
			text, err = parseText(value)
			parsed.Text = &text
		}
		if err != nil {
			return Estimate{}, err
		}
	}
	return parsed, nil
}

func Batch(ctx context.Context, infer execution.Inferer, request Request) (map[string]Estimate, map[string]string, error) {
	data, err := request.prompt()
	if err != nil {
		return nil, nil, err
	}
	args, err := ask(ctx, infer, render("batch_system", data), render("batch_user", data), request.tool())
	if err != nil {
		return nil, nil, err
	}
	subjects := map[string]Subject{}
	for _, subject := range request.Subjects {
		subjects[subject.ID] = subject
	}
	estimates := map[string]Estimate{}
	failures := map[string]string{}
	entries, _ := args["results"].([]any)
	for _, entry := range entries {
		raw, _ := entry.(map[string]any)
		id, _ := raw["id"].(string)
		subject, known := subjects[id]
		_, answered := estimates[id]
		if _, rejected := failures[id]; !known || answered || rejected {
			continue
		}
		parsed, err := parseSubject(subject, raw)
		if err != nil {
			failures[id] = err.Error()
			continue
		}
		estimates[id] = parsed
	}
	for _, subject := range request.Subjects {
		_, answered := estimates[subject.ID]
		if _, rejected := failures[subject.ID]; !answered && !rejected {
			failures[subject.ID] = "missing from model response"
		}
	}
	return estimates, failures, nil
}
