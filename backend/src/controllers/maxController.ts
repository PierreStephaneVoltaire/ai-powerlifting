import { GetCommand, UpdateCommand, PutCommand } from '@aws-sdk/lib-dynamodb'
import { docClient, TABLE } from '../db/dynamo'
import { AppError } from '../middleware/errorHandler'
import type { MaxEntry, MaxHistoryStore } from '@powerlifting/types'

async function resolveVersionSk(pk: string, version: string): Promise<string> {
  if (version !== 'current') return `program#${version}`

  const pointerCommand = new GetCommand({
    TableName: TABLE,
    Key: {
      pk,
      sk: 'program#current',
    },
  })

  const pointerResult = await docClient.send(pointerCommand)
  return (pointerResult.Item as any)?.ref_sk || 'program#v001'
}

export async function getMaxHistory(pk: string, version: string): Promise<MaxHistoryStore> {
  const command = new GetCommand({
    TableName: TABLE,
    Key: {
      pk,
      sk: `max_history#${version}`,
    },
  })

  const result = await docClient.send(command)

  if (!result.Item) {
    // Return empty history if not found
    return {
      pk,
      sk: `max_history#${version}`,
      entries: [],
      updated_at: new Date().toISOString(),
    }
  }

  return result.Item as MaxHistoryStore
}

export async function addMaxEntry(pk: string, version: string, entry: MaxEntry): Promise<void> {
  const history = await getMaxHistory(pk, version)

  history.entries.push(entry)
  history.entries.sort((a, b) => b.date.localeCompare(a.date)) // Sort descending by date
  history.updated_at = new Date().toISOString()

  const command = new PutCommand({
    TableName: TABLE,
    Item: history,
  })

  await docClient.send(command)
}

export async function updateTargetMaxes(
  pk: string,
  version: string,
  maxes: { squat_kg: number; bench_kg: number; deadlift_kg: number }
): Promise<void> {
  const sk = await resolveVersionSk(pk, version)
  const command = new UpdateCommand({
    TableName: TABLE,
    Key: {
      pk,
      sk,
    },
    UpdateExpression: `SET
      #meta.target_squat_kg = :squat,
      #meta.target_bench_kg = :bench,
      #meta.target_dl_kg = :dl,
      #meta.target_total_kg = :total,
      #meta.updated_at = :now`,
    ExpressionAttributeNames: {
      '#meta': 'meta',
    },
    ExpressionAttributeValues: {
      ':squat': maxes.squat_kg,
      ':bench': maxes.bench_kg,
      ':dl': maxes.deadlift_kg,
      ':total': maxes.squat_kg + maxes.bench_kg + maxes.deadlift_kg,
      ':now': new Date().toISOString(),
    },
  })

  await docClient.send(command)
}

export async function getTargetMaxes(pk: string, version: string): Promise<{
  squat_kg: number
  bench_kg: number
  deadlift_kg: number
  total_kg: number
}> {
  const sk = await resolveVersionSk(pk, version)
  const command = new GetCommand({
    TableName: TABLE,
    Key: {
      pk,
      sk,
    },
    ProjectionExpression: '#meta.target_squat_kg, #meta.target_bench_kg, #meta.target_dl_kg, #meta.target_total_kg',
    ExpressionAttributeNames: {
      '#meta': 'meta',
    },
  })

  const result = await docClient.send(command)

  if (!result.Item) {
    throw new AppError(`Program version ${version} not found`, 404)
  }

  const meta = result.Item.meta as any
  return {
    squat_kg: meta.target_squat_kg,
    bench_kg: meta.target_bench_kg,
    deadlift_kg: meta.target_dl_kg,
    total_kg: meta.target_total_kg,
  }
}
