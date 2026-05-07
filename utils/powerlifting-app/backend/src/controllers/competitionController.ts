import { GetCommand, UpdateCommand } from '@aws-sdk/lib-dynamodb'
import { docClient, TABLE } from '../db/dynamo'
import { AppError } from '../middleware/errorHandler'
import type { Competition, LastComp, LiftResults, PostMeetReport } from '@powerlifting/types'

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

/**
 * Get competitions
 */
export async function getCompetitions(pk: string, version: string): Promise<Competition[]> {
  const sk = await resolveVersionSk(pk, version)

  const getCommand = new GetCommand({
    TableName: TABLE,
    Key: { pk, sk },
    ProjectionExpression: 'competitions',
  })

  const result = await docClient.send(getCommand)

  if (!result.Item) {
    throw new AppError(`Program version ${version} not found`, 404)
  }

  return (result.Item.competitions ?? []) as Competition[]
}

/**
 * Update all competitions
 */
export async function updateCompetitions(
  pk: string,
  version: string,
  competitions: Competition[]
): Promise<void> {
  const sk = await resolveVersionSk(pk, version)

  const updateCommand = new UpdateCommand({
    TableName: TABLE,
    Key: { pk, sk },
    UpdateExpression: 'SET competitions = :competitions, #meta.updated_at = :now',
    ExpressionAttributeNames: { '#meta': 'meta' },
    ExpressionAttributeValues: {
      ':competitions': competitions,
      ':now': new Date().toISOString(),
    },
  })

  await docClient.send(updateCommand)
}

/**
 * Migrate last_comp from meta into competitions array.
 * This is a one-time migration that moves the historical competition
 * from meta.last_comp into the competitions array with status='completed'.
 */
export async function migrateLastComp(pk: string, version: string): Promise<Competition[]> {
  const sk = await resolveVersionSk(pk, version)

  const getCommand = new GetCommand({
    TableName: TABLE,
    Key: { pk, sk },
    ProjectionExpression: 'competitions, meta.last_comp',
  })

  const result = await docClient.send(getCommand)

  if (!result.Item) {
    throw new AppError(`Program version ${version} not found`, 404)
  }

  const competitions = (result.Item.competitions ?? []) as Competition[]
  const lastComp = (result.Item.meta as any)?.last_comp as LastComp | undefined

  // Check if migration already done (a completed competition with 2025 date exists)
  const alreadyMigrated = competitions.some(
    c => c.status === 'completed' && c.date?.startsWith('2025')
  )

  if (alreadyMigrated || !lastComp) {
    return competitions
  }

  // Create migrated competition entry
  const migratedComp: Competition = {
    name: 'Sep 2025 Comp',
    date: lastComp.date || '2025-09-01',
    federation: 'unknown',
    status: 'completed',
    weight_class_kg: lastComp.weight_class_kg,
    body_weight_kg: lastComp.body_weight_kg,
    results: lastComp.results,
    notes: '',
  }

  // Add to beginning of array (oldest first)
  const updatedCompetitions = [migratedComp, ...competitions]

  // Update DynamoDB
  const updateCommand = new UpdateCommand({
    TableName: TABLE,
    Key: { pk, sk },
    UpdateExpression: 'SET competitions = :competitions, #meta.updated_at = :now',
    ExpressionAttributeNames: { '#meta': 'meta' },
    ExpressionAttributeValues: {
      ':competitions': updatedCompetitions,
      ':now': new Date().toISOString(),
    },
  })

  await docClient.send(updateCommand)

  return updatedCompetitions
}

/**
 * Mark a competition as completed with actual results
 */
export async function completeCompetition(
  pk: string,
  version: string,
  compDate: string,
  results: LiftResults,
  bodyWeightKg: number,
  postMeetReport?: PostMeetReport
): Promise<void> {
  const sk = await resolveVersionSk(pk, version)

  const getCommand = new GetCommand({
    TableName: TABLE,
    Key: { pk, sk },
    ProjectionExpression: 'competitions',
  })

  const result = await docClient.send(getCommand)

  if (!result.Item) {
    throw new AppError(`Program version ${version} not found`, 404)
  }

  const competitions = (result.Item.competitions ?? []) as Competition[]
  const compIndex = competitions.findIndex(c => c.date === compDate)

  if (compIndex === -1) {
    throw new AppError(`Competition with date ${compDate} not found`, 404)
  }

  // Update competition with results
  competitions[compIndex] = {
    ...competitions[compIndex],
    status: 'completed',
    results,
    body_weight_kg: bodyWeightKg,
    ...(postMeetReport ? { post_meet_report: postMeetReport } : {}),
  }

  const updateCommand = new UpdateCommand({
    TableName: TABLE,
    Key: { pk, sk },
    UpdateExpression: 'SET competitions = :competitions, #meta.updated_at = :now',
    ExpressionAttributeNames: { '#meta': 'meta' },
    ExpressionAttributeValues: {
      ':competitions': competitions,
      ':now': new Date().toISOString(),
    },
  })

  await docClient.send(updateCommand)
}
