import { GetCommand, UpdateCommand } from '@aws-sdk/lib-dynamodb'
import { docClient, TABLE } from '../db/dynamo'
import { AppError } from '../middleware/errorHandler'
import type { DietNote } from '@powerlifting/types'

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
 * Update all diet notes
 */
export async function updateDietNotes(
  pk: string,
  version: string,
  dietNotes: DietNote[]
): Promise<void> {
  const sk = await resolveVersionSk(pk, version)

  const updateCommand = new UpdateCommand({
    TableName: TABLE,
    Key: { pk, sk },
    UpdateExpression: 'SET diet_notes = :notes, #meta.updated_at = :now',
    ExpressionAttributeNames: { '#meta': 'meta' },
    ExpressionAttributeValues: {
      ':notes': dietNotes,
      ':now': new Date().toISOString(),
    },
  })

  await docClient.send(updateCommand)
}

/**
 * Get diet notes
 */
export async function getDietNotes(pk: string, version: string): Promise<DietNote[]> {
  const sk = await resolveVersionSk(pk, version)

  const getCommand = new GetCommand({
    TableName: TABLE,
    Key: { pk, sk },
    ProjectionExpression: 'diet_notes',
  })

  const result = await docClient.send(getCommand)

  if (!result.Item) {
    throw new AppError(`Program version ${version} not found`, 404)
  }

  return (result.Item.diet_notes ?? []) as DietNote[]
}
