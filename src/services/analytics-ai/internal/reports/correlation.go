package reports

import (
	"context"
	"slices"
	"time"

	analyticsv1 "powerlifting/analytics-ai/gen/analytics"
	"powerlifting/analytics-ai/internal/prompts"
)

var measurementKeys = []string{"height_cm", "arm_wingspan_cm", "leg_length_cm", "weight_class_kg", "current_body_weight_kg"}

func Correlation(ctx context.Context, env Env) (map[string]any, error) {
	weeks := 4
	if requested := asInt(env.Args["weeks"]); requested > 0 {
		weeks = requested
	}
	block := env.text("block")
	if block == "" {
		block = "current"
	}
	reply, err := env.Source.Correlation(ctx, env.Principal, block)
	if err != nil {
		return nil, err
	}
	return correlate(ctx, env, reply, weeks, true)
}

func BlockCorrelation(ctx context.Context, env Env) (map[string]any, error) {
	reply, err := env.Source.Correlation(ctx, env.Principal, env.blockKey())
	if err != nil {
		return nil, err
	}
	return correlate(ctx, env, reply, int(reply.Weeks), false)
}

func correlate(ctx context.Context, env Env, reply *analyticsv1.CorrelationInputsReply, weeks int, trailing bool) (map[string]any, error) {
	input := correlationInput(reply, weeks)
	windowStart := reply.WindowStart
	if trailing {
		input, windowStart = trailingWindow(input, reply.WindowStart, weeks)
	}
	input.WindowStart = windowStart
	report := map[string]any{"cached": false, "generated_at": env.timestamp(), "window_start": windowStart, "weeks": max(1, weeks)}
	if distinct := distinctWeeks(input); !Sufficient(distinct) {
		return InsufficientCorrelation(windowStart, weeks, distinct), nil
	}
	user, err := prompts.RenderCorrelationUser(input)
	if err != nil {
		return nil, err
	}
	answer, err := ask(ctx, env.Infer, prompts.CorrelationSystem(), user, prompts.Tool("report_correlation_findings"))
	if err != nil {
		return nil, err
	}
	report["findings"] = pick(answer, "findings", []any{})
	report["summary"] = pick(answer, "summary", "")
	report["insufficient_data"] = pick(answer, "insufficient_data", false)
	report["insufficient_data_reason"] = pick(answer, "insufficient_data_reason", "")
	return report, nil
}

func correlationInput(reply *analyticsv1.CorrelationInputsReply, weeks int) prompts.CorrelationInput {
	input := prompts.CorrelationInput{Weeks: weeks, WindowStart: reply.WindowStart}
	for _, row := range reply.WeeklyE1Rm {
		if row.SquatKg == nil && row.BenchKg == nil && row.DeadliftKg == nil {
			continue
		}
		input.E1rm = append(input.E1rm, prompts.WeekLifts{Week: int(row.WeekNumber), Squat: row.SquatKg, Bench: row.BenchKg, Deadlift: row.DeadliftKg})
	}
	for _, week := range reply.WeeklyAccessory {
		entry := prompts.WeekAccessory{Week: int(week.WeekNumber)}
		for _, exercise := range week.Exercises {
			if exercise.VolumeKg > 0 {
				entry.Exercises = append(entry.Exercises, prompts.Exercise{Name: exercise.Name, VolumeKg: exercise.VolumeKg})
			}
		}
		if len(entry.Exercises) > 0 {
			input.Accessory = append(input.Accessory, entry)
		}
	}
	mapDrivers(&input, reply)
	for _, profile := range reply.LiftProfiles {
		fields := profile.AsMap()
		input.LiftProfiles = append(input.LiftProfiles, prompts.LiftProfile{
			Lift: asString(fields["lift"]), StyleNotes: asString(fields["style_notes"]), StickingPoints: asString(fields["sticking_points"]),
			PrimaryMuscle: asString(fields["primary_muscle"]), VolumeTolerance: asString(fields["volume_tolerance"]),
		})
	}
	measurements := reply.GetAthleteMeasurements().AsMap()
	for _, key := range measurementKeys {
		measurement := prompts.Measurement{Name: key}
		if value, ok := asFloat(measurements[key]); ok {
			measurement.Value = &value
		}
		input.Measurements = append(input.Measurements, measurement)
	}
	return input
}

func dims(value *analyticsv1.FatigueDims) prompts.Dims {
	return prompts.Dims{Axial: value.GetAxial(), Neural: value.GetNeural(), Peripheral: value.GetPeripheral(), Systemic: value.GetSystemic()}
}

func mapDrivers(input *prompts.CorrelationInput, reply *analyticsv1.CorrelationInputsReply) {
	for _, row := range reply.ExerciseWeeks {
		input.ExerciseWeeks = append(input.ExerciseWeeks, prompts.ExerciseDose{
			Week: int(row.WeekNumber), Exercise: row.Exercise, Sets: row.Sets, Reps: row.Reps, VolumeKg: row.VolumeKg,
			Sessions: int(row.Sessions), IntensityPct: row.AvgIntensityPct, RPE: row.AvgRpe,
		})
	}
	for _, row := range reply.Exercises {
		input.Exercises = append(input.Exercises, prompts.ExerciseInfo{
			Name: row.Name, Primary: row.PrimaryMuscles, Secondary: row.SecondaryMuscles, Fatigue: dims(row.Fatigue),
			Squat: row.GetLiftTransfer().GetSquat(), Bench: row.GetLiftTransfer().GetBench(), Deadlift: row.GetLiftTransfer().GetDeadlift(),
			TransferSource: row.TransferSource,
		})
	}
	for _, row := range reply.MuscleWeeks {
		input.MuscleWeeks = append(input.MuscleWeeks, prompts.MuscleDose{Week: int(row.WeekNumber), Muscle: row.Muscle, Sets: row.WeightedSets})
	}
	for _, row := range reply.MuscleLandmarks {
		input.MuscleLandmarks = append(input.MuscleLandmarks, prompts.MuscleLandmark{Muscle: row.Muscle, MEV: row.Mev, MAV: row.Mav, MRV: row.Mrv})
	}
	for _, row := range reply.FatigueWeeks {
		input.FatigueWeeks = append(input.FatigueWeeks, prompts.FatigueWeek{Week: int(row.WeekNumber), Ratio: dims(row.Ratio)})
	}
	for _, row := range reply.LiftSessions {
		input.LiftSessions = append(input.LiftSessions, prompts.LiftSession{
			Date: row.Date, Lift: row.Lift, E1rmKg: row.TopE1RmKg, ResidualPct: row.E1RmResidualPct, RPE: row.AvgRpe,
			Prior: dims(row.Prior48HFatigue), PriorMuscles: row.Prior48HMuscleSets,
		})
	}
	for _, row := range reply.DriverStats {
		input.DriverStats = append(input.DriverStats, prompts.DriverStat{
			Type: row.DriverType, Driver: row.Driver, Lift: row.Lift, Rho: row.Rho, N: int(row.N), NHigh: int(row.NHigh), NLow: int(row.NLow),
			ResidualHigh: row.MeanResidualPctHigh, ResidualLow: row.MeanResidualPctLow, RPEHigh: row.MeanRpeHigh, RPELow: row.MeanRpeLow,
		})
	}
}

func distinctWeeks(input prompts.CorrelationInput) int {
	weeks := map[int]bool{}
	for _, row := range input.E1rm {
		weeks[row.Week] = true
	}
	for _, row := range input.Accessory {
		weeks[row.Week] = true
	}
	for _, row := range input.ExerciseWeeks {
		weeks[row.Week] = true
	}
	return len(weeks)
}

func trailingWindow(input prompts.CorrelationInput, start string, weeks int) (prompts.CorrelationInput, string) {
	latest := 0
	for _, row := range input.E1rm {
		latest = max(latest, row.Week)
	}
	for _, row := range input.Accessory {
		latest = max(latest, row.Week)
	}
	for _, row := range input.ExerciseWeeks {
		latest = max(latest, row.Week)
	}
	first := latest - weeks + 1
	if first <= 1 {
		return input, start
	}
	input.E1rm = slices.DeleteFunc(slices.Clone(input.E1rm), func(row prompts.WeekLifts) bool { return row.Week < first })
	input.Accessory = slices.DeleteFunc(slices.Clone(input.Accessory), func(row prompts.WeekAccessory) bool { return row.Week < first })
	input.ExerciseWeeks = slices.DeleteFunc(slices.Clone(input.ExerciseWeeks), func(row prompts.ExerciseDose) bool { return row.Week < first })
	input.MuscleWeeks = slices.DeleteFunc(slices.Clone(input.MuscleWeeks), func(row prompts.MuscleDose) bool { return row.Week < first })
	input.FatigueWeeks = slices.DeleteFunc(slices.Clone(input.FatigueWeeks), func(row prompts.FatigueWeek) bool { return row.Week < first })
	if begin, err := time.Parse("2006-01-02", start); err == nil {
		start = begin.AddDate(0, 0, 7*(first-1)).Format("2006-01-02")
		input.LiftSessions = slices.DeleteFunc(slices.Clone(input.LiftSessions), func(row prompts.LiftSession) bool { return row.Date < start })
	}
	return input, start
}
