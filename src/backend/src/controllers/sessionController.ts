import { invokeLambda } from '../utils/lambda'
import { AppError } from '../middleware/errorHandler'
import type { Session, Exercise, SessionStatus, SessionWellness } from '@powerlifting/types'

export interface MutationEnvelope { expected_revision: number; idempotency_key: string; session_id?: string }
export interface SessionMutationResult {
  session?: Session
  deleted?: string
  revision?: number
  success?: boolean
}

async function fetchCurrent(pk: string, date: string, index: number, session_id?: string): Promise<Session> {
  const session = await invokeLambda('pod_sessions', { function: 'session_get',  pk, date, index, session_id })
  if (!session) throw new AppError(`Session at index ${index} not found`, 404)
  return session as Session
}

export async function createSession(
  pk: string,
  _version: string,
  session: Session,
  envelope: MutationEnvelope,
): Promise<Session> {
  return await invokeLambda('pod_sessions', { function: 'session_create',  pk, session, ...envelope }) as Session
}

export async function deleteSession(
  pk: string,
  _version: string,
  date: string,
  index: number,
  envelope: MutationEnvelope,
): Promise<SessionMutationResult> {
  return await invokeLambda('pod_sessions', { function: 'session_delete',  pk, date, index, ...envelope }) as SessionMutationResult
}

export async function getSession(
  pk: string,
  _version: string,
  date: string,
  index: number,
): Promise<Session | null> {
  return (await invokeLambda('pod_sessions', { function: 'session_get',  pk, date, index })) as Session | null
}

export async function updateSession(
  pk: string,
  _version: string,
  date: string,
  index: number,
  session: Session,
  envelope: MutationEnvelope,
): Promise<Session> {
  return await invokeLambda('pod_sessions', { function: 'session_replace',  pk, date, index, session, ...envelope }) as Session
}

export async function rescheduleSession(
  pk: string,
  _version: string,
  date: string,
  index: number,
  newDate: string,
  newDay: string,
  envelope: MutationEnvelope,
): Promise<Session> {
  return await invokeLambda('pod_sessions', { function: 'session_patch',  pk, date, index, patch: { date: newDate, day: newDay }, ...envelope }) as Session
}

export async function completeSession(
  pk: string,
  _version: string,
  date: string,
  index: number,
  data: { rpe?: number; bodyWeightKg?: number; notes?: string; wellness?: SessionWellness | undefined },
  envelope: MutationEnvelope,
): Promise<Session> {
  const current = await fetchCurrent(pk, date, index, envelope.session_id)
  return await invokeLambda('pod_sessions', { function: 'session_patch',
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
    ...envelope,
  })
}

export async function updateSessionStatus(
  pk: string,
  _version: string,
  date: string,
  index: number,
  status: SessionStatus,
  envelope: MutationEnvelope,
): Promise<Session> {
  return await invokeLambda('pod_sessions', { function: 'session_patch',
    pk,
    date,
    index,
    patch: {
      status,
      completed: status === 'completed' || status === 'logged',
    },
    ...envelope,
  })
}

export async function addExercise(
  pk: string,
  _version: string,
  date: string,
  index: number,
  exercise: Exercise,
  envelope: MutationEnvelope,
): Promise<Session> {
  const current = await fetchCurrent(pk, date, index, envelope.session_id)
  return await invokeLambda('pod_sessions', { function: 'session_patch',
    pk,
    date,
    index,
    patch: { exercises: [...(current.exercises || []), exercise] },
    ...envelope,
  })
}

export async function removeExercise(
  pk: string,
  _version: string,
  date: string,
  index: number,
  exerciseIndex: number,
  envelope: MutationEnvelope,
): Promise<Session> {
  const current = await fetchCurrent(pk, date, index, envelope.session_id)
  const exercises = [...(current.exercises || [])]
  if (exerciseIndex < 0 || exerciseIndex >= exercises.length) {
    throw new AppError(`Exercise index ${exerciseIndex} out of range`, 400)
  }
  exercises.splice(exerciseIndex, 1)
  return await invokeLambda('pod_sessions', { function: 'session_patch',  pk, date, index, patch: { exercises }, ...envelope }) as Session
}

export async function updateExerciseField(
  pk: string,
  _version: string,
  date: string,
  index: number,
  exerciseIndex: number,
  field: keyof Exercise,
  value: unknown,
  envelope: MutationEnvelope,
): Promise<Session> {
  const current = await fetchCurrent(pk, date, index, envelope.session_id)
  const exercises = [...(current.exercises || [])]
  if (exerciseIndex < 0 || exerciseIndex >= exercises.length) {
    throw new AppError(`Exercise index ${exerciseIndex} out of range`, 400)
  }
  ;(exercises[exerciseIndex] as any)[field] = value
  return await invokeLambda('pod_sessions', { function: 'session_patch',  pk, date, index, patch: { exercises }, ...envelope }) as Session
}
