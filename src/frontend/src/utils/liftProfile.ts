import type { LiftProfile } from '@powerlifting/types'
import definitions from '../../../services/lift_profile_options.json'

export type Lift = LiftProfile['lift']

export interface LiftProfileOption {
  value: string
  label: string
}

export interface LiftProfileField {
  key: string
  label: string
  options: LiftProfileOption[]
  locked?: { when: Record<string, string>; value: string }
}

const DEFINITIONS = definitions as Record<Lift | 'common', LiftProfileField[]>

export const LIFTS: Lift[] = ['squat', 'bench', 'deadlift']
export const VOLUME_TOLERANCE_FIELD = DEFINITIONS.common.find((field) => field.key === 'volume_tolerance') as LiftProfileField

export function liftProfileFields(lift: Lift): LiftProfileField[] {
  return DEFINITIONS[lift] ?? []
}

export function lockedValue(field: LiftProfileField, options: Record<string, string>): string | null {
  if (!field.locked) return null
  return Object.entries(field.locked.when).every(([key, value]) => options[key] === value) ? field.locked.value : null
}

export function cleanOptions(lift: Lift, options: Record<string, string> | undefined): Record<string, string> {
  const cleaned: Record<string, string> = {}
  for (const field of liftProfileFields(lift)) {
    const value = options?.[field.key]
    if (value && field.options.some((option) => option.value === value)) cleaned[field.key] = value
  }
  for (const field of liftProfileFields(lift)) {
    const locked = lockedValue(field, cleaned)
    if (locked) cleaned[field.key] = locked
  }
  return cleaned
}

export function missingOptions(profile: LiftProfile): string[] {
  const options = profile.options ?? {}
  return liftProfileFields(profile.lift).filter((field) => !options[field.key]).map((field) => field.label)
}

export function describeLiftProfile(profile: LiftProfile): { label: string; value: string }[] {
  const options = profile.options ?? {}
  return liftProfileFields(profile.lift).flatMap((field) => {
    const option = field.options.find((candidate) => candidate.value === options[field.key])
    return option ? [{ label: field.label, value: option.label }] : []
  })
}

export function defaultLiftProfile(lift: Lift): LiftProfile {
  return { lift, options: {}, volume_tolerance: 'moderate', notes: '', stimulus_coefficient: 1, e1rm_multiplier: 1 }
}

export function normalizeLiftProfile(profile: Partial<LiftProfile> & { lift: Lift }): LiftProfile {
  const multiplier = Math.max(0.85, Math.min(1.10, profile.e1rm_multiplier ?? 1))
  return {
    ...defaultLiftProfile(profile.lift),
    ...profile,
    options: cleanOptions(profile.lift, profile.options),
    volume_tolerance: profile.volume_tolerance ?? 'moderate',
    notes: profile.notes ?? '',
    stimulus_coefficient: Math.max(1, Math.min(2, profile.stimulus_coefficient ?? 1)),
    e1rm_multiplier: Number(multiplier.toFixed(2)),
  }
}

export function normalizeLiftProfiles(profiles: LiftProfile[] = []): LiftProfile[] {
  return LIFTS.map((lift) => normalizeLiftProfile(profiles.find((profile) => profile.lift === lift) ?? { lift }))
}

export function mergeLiftProfiles(profiles: LiftProfile[] | undefined, replacement: LiftProfile): LiftProfile[] {
  return LIFTS.map((lift) => normalizeLiftProfile(lift === replacement.lift ? replacement : profiles?.find((profile) => profile.lift === lift) ?? { lift }))
}
