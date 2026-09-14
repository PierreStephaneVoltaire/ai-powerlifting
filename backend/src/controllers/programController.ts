import { invokeLambda } from '../utils/lambda'
import { randomUUID } from 'crypto'
import type { Program, ProgramListItem, Phase, Session, PlannedExercise, LiftProfile } from '@powerlifting/types'

export async function getProgram(pk: string, version: string): Promise<Program> {
  return (await invokeLambda('pod_training_program', { function: 'program_get',  pk, program_sk: version === "current" ? undefined : `program#${version}` })) as Program
}

export async function listPrograms(pk: string): Promise<ProgramListItem[]> {
  return (await invokeLambda('pod_training_program', { function: 'program_list_full',  pk, include_archived: true })) as ProgramListItem[]
}

export async function updateMetaField(
  pk: string,
  version: string,
  field: string,
  value: unknown,
): Promise<void> {
  await invokeLambda('pod_training_program', { function: 'program_update_meta_field',  pk, program_sk: version === "current" ? undefined : `program#${version}`, field, value })
}

export async function updateBodyWeight(
  pk: string,
  version: string,
  weightKg: number,
): Promise<void> {
  await invokeLambda('pod_training_program', { function: 'program_update_meta_field',  pk, program_sk: version === "current" ? undefined : `program#${version}`, field: 'current_body_weight_kg', value: weightKg })
  await invokeLambda('pod_training_program', { function: 'program_update_meta_field',  pk, program_sk: version === "current" ? undefined : `program#${version}`, field: 'current_body_weight_lb', value: weightKg * 2.20462 })
}

export async function updatePhases(
  pk: string,
  version: string,
  phases: Phase[],
  block?: string,
): Promise<void> {
  await invokeLambda('pod_training_program', { function: 'program_update_phases',  pk, program_sk: version === "current" ? undefined : `program#${version}`, phases, block })
}

export async function updateLiftProfiles(
  pk: string,
  version: string,
  liftProfiles: LiftProfile[],
): Promise<void> {
  await invokeLambda('pod_training_program', { function: 'program_update_lift_profiles',  pk, program_sk: version === "current" ? undefined : `program#${version}`, lift_profiles: liftProfiles })
}

export async function archiveProgram(pk: string, version: string): Promise<void> {
  await invokeLambda('pod_training_program', { function: 'program_archive',  pk, program_sk: version === "current" ? undefined : `program#${version}` })
}

export async function unarchiveProgram(pk: string, version: string): Promise<void> {
  await invokeLambda('pod_training_program', { function: 'program_unarchive',  pk, program_sk: version === "current" ? undefined : `program#${version}` })
}

export async function batchCreateWeek(
  pk: string,
  version: string,
  weekNumber: number,
  weekLabel: string,
  days: Array<{ date: string; day: string }>,
  phase: string,
  exercises: PlannedExercise[],
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
    await invokeLambda('pod_sessions', { function: 'session_create',  pk, program_sk: version === "current" ? undefined : `program#${version}`, session })
  }
}

export async function updatePlannedExercises(
  pk: string,
  version: string,
  date: string,
  index: number,
  plannedExercises: PlannedExercise[],
): Promise<void> {
  const existing = (await invokeLambda('pod_sessions', { function: 'session_get',  pk, program_sk: version === "current" ? undefined : `program#${version}`, date, index })) as Session
  const syncExercises = !existing.completed
    ? plannedExercises.map((pe, exerciseIndex) => {
        const prior = existing.exercises?.[exerciseIndex]
        const priorRecord = prior as (typeof prior & { set_ids?: string[] }) | undefined
        const priorSets = Array.isArray(priorRecord?.set_statuses) ? priorRecord.set_statuses : []
        const setCount = pe.sets
        return {
        ...(prior || {}),
        name: pe.name,
        sets: pe.sets,
        reps: pe.reps,
        kg: pe.kg,
        notes: priorRecord?.notes || '',
        failed_sets: Array.from({ length: setCount }, (_, setIndex) => priorRecord?.failed_sets?.[setIndex] ?? false),
        set_statuses: Array.from({ length: setCount }, (_, setIndex) => priorSets[setIndex] ?? 'pending'),
        failed_set_reasons: Array.from({ length: setCount }, (_, setIndex) => priorRecord?.failed_set_reasons?.[setIndex] ?? []),
        set_ids: Array.from({ length: setCount }, (_, setIndex) => priorRecord?.set_ids?.[setIndex] || randomUUID()),
      }
    })
    : existing.exercises

  await invokeLambda('pod_sessions', { function: 'session_patch', 
    pk, program_sk: version === "current" ? undefined : `program#${version}`,
    date,
    index,
    patch: {
      planned_exercises: plannedExercises,
      ...(syncExercises !== existing.exercises ? { exercises: syncExercises } : {}),
    },
  })
}
