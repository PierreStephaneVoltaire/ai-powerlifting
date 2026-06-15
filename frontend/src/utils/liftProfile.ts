import { LiftProfile } from '@powerlifting/types'

export function normalizeLiftProfile(profile: Partial<LiftProfile> & { lift: 'squat' | 'bench' | 'deadlift' }): LiftProfile {
  const multiplier = profile.e1rm_multiplier ?? 1.00
  const clampedMultiplier = Math.max(0.85, Math.min(1.10, multiplier))

  return {
    lift: profile.lift,
    style_notes: profile.style_notes ?? '',
    sticking_points: profile.sticking_points ?? '',
    primary_muscle: profile.primary_muscle ?? '',
    volume_tolerance: profile.volume_tolerance ?? 'moderate',
    e1rm_multiplier: Number(clampedMultiplier.toFixed(2)),
    stimulus_coefficient: profile.stimulus_coefficient,
    stimulus_coefficient_reasoning: profile.stimulus_coefficient_reasoning,
    stimulus_coefficient_confidence: profile.stimulus_coefficient_confidence,
    stimulus_coefficient_updated_at: profile.stimulus_coefficient_updated_at,
    inol_low_threshold: profile.inol_low_threshold,
    inol_high_threshold: profile.inol_high_threshold,
  }
}

export function normalizeLiftProfiles(profiles: LiftProfile[] = []): LiftProfile[] {
  return (['squat', 'bench', 'deadlift'] as const).map((lift) => {
    const existing = profiles.find((p) => p.lift === lift)
    return normalizeLiftProfile(existing ?? { lift })
  })
}
