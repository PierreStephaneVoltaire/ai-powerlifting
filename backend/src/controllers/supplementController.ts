import { GetCommand, UpdateCommand } from '@aws-sdk/lib-dynamodb'
import { docClient, TABLE } from '../db/dynamo'
import { AppError } from '../middleware/errorHandler'
import type { SupplementPhase } from '@powerlifting/types'

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
 * Update all supplement phases
 */
export async function updateSupplementPhases(
  pk: string,
  version: string,
  phases: SupplementPhase[]
): Promise<void> {
  const sk = await resolveVersionSk(pk, version)

  const updateCommand = new UpdateCommand({
    TableName: TABLE,
    Key: { pk, sk },
    UpdateExpression: 'SET supplement_phases = :phases, #meta.updated_at = :now',
    ExpressionAttributeNames: { '#meta': 'meta' },
    ExpressionAttributeValues: {
      ':phases': phases,
      ':now': new Date().toISOString(),
    },
  })

  await docClient.send(updateCommand)
}

/**
 * Get supplement phases
 */
export async function getSupplementPhases(
  pk: string,
  version: string
): Promise<SupplementPhase[]> {
  const sk = await resolveVersionSk(pk, version)

  const getCommand = new GetCommand({
    TableName: TABLE,
    Key: { pk, sk },
    ProjectionExpression: 'supplement_phases',
  })

  const result = await docClient.send(getCommand)

  if (!result.Item) {
    throw new AppError(`Program version ${version} not found`, 404)
  }

  return (result.Item.supplement_phases ?? []) as SupplementPhase[]
}
