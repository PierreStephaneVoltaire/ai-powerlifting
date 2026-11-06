import { callOperation } from '../utils/operations'
import { AppError } from '../middleware/errorHandler'
import type { Session, Exercise, SessionStatus, SessionWellness } from '@powerlifting/types'

export interface SessionTarget { session_id?: string }
interface SessionMutationResult {
  session?: Session
  deleted?: string
  success?: boolean
}

async function fetchCurrent(pk: string, date: string, index: number, session_id?: string): Promise<Session> {
  const session = await callOperation('session_get', { pk, date, index, session_id })
  if (!session) throw new AppError(`Session at index ${index} not found`, 404)
  return session as Session
}

export async function createSession(
  pk: string,
  _version: string,
  session: Session,
  target: SessionTarget,
): Promise<Session> {
  return await callOperation('session_create', { pk, session, ...target }) as Session
}

export async function deleteSession(
  pk: string,
  _version: string,
  date: string,
  index: number,
  target: SessionTarget,
): Promise<SessionMutationResult> {
  return await callOperation('session_delete', { pk, date, index, ...target }) as SessionMutationResult
}

export async function getSession(
  pk: string,
  _version: string,
  date: string,
  index: number,
): Promise<Session | null> {
  return (await callOperation('session_get', { pk, date, index })) as Session | null
}

export async function updateSession(
  pk: string,
  _version: string,
  date: string,
  index: number,
  session: Session,
  target: SessionTarget,
): Promise<Session> {
  return await callOperation('session_replace', { pk, date, index, session, ...target }) as Session
}

export async function rescheduleSession(
  pk: string,
  _version: string,
  date: string,
  index: number,
  newDate: string,
  newDay: string,
  target: SessionTarget,
): Promise<Session> {
  return await callOperation('session_patch', { pk, date, index, patch: { date: newDate, day: newDay }, ...target }) as Session
}

export async function completeSession(
  pk: string,
  _version: string,
  date: string,
  index: number,
  data: { rpe?: number; bodyWeightKg?: number; notes?: string; wellness?: SessionWellness | undefined },
  target: SessionTarget,
): Promise<Session> {
  const current = await fetchCurrent(pk, date, index, target.session_id)
  return await callOperation('session_patch', { pk,
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
    ...target,
  })
}

export async function updateSessionStatus(
  pk: string,
  _version: string,
  date: string,
  index: number,
  status: SessionStatus,
  target: SessionTarget,
): Promise<Session> {
  return await callOperation('session_patch', { pk,
    date,
    index,
    patch: {
      status,
      completed: status === 'completed' || status === 'logged',
    },
    ...target,
  })
}

export async function addExercise(
  pk: string,
  _version: string,
  date: string,
  index: number,
  exercise: Exercise,
  target: SessionTarget,
): Promise<Session> {
  const current = await fetchCurrent(pk, date, index, target.session_id)
  return await callOperation('session_patch', { pk,
    date,
    index,
    patch: { exercises: [...(current.exercises || []), exercise] },
    ...target,
  })
}

export async function removeExercise(
  pk: string,
  _version: string,
  date: string,
  index: number,
  exerciseIndex: number,
  target: SessionTarget,
): Promise<Session> {
  const current = await fetchCurrent(pk, date, index, target.session_id)
  const exercises = [...(current.exercises || [])]
  if (exerciseIndex < 0 || exerciseIndex >= exercises.length) {
    throw new AppError(`Exercise index ${exerciseIndex} out of range`, 400)
  }
  exercises.splice(exerciseIndex, 1)
  return await callOperation('session_patch', { pk, date, index, patch: { exercises }, ...target }) as Session
}

export async function updateExerciseField(
  pk: string,
  _version: string,
  date: string,
  index: number,
  exerciseIndex: number,
  field: keyof Exercise,
  value: unknown,
  target: SessionTarget,
): Promise<Session> {
  const current = await fetchCurrent(pk, date, index, target.session_id)
  const exercises = [...(current.exercises || [])]
  if (exerciseIndex < 0 || exerciseIndex >= exercises.length) {
    throw new AppError(`Exercise index ${exerciseIndex} out of range`, 400)
  }
  ;(exercises[exerciseIndex] as any)[field] = value
  return await callOperation('session_patch', { pk, date, index, patch: { exercises }, ...target }) as Session
}
