import { GetCommand, QueryCommand, UpdateCommand, DeleteCommand, PutCommand } from '@aws-sdk/lib-dynamodb'
import { docClient, POWERLIFTING_GOALS_TABLE } from '../db/dynamo'
import { AppError } from '../middleware/errorHandler'
import type { AthleteGoal, StoredGoal } from '@powerlifting/types'
import { randomUUID } from 'crypto'

function stripStoredFields(g: StoredGoal): AthleteGoal {
  const { id: _id, target_competition_ids, created_at, updated_at, ...rest } = g
  return rest as AthleteGoal
}

function addStoredFields(g: AthleteGoal, id: string): StoredGoal {
  const now = new Date().toISOString()
  return { ...g, id, target_competition_ids: [], created_at: now, updated_at: now }
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

export async function getGoals(pk: string, version: string): Promise<AthleteGoal[]> {
  const items = await queryGoals(pk)
  return items.map(stripStoredFields)
}

export async function updateGoals(
  pk: string,
  version: string,
  goals: AthleteGoal[],
): Promise<void> {
  const userPk = pk
  const existing = await queryGoals(userPk)
  const byId = new Map<string, StoredGoal>()
  for (const sg of existing) byId.set(sg.id, sg)
  const incomingIds = new Set<string>()

  for (const g of goals) {
    const id = (g as { id?: string }).id
    if (id && byId.has(id)) {
      incomingIds.add(id)
      const cur = byId.get(id)!
      const merged: StoredGoal = {
        ...cur,
        ...g,
        id,
        target_competition_ids: cur.target_competition_ids ?? [],
        created_at: cur.created_at,
        updated_at: new Date().toISOString(),
      }
      await docClient.send(new PutCommand({
        TableName: POWERLIFTING_GOALS_TABLE,
        Item: merged,
      }))
    } else {
      const newId = (g as { id?: string }).id || randomUUID()
      incomingIds.add(newId)
      const fresh = addStoredFields(g, newId)
      await docClient.send(new PutCommand({
        TableName: POWERLIFTING_GOALS_TABLE,
        Item: fresh,
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
