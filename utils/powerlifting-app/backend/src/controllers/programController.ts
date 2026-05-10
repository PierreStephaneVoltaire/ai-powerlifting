import { GetCommand, QueryCommand, PutCommand, UpdateCommand, DeleteCommand } from '@aws-sdk/lib-dynamodb'
import crypto from 'crypto'
import { docClient, TABLE } from '../db/dynamo'
import { transformProgram } from '../db/transforms'
import { AppError } from '../middleware/errorHandler'
import {
  createSession as createStoredSession,
  listSessions,
  patchSessionAt,
  replaceProgramSessions,
} from '../services/sessionStore'
import type { Program, ProgramListItem, Phase, Session, PlannedExercise, LiftProfile } from '@powerlifting/types'

/**
 * Resolve a version string to the actual SK.
 * If version is "current", look up the pointer to get the real version.
 */
async function resolveVersionSk(pk: string, version: string): Promise<string> {
  if (version === 'current') {
    // Look up the pointer
    const pointerCommand = new GetCommand({
      TableName: TABLE,
      Key: {
        pk,
        sk: 'program#current',
      },
    })

    const pointerResult = await docClient.send(pointerCommand)

    if (!pointerResult.Item) {
      // No pointer exists, fall back to v001
      return 'program#v001'
    }

    // Return the referenced SK
    return (pointerResult.Item as any).ref_sk || 'program#v001'
  }

  return `program#${version}`
}

/**
 * Get a specific program version
 */
export async function getProgram(pk: string, version: string): Promise<Program> {
  const sk = await resolveVersionSk(pk, version)

  const command = new GetCommand({
    TableName: TABLE,
    Key: {
      pk,
      sk,
    },
  })

  const result = await docClient.send(command)

  if (!result.Item) {
    throw new AppError(`Program version ${version} not found`, 404)
  }

  const program = transformProgram(result.Item as Record<string, unknown>)
  program.sessions = await listSessions(pk, sk, program.phases)
  return program
}

/**
 * List all program versions
 */
export async function listPrograms(pk: string): Promise<ProgramListItem[]> {
  const command = new QueryCommand({
    TableName: TABLE,
    KeyConditionExpression: 'pk = :pk AND begins_with(sk, :prefix)',
    ExpressionAttributeValues: {
      ':pk': pk,
      ':prefix': 'program#',
    },
  })

  const result = await docClient.send(command)

  // Find the current pointer
  const pointer = (result.Items || []).find((item: any) => item.sk === 'program#current')
  const currentRefSk = pointer?.ref_sk || 'program#v001'

  // Filter to only actual programs (not pointers) and map to list items
  const programs = (result.Items || [])
    .filter((item: any) => item.sk !== 'program#current' && item.meta)
    .map((item: any) => ({
      version: item.sk.replace('program#', ''),
      sk: item.sk,
      comp_date: item.meta?.comp_date || '',
      updated_at: item.meta?.updated_at || '',
      version_label: item.meta?.version_label || item.sk.replace('program#', ''),
      is_current: item.sk === currentRefSk,
    }))

  // Add "current" as the first option if there's a pointer
  if (pointer) {
    const currentProgram = programs.find(p => p.is_current)
    programs.unshift({
      version: 'current',
      sk: currentRefSk,
      comp_date: currentProgram?.comp_date || '',
      updated_at: currentProgram?.updated_at || '',
      version_label: currentProgram?.version_label ? `Current (${currentProgram.version_label})` : 'Current',
      is_current: true,
    })
  }

  return programs
}

/**
 * Fork a program to a new version
 */
export async function forkProgram(
  pk: string,
  currentVersion: string,
  label?: string
): Promise<string> {
  // Get current program
  const current = await getProgram(pk, currentVersion)

  // Find next version number
  const all = await listPrograms(pk)
  const nums = all.map(v => parseInt(v.version.replace(/\D/g, ''), 10)).filter(n => !isNaN(n))
  const next = nums.length > 0 ? Math.max(...nums) + 1 : 1
  const newVersion = `v${String(next).padStart(3, '0')}`

  // Clone with updated metadata
  const forked: Program = {
    ...current,
    sk: `program#${newVersion}`,
    meta: {
      ...current.meta,
      version_label: label || newVersion,
      updated_at: new Date().toISOString(),
      change_log: [
        ...current.meta.change_log,
        {
          action: 'forked_from',
          source: currentVersion,
          date: new Date().toISOString(),
        },
      ],
    },
  }
  const { sessions = [], ...programItem } = forked

  // Write new item
  const command = new PutCommand({
    TableName: TABLE,
    Item: programItem,
  })

  await docClient.send(command)
  await replaceProgramSessions(pk, `program#${newVersion}`, sessions, forked.phases || [])
  return newVersion
}

/**
 * Update a single meta field
 */
export async function updateMetaField(
  pk: string,
  version: string,
  field: string,
  value: unknown
): Promise<void> {
  const allowedFields = [
    'program_name', 'program_start', 'comp_date', 'federation', 'practicing_for',
    'version_label', 'sex', 'weight_class_kg', 'weight_class_confirm_by',
    'current_body_weight_kg', 'current_body_weight_lb',
    'target_squat_kg', 'target_bench_kg', 'target_dl_kg', 'target_total_kg',
    'attempt_pct', 'height_cm', 'arm_wingspan_cm', 'leg_length_cm',
    'block_start_maxes', 'program_week_start_day', 'block_week_start_days',
  ]

  if (!allowedFields.includes(field)) {
    throw new AppError(`Cannot update field: ${field}`, 400)
  }

  const sk = await resolveVersionSk(pk, version)

  const command = new UpdateCommand({
    TableName: TABLE,
    Key: {
      pk,
      sk,
    },
    UpdateExpression: `SET #meta.#field = :value, #meta.updated_at = :now`,
    ExpressionAttributeNames: {
      '#meta': 'meta',
      '#field': field,
    },
    ExpressionAttributeValues: {
      ':value': value,
      ':now': new Date().toISOString(),
    },
  })

  await docClient.send(command)
}

/**
 * Update body weight
 */
export async function updateBodyWeight(
  pk: string,
  version: string,
  weightKg: number
): Promise<void> {
  const weightLb = weightKg * 2.20462
  const sk = await resolveVersionSk(pk, version)

  const command = new UpdateCommand({
    TableName: TABLE,
    Key: {
      pk,
      sk,
    },
    UpdateExpression: `SET #meta.current_body_weight_kg = :kg, #meta.current_body_weight_lb = :lb, #meta.updated_at = :now`,
    ExpressionAttributeNames: {
      '#meta': 'meta',
    },
    ExpressionAttributeValues: {
      ':kg': weightKg,
      ':lb': weightLb,
      ':now': new Date().toISOString(),
    },
  })

  await docClient.send(command)
}

/**
 * Update phases.
 * If `block` is provided: replaces only the phases scoped to that block, leaving
 * other blocks' phases untouched. Incoming phases without a block are tagged with `block`.
 * If `block` is omitted: full replace of the phases array; each phase keeps its own `block` field.
 */
export async function updatePhases(
  pk: string,
  version: string,
  phases: Phase[],
  block?: string
): Promise<void> {
  const sk = await resolveVersionSk(pk, version)

  let nextPhases: Phase[]
  if (block) {
    const getCommand = new GetCommand({
      TableName: TABLE,
      Key: { pk, sk },
      ProjectionExpression: 'phases',
    })
    const result = await docClient.send(getCommand)
    if (!result.Item) {
      throw new AppError(`Program version ${version} not found`, 404)
    }
    const existing = (result.Item.phases ?? []) as Phase[]
    const otherBlocks = existing.filter(p => (p.block ?? 'current') !== block)
    const incoming = phases.map(p => ({ ...p, block: p.block ?? block }))
    nextPhases = [...otherBlocks, ...incoming]
  } else {
    nextPhases = phases.map(p => ({ ...p, block: p.block ?? 'current' }))
  }

  const command = new UpdateCommand({
    TableName: TABLE,
    Key: {
      pk,
      sk,
    },
    UpdateExpression: `SET phases = :phases, #meta.updated_at = :now`,
    ExpressionAttributeNames: {
      '#meta': 'meta',
    },
    ExpressionAttributeValues: {
      ':phases': nextPhases,
      ':now': new Date().toISOString(),
    },
  })

  await docClient.send(command)
}

/**
 * Batch create planned sessions for a week.
 * Creates one session per day entry, all with status "planned" and the same planned_exercises.
 */
export async function batchCreateWeek(
  pk: string,
  version: string,
  weekNumber: number,
  weekLabel: string,
  days: Array<{ date: string; day: string }>,
  phaseName: string,
  exercises: PlannedExercise[]
): Promise<void> {
  const sk = await resolveVersionSk(pk, version)
  const getCommand = new GetCommand({
    TableName: TABLE,
    Key: { pk, sk },
    ProjectionExpression: 'phases',
  })

  const result = await docClient.send(getCommand)

  if (!result.Item) {
    throw new AppError(`Program version ${version} not found`, 404)
  }

  const phases = (result.Item.phases ?? []) as Phase[]
  const sessions = await listSessions(pk, sk, phases)

  const targetBlock = 'current'
  const phase = phases.find(p =>
    (p.block ?? 'current') === targetBlock &&
    weekNumber >= p.start_week &&
    weekNumber <= p.end_week
  ) ?? { name: phaseName, intent: '', start_week: weekNumber, end_week: weekNumber, block: targetBlock }

  const existingDates = new Set(sessions.map(s => s.date))
  for (const day of days) {
    if (existingDates.has(day.date)) {
      throw new AppError(`Session with date ${day.date} already exists`, 400)
    }
  }

  const newSessions: Session[] = days.map(day => ({
    id: crypto.randomUUID(),
    date: day.date,
    day: day.day,
    week: weekLabel,
    week_number: weekNumber,
    phase,
    status: 'planned',
    completed: false,
    planned_exercises: exercises,
    exercises: [],
    session_notes: '',
    session_rpe: null,
    body_weight_kg: null,
    block: 'current',
  }))

  for (const session of newSessions) {
    await createStoredSession(pk, sk, session, phases)
  }
}

/**
 * Update lift profiles (squat/bench/deadlift style, sticking points, muscle dominance, volume tolerance).
 */
export async function updateLiftProfiles(
  pk: string,
  version: string,
  liftProfiles: LiftProfile[]
): Promise<void> {
  const sk = await resolveVersionSk(pk, version)

  const command = new UpdateCommand({
    TableName: TABLE,
    Key: {
      pk,
      sk,
    },
    UpdateExpression: 'SET lift_profiles = :profiles, #meta.updated_at = :now',
    ExpressionAttributeNames: {
      '#meta': 'meta',
    },
    ExpressionAttributeValues: {
      ':profiles': liftProfiles,
      ':now': new Date().toISOString(),
    },
  })

  await docClient.send(command)
}

/**
 * Update planned exercises on a session.
 */
export async function updatePlannedExercises(
  pk: string,
  version: string,
  date: string,
  index: number,
  plannedExercises: PlannedExercise[]
): Promise<void> {
  const sk = await resolveVersionSk(pk, version)
  const getCommand = new GetCommand({
    TableName: TABLE,
    Key: { pk, sk },
    ProjectionExpression: 'phases',
  })

  const result = await docClient.send(getCommand)

  if (!result.Item) {
    throw new AppError(`Program version ${version} not found`, 404)
  }

  const phases = (result.Item.phases ?? []) as Phase[]
  const sessions = await listSessions(pk, sk, phases)

  if (index < 0 || index >= sessions.length) {
    throw new AppError(`Session at index ${index} not found`, 404)
  }
  if (sessions[index].date !== date) {
    throw new AppError(`Session at index ${index} has date ${sessions[index].date}, expected ${date}`, 409)
  }

  // Sync exercises from planned for incomplete sessions
  const existing = sessions[index]
  const syncExercises = !existing.completed
    ? plannedExercises.map(pe => ({
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

  await patchSessionAt(
    pk,
    sk,
    date,
    index,
    {
      planned_exercises: plannedExercises,
      ...(syncExercises !== existing.exercises ? { exercises: syncExercises } : {}),
    },
    phases,
  )
}

/**
 * Archive a program version
 */
export async function archiveProgram(pk: string, version: string): Promise<void> {
  const sk = await resolveVersionSk(pk, version)
  const now = new Date().toISOString()

  // Update program item
  await docClient.send(new UpdateCommand({
    TableName: TABLE,
    Key: { pk, sk },
    UpdateExpression: 'SET meta.archived = :a, meta.archived_at = :now',
    ExpressionAttributeValues: {
      ':a': true,
      ':now': now,
    },
  }))

  // Check if it's current
  const pointerCommand = new GetCommand({
    TableName: TABLE,
    Key: { pk, sk: 'program#current' },
  })
  const pointerResult = await docClient.send(pointerCommand)
  const currentSk = (pointerResult.Item as any)?.ref_sk

  if (currentSk === sk) {
    // Need to repoint current
    const allPrograms = await listPrograms(pk)
    const nonArchived = allPrograms.filter(p => !p.archived && p.sk !== sk)
    
    if (nonArchived.length > 0) {
      // Sort by SK descending (latest version first)
      nonArchived.sort((a, b) => b.sk.localeCompare(a.sk))
      const latest = nonArchived[0]
      const versionNum = parseInt(latest.sk.split('#v')[1], 10)

      await docClient.send(new PutCommand({
        TableName: TABLE,
        Item: {
          pk,
          sk: 'program#current',
          version: versionNum,
          ref_sk: latest.sk,
          updated_at: now,
        },
      }))
    } else {
      // No other programs, delete pointer
      await docClient.send(new DeleteCommand({
        TableName: TABLE,
        Key: { pk, sk: 'program#current' },
      }))
    }
  }
}

/**
 * Unarchive a program version
 */
export async function unarchiveProgram(pk: string, version: string): Promise<void> {
  const sk = await resolveVersionSk(pk, version)

  await docClient.send(new UpdateCommand({
    TableName: TABLE,
    Key: { pk, sk },
    UpdateExpression: 'SET meta.archived = :a, meta.archived_at = :null',
    ExpressionAttributeValues: {
      ':a': false,
      ':null': null,
    },
  }))
}
