import { invokeLambda } from '../utils/lambda'
import { AppError } from '../middleware/errorHandler'
import { randomUUID } from 'crypto'
import type { Program, ProgramListItem, Phase, Session, PlannedExercise, LiftProfile } from '@powerlifting/types'

// Programs live in if-health. All DynamoDB work (program#current pointer,
// in-place meta/phases/lift_profiles updates, archive/unarchive, list) lives in
// the program_* Fission functions (layer pl_program / program_store). The
// backend is a pure auth/pk router.
//
// No fork / no version handling — the frontend only operates on current. The
// `version` param is kept in signatures (prefixed _version) so the route
// compiles unchanged but is ignored; Fission resolves current internally.
// batchCreateWeek + updatePlannedExercises compose the session_* fission tools
// (sessions are a separate table / domain).

export async function getProgram(pk: string, _version: string): Promise<Program> {
  return (await invokeLambda('program_get', { pk })) as Program
}

export async function listPrograms(pk: string): Promise<ProgramListItem[]> {
  return (await invokeLambda('program_list_full', { pk, include_archived: true })) as ProgramListItem[]
}

export async function updateMetaField(
  pk: string,
  _version: string,
  field: string,
  value: unknown,
): Promise<void> {
  await invokeLambda('program_update_meta_field', { pk, field, value })
}

export async function updateBodyWeight(
  pk: string,
  _version: string,
  weightKg: number,
): Promise<void> {
  // Two in-place meta updates — the route calls updateMetaField twice; keep the
  // convenience wrapper delegating to the same fission tool.
  await invokeLambda('program_update_meta_field', { pk, field: 'current_body_weight_kg', value: weightKg })
  await invokeLambda('program_update_meta_field', { pk, field: 'current_body_weight_lb', value: weightKg * 2.20462 })
}

export async function updatePhases(
  pk: string,
  _version: string,
  phases: Phase[],
  block?: string,
): Promise<void> {
  await invokeLambda('program_update_phases', { pk, phases, block })
}

export async function updateLiftProfiles(
  pk: string,
  _version: string,
  liftProfiles: LiftProfile[],
): Promise<void> {
  await invokeLambda('program_update_lift_profiles', { pk, lift_profiles: liftProfiles })
}

export async function archiveProgram(pk: string, _version: string): Promise<void> {
  await invokeLambda('program_archive', { pk })
}

export async function unarchiveProgram(pk: string, _version: string): Promise<void> {
  await invokeLambda('program_unarchive', { pk })
}

export async function batchCreateWeek(
  pk: string,
  _version: string,
  weekNumber: number,
  weekLabel: string,
  days: Array<{ date: string; day: string }>,
  phase: string,
  exercises: PlannedExercise[],
): Promise<void> {
  // Compose session_create for each day — sessions are a separate table/domain.
  // Check for existing-date conflicts first (cheap read via session_list_full).
  const existing = (await invokeLambda('session_list_full', { pk })) as Session[]
  const existingDates = new Set(existing.map((s) => s.date))
  for (const day of days) {
    if (existingDates.has(day.date)) {
      throw new AppError(`Session with date ${day.date} already exists`, 400)
    }
  }
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
    await invokeLambda('session_create', { pk, session })
  }
}

export async function updatePlannedExercises(
  pk: string,
  _version: string,
  date: string,
  index: number,
  plannedExercises: PlannedExercise[],
): Promise<void> {
  // Read the session, sync exercises from planned for incomplete sessions, patch.
  const existing = (await invokeLambda('session_get', { pk, date, index })) as Session
  const syncExercises = !existing.completed
    ? plannedExercises.map((pe) => ({
        name: pe.name,
        sets: pe.sets,
        reps: pe.reps,
        kg: pe.kg,
        notes: '',
        failed_sets: Array(pe.sets).fill(false),
        set_statuses: Array(pe.sets).fill('pending'),
        failed_set_reasons: Array.from({ length: pe.sets }, () => []),
      }))
    : existing.exercises

  await invokeLambda('session_patch', {
    pk,
    date,
    index,
    patch: {
      planned_exercises: plannedExercises,
      ...(syncExercises !== existing.exercises ? { exercises: syncExercises } : {}),
    },
  })
}
