import { invokeLambda } from '../utils/lambda'
import { AppError } from '../middleware/errorHandler'
import type { Session, Exercise, SessionStatus, SessionWellness } from '@powerlifting/types'

async function fetchCurrent(pk: string, date: string, index: number): Promise<Session> {
  const session = await invokeLambda('pod_sessions', { function: 'session_get',  pk, date, index })
  if (!session) throw new AppError(`Session at index ${index} not found`, 404)
  return session as Session
}

export async function createSession(
  pk: string,
  _version: string,
  session: Session,
): Promise<void> {
  await invokeLambda('pod_sessions', { function: 'session_create',  pk, session })
}

export async function deleteSession(
  pk: string,
  _version: string,
  date: string,
  index: number,
): Promise<void> {
  await invokeLambda('pod_sessions', { function: 'session_delete',  pk, date, index })
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
): Promise<void> {
  await invokeLambda('pod_sessions', { function: 'session_replace',  pk, date, index, session })
}

export async function rescheduleSession(
  pk: string,
  _version: string,
  date: string,
  index: number,
  newDate: string,
  newDay: string,
): Promise<void> {
  await invokeLambda('pod_sessions', { function: 'session_patch',  pk, date, index, patch: { date: newDate, day: newDay } })
}

export async function completeSession(
  pk: string,
  _version: string,
  date: string,
  index: number,
  data: { rpe?: number; bodyWeightKg?: number; notes?: string; wellness?: SessionWellness | undefined },
): Promise<void> {
  const current = await fetchCurrent(pk, date, index)
  await invokeLambda('pod_sessions', { function: 'session_patch', 
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
  await invokeLambda('pod_sessions', { function: 'session_patch', 
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
  await invokeLambda('pod_sessions', { function: 'session_patch', 
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
  await invokeLambda('pod_sessions', { function: 'session_patch',  pk, date, index, patch: { exercises } })
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
  await invokeLambda('pod_sessions', { function: 'session_patch',  pk, date, index, patch: { exercises } })
}
