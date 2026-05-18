import { GetCommand, UpdateCommand } from '@aws-sdk/lib-dynamodb'
import { docClient, TABLE } from '../db/dynamo'
import { AppError } from '../middleware/errorHandler'
import type { BlockNote } from '@powerlifting/types'

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

export async function getBlockNotes(pk: string, version: string): Promise<BlockNote[]> {
  const sk = await resolveVersionSk(pk, version)

  const getCommand = new GetCommand({
    TableName: TABLE,
    Key: { pk, sk },
    ProjectionExpression: '#meta.block_notes, block_notes',
    ExpressionAttributeNames: { '#meta': 'meta' },
  })

  const result = await docClient.send(getCommand)

  if (!result.Item) {
    throw new AppError(`Program version ${version} not found`, 404)
  }

  const metaNotes = (result.Item.meta as { block_notes?: unknown } | undefined)?.block_notes
  const legacyNotes = result.Item.block_notes
  if (Array.isArray(metaNotes) && (metaNotes.length > 0 || !Array.isArray(legacyNotes))) {
    return metaNotes as BlockNote[]
  }
  return (legacyNotes ?? []) as BlockNote[]
}

export async function updateBlockNotes(
  pk: string,
  version: string,
  blockNotes: BlockNote[]
): Promise<void> {
  const sk = await resolveVersionSk(pk, version)

  const updateCommand = new UpdateCommand({
    TableName: TABLE,
    Key: { pk, sk },
    UpdateExpression: 'SET #meta.block_notes = :notes, #meta.updated_at = :now REMOVE block_notes',
    ExpressionAttributeNames: { '#meta': 'meta' },
    ExpressionAttributeValues: {
      ':notes': blockNotes,
      ':now': new Date().toISOString(),
    },
  })

  await docClient.send(updateCommand)
}
