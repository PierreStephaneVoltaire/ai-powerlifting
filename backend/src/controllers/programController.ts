import { invokeLambda } from '../utils/lambda'
import { randomUUID } from 'crypto'
import type { Program, ProgramListItem, Phase, Session, PlannedExercise, LiftProfile } from '@powerlifting/types'
import type { MutationEnvelope } from './sessionController'

export type ProgramLoadOptions = {
  block?: string
  windowStart?: string
  windowEnd?: string
}

export async function getProgram(pk: string, version: string, options: ProgramLoadOptions = {}): Promise<Program> {
  return (await invokeLambda('pod_training_program', {
    function: 'program_get',
    pk,
    program_sk: version === "current" ? undefined : `program#${version}`,
    block: options.block,
    window_start: options.windowStart,
    window_end: options.windowEnd,
  })) as Program
}

export async function listPrograms(pk: string): Promise<ProgramListItem[]> {
  return (await invokeLambda('pod_training_program', { function: 'program_list_full',  pk, include_archived: true })) as ProgramListItem[]
}

export async function updateMetaField(
  pk: string,
  version: string,
  field: string,
  value: unknown,
  envelope: MutationEnvelope,
): Promise<Record<string, unknown>> {
  return await invokeLambda('pod_training_program', { function: 'program_update_meta_field',  pk, program_sk: version === "current" ? undefined : `program#${version}`, field, value, ...envelope }) as Record<string, unknown>
}

export async function updateMetaFields(pk: string, version: string, updates: Record<string, unknown>, envelope: MutationEnvelope): Promise<Record<string, unknown>> {
  return await invokeLambda('pod_training_program', { function: 'program_update_meta_field', pk, program_sk: version === 'current' ? undefined : `program#${version}`, updates, ...envelope }) as Record<string, unknown>
}

export async function updateBodyWeight(
  pk: string,
  version: string,
  weightKg: number,
  envelope: MutationEnvelope,
): Promise<Record<string, unknown>> {
  return await invokeLambda('pod_training_program', { function: 'program_update_meta_field',  pk, program_sk: version === "current" ? undefined : `program#${version}`, updates: { current_body_weight_kg: weightKg, current_body_weight_lb: weightKg * 2.20462 }, ...envelope }) as Record<string, unknown>
}

export async function updatePhases(
  pk: string,
  version: string,
  phases: Phase[],
  block: string | undefined,
  envelope: MutationEnvelope,
): Promise<Record<string, unknown>> {
  return await invokeLambda('pod_training_program', { function: 'program_update_phases',  pk, program_sk: version === "current" ? undefined : `program#${version}`, phases, block, ...envelope }) as Record<string, unknown>
}

export async function updateLiftProfiles(
  pk: string,
  version: string,
  liftProfiles: LiftProfile[],
  envelope: MutationEnvelope,
): Promise<Record<string, unknown>> {
  return await invokeLambda('pod_training_program', { function: 'program_update_lift_profiles',  pk, program_sk: version === "current" ? undefined : `program#${version}`, lift_profiles: liftProfiles, ...envelope }) as Record<string, unknown>
}

export async function archiveProgram(pk: string, version: string, envelope: MutationEnvelope): Promise<Record<string, unknown>> {
  return await invokeLambda('pod_training_program', { function: 'program_archive',  pk, program_sk: version === "current" ? undefined : `program#${version}`, ...envelope }) as Record<string, unknown>
}

export async function unarchiveProgram(pk: string, version: string, envelope: MutationEnvelope): Promise<Record<string, unknown>> {
  return await invokeLambda('pod_training_program', { function: 'program_unarchive',  pk, program_sk: version === "current" ? undefined : `program#${version}`, ...envelope }) as Record<string, unknown>
}

export async function batchCreateWeek(
  pk: string,
  version: string,
  weekNumber: number,
  weekLabel: string,
  days: Array<{ date: string; day: string }>,
  phase: string,
  exercises: PlannedExercise[],
  envelope: MutationEnvelope,
): Promise<void> {
  const result = (await invokeLambda('pod_sessions', { function: 'session_list',  pk, program_sk: version === "current" ? undefined : `program#${version}` })) as { sessions: Session[] }
  for (const day of days) {
    const session: Session = {
      id: randomUUID(),
      date: day.date,
      day: day.day,
      week: weekLabel,
      week_number: weekNumber,
      phase: { name: phase, intent: '', start_week: weekNumber, end_week: weekNumber, block: 'current' },
      status: 'planned',
      completed: false,
      planned_exercises: exercises,
      exercises: [],
      session_notes: '',
      session_rpe: null,
      body_weight_kg: null,
      block: 'current',
    }
    await invokeLambda('pod_sessions', { function: 'session_create',  pk, program_sk: version === "current" ? undefined : `program#${version}`, session, ...envelope })
  }
}

export async function updatePlannedExercises(
  pk: string,
  version: string,
  date: string,
  index: number,
  plannedExercises: PlannedExercise[],
  envelope: MutationEnvelope,
): Promise<void> {
  const existing = (await invokeLambda('pod_sessions', { function: 'session_get',  pk, program_sk: version === "current" ? undefined : `program#${version}`, date, index, session_id: envelope.session_id })) as Session
  const exerciseKey = (exercise: any) => String(exercise.glossary_id || exercise.exercise_id || exercise.name || '').trim().toLowerCase()
  const priorByKey = new Map((existing.exercises || []).map((exercise: any) => [exerciseKey(exercise), exercise]))
  const syncExercises = !existing.completed
    ? (() => {
      const matched = new Set<string>()
      const updated = plannedExercises.map((pe) => {
        const prior = priorByKey.get(exerciseKey(pe)) as any
        matched.add(exerciseKey(pe))
        const priorSets: string[] = Array.isArray(prior?.set_statuses) ? prior.set_statuses : []
        const executed = priorSets.some((status) => status !== 'pending')
        const setCount = Math.max(Number(pe.sets) || 0, priorSets.length)
        return {
          ...(prior || {}),
          name: executed ? prior?.name : pe.name,
          sets: setCount,
          reps: executed ? prior?.reps : pe.reps,
          kg: executed ? prior?.kg : pe.kg,
          notes: prior?.notes || '',
          failed_sets: Array.from({ length: setCount }, (_, i) => prior?.failed_sets?.[i] ?? false),
          set_statuses: Array.from({ length: setCount }, (_, i) => priorSets[i] ?? 'pending'),
          failed_set_reasons: Array.from({ length: setCount }, (_, i) => prior?.failed_set_reasons?.[i] ?? []),
          set_ids: Array.from({ length: setCount }, (_, i) => prior?.set_ids?.[i] || randomUUID()),
        }
      })
      return updated.concat((existing.exercises || []).filter((exercise: any) => {
        const key = exerciseKey(exercise)
        return !matched.has(key) && (exercise.set_statuses || []).some((status: string) => status !== 'pending')
      }))
    })()
    : existing.exercises

  await invokeLambda('pod_sessions', { function: 'session_patch', 
    pk, program_sk: version === "current" ? undefined : `program#${version}`,
    date,
    index,
    patch: {
      planned_exercises: plannedExercises,
      ...(syncExercises !== existing.exercises ? { exercises: syncExercises } : {}),
    },
    ...envelope,
  })
}
