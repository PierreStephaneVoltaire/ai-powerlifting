import { invokeLambda } from '../utils/lambda'
import { AppError } from '../middleware/errorHandler'
import type { Session, Exercise, SessionStatus, SessionWellness } from '@powerlifting/types'

// Sessions live in their own table (if-sessions), scoped to the CURRENT program.
// All DynamoDB work (program#current pointer resolution, phase loading, SK
// construction, same-day ordinals, buildItem/publicSession) lives in the
// session_* Fission functions (layer pl_sessions / session_store). The backend
// is now a pure auth/pk router.
//
// Program version is intentionally NOT handled — the frontend only ever
// operates on the current program, and the Fission tools resolve
// `program#current` internally. The `version` param is accepted by the route
// but ignored here.
//
// Compound operations (complete / add-exercise / remove-exercise /
// update-exercise-field) compose with a single session_get + session_patch;
// the merge is trivial field selection, not DynamoDB logic. reschedule and
// status need no read (the patch is self-contained).

async function fetchCurrent(pk: string, date: string, index: number): Promise<Session> {
  const session = await invokeLambda('session_get', { pk, date, index })
  if (!session) throw new AppError(`Session at index ${index} not found`, 404)
  return session as Session
}

export async function createSession(
  pk: string,
  _version: string,
  session: Session,
): Promise<void> {
  await invokeLambda('session_create', { pk, session })
}

export async function deleteSession(
  pk: string,
  _version: string,
  date: string,
  index: number,
): Promise<void> {
  await invokeLambda('session_delete', { pk, date, index })
}

export async function getSession(
  pk: string,
  _version: string,
  date: string,
  index: number,
): Promise<Session | null> {
  return (await invokeLambda('session_get', { pk, date, index })) as Session | null
}

export async function updateSession(
  pk: string,
  _version: string,
  date: string,
  index: number,
  session: Session,
): Promise<void> {
  await invokeLambda('session_replace', { pk, date, index, session })
}

export async function rescheduleSession(
  pk: string,
  _version: string,
  date: string,
  index: number,
  newDate: string,
  newDay: string,
): Promise<void> {
  await invokeLambda('session_patch', { pk, date, index, patch: { date: newDate, day: newDay } })
}

export async function completeSession(
  pk: string,
  _version: string,
  date: string,
  index: number,
  data: { rpe?: number; bodyWeightKg?: number; notes?: string; wellness?: SessionWellness | undefined },
): Promise<void> {
  const current = await fetchCurrent(pk, date, index)
  await invokeLambda('session_patch', {
    pk,
    date,
    index,
    patch: {
      completed: true,
      status: current.status === 'planned' ? 'completed' : current.status,
      session_rpe: data.rpe ?? current.session_rpe,
      body_weight_kg: data.bodyWeightKg ?? current.body_weight_kg,
      session_notes: data.notes ?? current.session_notes,
      wellness: data.wellness ?? current.wellness,
    },
  })
}

export async function updateSessionStatus(
  pk: string,
  _version: string,
  date: string,
  index: number,
  status: SessionStatus,
): Promise<void> {
  await invokeLambda('session_patch', {
    pk,
    date,
    index,
    patch: {
      status,
      completed: status === 'completed' || status === 'logged',
    },
  })
}

export async function addExercise(
  pk: string,
  _version: string,
  date: string,
  index: number,
  exercise: Exercise,
): Promise<void> {
  const current = await fetchCurrent(pk, date, index)
  await invokeLambda('session_patch', {
    pk,
    date,
    index,
    patch: { exercises: [...(current.exercises || []), exercise] },
  })
}

export async function removeExercise(
  pk: string,
  _version: string,
  date: string,
  index: number,
  exerciseIndex: number,
): Promise<void> {
  const current = await fetchCurrent(pk, date, index)
  const exercises = [...(current.exercises || [])]
  if (exerciseIndex < 0 || exerciseIndex >= exercises.length) {
    throw new AppError(`Exercise index ${exerciseIndex} out of range`, 400)
  }
  exercises.splice(exerciseIndex, 1)
  await invokeLambda('session_patch', { pk, date, index, patch: { exercises } })
}

export async function updateExerciseField(
  pk: string,
  _version: string,
  date: string,
  index: number,
  exerciseIndex: number,
  field: keyof Exercise,
  value: unknown,
): Promise<void> {
  const current = await fetchCurrent(pk, date, index)
  const exercises = [...(current.exercises || [])]
  if (exerciseIndex < 0 || exerciseIndex >= exercises.length) {
    throw new AppError(`Exercise index ${exerciseIndex} out of range`, 400)
  }
  ;(exercises[exerciseIndex] as any)[field] = value
  await invokeLambda('session_patch', { pk, date, index, patch: { exercises } })
}
