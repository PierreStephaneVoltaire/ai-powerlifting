import { GetCommand } from '@aws-sdk/lib-dynamodb'
import { docClient, TABLE } from '../db/dynamo'
import { AppError } from '../middleware/errorHandler'
import type { Session, Exercise, Phase, SessionStatus, SessionWellness } from '@powerlifting/types'
import {
  createSession as createStoredSession,
  deleteSessionAt,
  getSession as getStoredSession,
  patchSessionAt,
  replaceSessionAt,
} from '../services/sessionStore'

/**
 * Resolve a version string to the actual SK.
 */
async function resolveVersionSk(pk: string, version: string): Promise<string> {
  if (version === 'current') {
    const pointerCommand = new GetCommand({
      TableName: TABLE,
      Key: { pk, sk: 'program#current' },
    })
    const pointerResult = await docClient.send(pointerCommand)
    if (!pointerResult.Item) return 'program#v001'
    return (pointerResult.Item as any).ref_sk || 'program#v001'
  }
  return `program#${version}`
}

async function loadPhases(pk: string, sk: string, version: string): Promise<Phase[]> {
  const result = await docClient.send(new GetCommand({
    TableName: TABLE,
    Key: { pk, sk },
    ProjectionExpression: 'phases',
  }))
  if (!result.Item) {
    throw new AppError(`Program version ${version} not found`, 404)
  }
  return (result.Item.phases ?? []) as Phase[]
}

/**
 * Create a new session
 */
export async function createSession(
  pk: string,
  version: string,
  session: Session
): Promise<void> {
  const sk = await resolveVersionSk(pk, version)
  const phases = await loadPhases(pk, sk, version)

  // Derive week_number and phase for the new session
  const weekMatch = session.week?.match(/W(\d+)/)
  const weekNumber = session.week_number || (weekMatch ? parseInt(weekMatch[1], 10) : 1)
  const sessionBlock = session.block ?? 'current'

  // Resolve phase scoped to the session's block
  let resolvedPhase: Phase = { name: 'Unknown', intent: '', start_week: weekNumber, end_week: weekNumber, block: sessionBlock }
  if (phases && phases.length > 0) {
    const phase = phases.find(p =>
      (p.block ?? 'current') === sessionBlock &&
      weekNumber >= p.start_week &&
      weekNumber <= p.end_week
    )
    if (phase) resolvedPhase = phase
  }

  const newSession: Session = {
    ...session,
    week_number: weekNumber,
    phase: resolvedPhase,
    block: sessionBlock,
  }

  await createStoredSession(pk, sk, newSession, phases)
}

/**
 * Delete a session by index
 */
export async function deleteSession(
  pk: string,
  version: string,
  date: string,
  index: number
): Promise<void> {
  const sk = await resolveVersionSk(pk, version)
  await deleteSessionAt(pk, sk, date, index)
}

export async function getSession(pk: string, version: string, date: string, index: number): Promise<Session | null> {
  const sk = await resolveVersionSk(pk, version)
  const phases = await loadPhases(pk, sk, version)
  return getStoredSession(pk, sk, date, index, phases)
}

/**
 * Update an entire session at a specific index
 */
export async function updateSession(
  pk: string,
  version: string,
  date: string,
  index: number,
  session: Session
): Promise<void> {
  const sk = await resolveVersionSk(pk, version)
  const phases = await loadPhases(pk, sk, version)
  await replaceSessionAt(pk, sk, date, index, session, phases)
}

/**
 * Reschedule a session to a new date
 */
export async function rescheduleSession(
  pk: string,
  version: string,
  date: string,
  index: number,
  newDate: string,
  newDay: string
): Promise<void> {
  const sk = await resolveVersionSk(pk, version)
  const phases = await loadPhases(pk, sk, version)
  await patchSessionAt(pk, sk, date, index, { date: newDate, day: newDay }, phases)
}

/**
 * Mark a session as complete with optional RPE and body weight
 */
export async function completeSession(
  pk: string,
  version: string,
  date: string,
  index: number,
  data: { rpe?: number; bodyWeightKg?: number; notes?: string; wellness?: SessionWellness | undefined }
): Promise<void> {
  const sk = await resolveVersionSk(pk, version)
  const phases = await loadPhases(pk, sk, version)
  const current = await getStoredSession(pk, sk, date, index, phases)
  await patchSessionAt(pk, sk, date, index, {
    completed: true,
    status: current.status === 'planned' ? 'completed' : current.status,
    session_rpe: data.rpe ?? current.session_rpe,
    body_weight_kg: data.bodyWeightKg ?? current.body_weight_kg,
    session_notes: data.notes ?? current.session_notes,
    wellness: data.wellness ?? current.wellness,
  }, phases)
}

/**
 * Update only the status field on a session
 */
export async function updateSessionStatus(
  pk: string,
  version: string,
  date: string,
  index: number,
  status: SessionStatus
): Promise<void> {
  const sk = await resolveVersionSk(pk, version)
  const phases = await loadPhases(pk, sk, version)
  const current = await getStoredSession(pk, sk, date, index, phases)
  await patchSessionAt(pk, sk, date, index, {
    status,
    completed: status === 'completed' || status === 'logged' ? true : current.completed,
  }, phases)
}

/**
 * Add an exercise to a session
 */
export async function addExercise(
  pk: string,
  version: string,
  date: string,
  index: number,
  exercise: Exercise
): Promise<void> {
  const sk = await resolveVersionSk(pk, version)
  const phases = await loadPhases(pk, sk, version)
  const session = await getStoredSession(pk, sk, date, index, phases)
  await patchSessionAt(pk, sk, date, index, {
    exercises: [...(session.exercises || []), exercise],
  }, phases)
}

/**
 * Remove an exercise from a session
 */
export async function removeExercise(
  pk: string,
  version: string,
  date: string,
  index: number,
  exerciseIndex: number
): Promise<void> {
  const sk = await resolveVersionSk(pk, version)
  const phases = await loadPhases(pk, sk, version)
  const session = await getStoredSession(pk, sk, date, index, phases)
  const exercises = [...(session.exercises || [])]
  if (exerciseIndex < 0 || exerciseIndex >= exercises.length) {
    throw new AppError(`Exercise index ${exerciseIndex} out of range`, 400)
  }

  exercises.splice(exerciseIndex, 1)
  await patchSessionAt(pk, sk, date, index, { exercises }, phases)
}

/**
 * Update a single field on an exercise
 */
export async function updateExerciseField(
  pk: string,
  version: string,
  date: string,
  index: number,
  exerciseIndex: number,
  field: keyof Exercise,
  value: unknown
): Promise<void> {
  const sk = await resolveVersionSk(pk, version)
  const phases = await loadPhases(pk, sk, version)
  const session = await getStoredSession(pk, sk, date, index, phases)
  const exercises = [...(session.exercises || [])]
  if (exerciseIndex < 0 || exerciseIndex >= exercises.length) {
    throw new AppError(`Exercise index ${exerciseIndex} out of range`, 400)
  }

  ;(exercises[exerciseIndex] as any)[field] = value
  await patchSessionAt(pk, sk, date, index, { exercises }, phases)
}
