import { QueryCommand, DeleteCommand, PutCommand } from '@aws-sdk/lib-dynamodb'
import { docClient, POWERLIFTING_GOALS_TABLE } from '../db/dynamo'
import type {
  AgeCategory,
  AthleteGoal,
  GoalPriority,
  GoalType,
  StoredGoal,
} from '@powerlifting/types'
import { randomUUID } from 'crypto'

const GOAL_TYPE_VALUES: ReadonlyArray<GoalType> = [
  'hit_total',
  'qualify_for_federation',
  'peak_for_meet',
  'conservative_pr',
  'competition_exposure',
  'improve_dots',
  'improve_ipf_gl',
  'custom',
]

const GOAL_PRIORITY_VALUES: ReadonlyArray<GoalPriority> = ['primary', 'secondary', 'optional']

const AGE_CATEGORY_VALUES: ReadonlyArray<AgeCategory> = [
  'open',
  'subjunior',
  'junior',
  'master1',
  'master2',
  'master3',
  'master4',
]

function newGoalId(): string {
  return `goal-${Date.now().toString(36)}-${Math.floor(Math.random() * 1e9).toString(36)}`
}

function normalizeGoalType(value: unknown): GoalType {
  return (GOAL_TYPE_VALUES as ReadonlyArray<string>).includes(String(value))
    ? (value as GoalType)
    : 'custom'
}

function normalizeGoalPriority(value: unknown): GoalPriority {
  return (GOAL_PRIORITY_VALUES as ReadonlyArray<string>).includes(String(value))
    ? (value as GoalPriority)
    : 'secondary'
}

function normalizeGoal(raw: unknown): AthleteGoal | null {
  if (!raw || typeof raw !== 'object') return null
  const r = raw as Record<string, unknown>
  const id = typeof r.id === 'string' && r.id.length > 0 ? r.id : newGoalId()
  const title = typeof r.title === 'string' ? r.title : ''
  const goalType = normalizeGoalType(r.goal_type)
  const priority = normalizeGoalPriority(r.priority)
  const out: AthleteGoal = { id, title, goal_type: goalType, priority }

  if (typeof r.target_date === 'string' && r.target_date) out.target_date = r.target_date
  if (Array.isArray(r.target_competition_ids)) {
    const ids = r.target_competition_ids.filter((v): v is string => typeof v === 'string' && v.length > 0)
    if (ids.length) out.target_competition_ids = [...new Set(ids)]
  }
  if (typeof r.target_total_kg === 'number' && Number.isFinite(r.target_total_kg) && r.target_total_kg > 0) {
    out.target_total_kg = r.target_total_kg
  }
  if (typeof r.target_dots === 'number' && Number.isFinite(r.target_dots) && r.target_dots > 0) {
    out.target_dots = r.target_dots
  }
  if (typeof r.target_ipf_gl === 'number' && Number.isFinite(r.target_ipf_gl) && r.target_ipf_gl > 0) {
    out.target_ipf_gl = r.target_ipf_gl
  }
  if (Array.isArray(r.target_federation_ids)) {
    const ids = r.target_federation_ids.filter((v): v is string => typeof v === 'string' && v.length > 0)
    if (ids.length) out.target_federation_ids = [...new Set(ids)]
  }
  if (Array.isArray(r.target_weight_class_kg)) {
    const wcs = r.target_weight_class_kg.filter((v): v is number => typeof v === 'number' && Number.isFinite(v) && v > 0)
    if (wcs.length) out.target_weight_class_kg = [...new Set(wcs)]
  }
  if (typeof r.age_class === 'string' && AGE_CATEGORY_VALUES.includes(r.age_class as AgeCategory)) {
    out.age_class = r.age_class as AgeCategory
  }
  if (typeof r.notes === 'string') out.notes = r.notes

  return out
}

function stripStoredFields(g: StoredGoal): AthleteGoal {
  const { id: _id, target_competition_ids, created_at, updated_at, ...rest } = g
  return rest as AthleteGoal
}

function buildStoredGoal(g: AthleteGoal, id: string, createdAt?: string): StoredGoal {
  const now = new Date().toISOString()
  return {
    ...g,
    id,
    target_competition_ids: g.target_competition_ids ?? [],
    created_at: createdAt ?? now,
    updated_at: now,
  }
}

async function queryGoals(pk: string): Promise<StoredGoal[]> {
  const items: StoredGoal[] = []
  let lastKey: Record<string, unknown> | undefined
  do {
    const resp = await docClient.send(new QueryCommand({
      TableName: POWERLIFTING_GOALS_TABLE,
      KeyConditionExpression: 'pk = :pk AND begins_with(sk, :prefix)',
      ExpressionAttributeValues: { ':pk': pk, ':prefix': 'GOAL#' },
      ExclusiveStartKey: lastKey,
    }))
    for (const it of resp.Items ?? []) items.push(it as StoredGoal)
    lastKey = resp.LastEvaluatedKey
  } while (lastKey)
  return items
}

export async function getGoals(pk: string): Promise<AthleteGoal[]> {
  const items = await queryGoals(pk)
  return items
    .map((it) => normalizeGoal(stripStoredFields(it)))
    .filter((g): g is AthleteGoal => g !== null)
}

export async function updateGoals(
  pk: string,
  goals: unknown[],
): Promise<void> {
  const userPk = pk
  const existing = await queryGoals(userPk)
  const byId = new Map<string, StoredGoal>()
  for (const sg of existing) byId.set(sg.id, sg)
  const incomingIds = new Set<string>()
  const now = new Date().toISOString()

  for (const raw of goals) {
    const normalized = normalizeGoal(raw)
    if (!normalized) continue
    const id = normalized.id
    if (byId.has(id)) {
      incomingIds.add(id)
      const cur = byId.get(id)!
      const merged: StoredGoal = {
        ...buildStoredGoal(normalized, id, cur.created_at),
        target_competition_ids: cur.target_competition_ids ?? [],
      }
      await docClient.send(new PutCommand({
        TableName: POWERLIFTING_GOALS_TABLE,
        Item: { ...merged, pk: userPk, sk: `GOAL#${id}` },
      }))
    } else {
      const newId = id || randomUUID()
      incomingIds.add(newId)
      const fresh = buildStoredGoal(normalized, newId)
      fresh.updated_at = now
      await docClient.send(new PutCommand({
        TableName: POWERLIFTING_GOALS_TABLE,
        Item: { ...fresh, pk: userPk, sk: `GOAL#${newId}` },
      }))
    }
  }

  for (const sg of existing) {
    if (!incomingIds.has(sg.id)) {
      await docClient.send(new DeleteCommand({
        TableName: POWERLIFTING_GOALS_TABLE,
        Key: { pk: userPk, sk: `GOAL#${sg.id}` },
      }))
    }
  }
}
