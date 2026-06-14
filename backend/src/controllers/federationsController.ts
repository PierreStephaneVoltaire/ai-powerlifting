import { GetCommand, PutCommand, QueryCommand, UpdateCommand } from '@aws-sdk/lib-dynamodb'
import { docClient, POWERLIFTING_USER_FEDERATIONS_TABLE, TABLE } from '../db/dynamo'
import type { FederationLibrary, UserFederation, FederationRecord, QualificationStandard } from '@powerlifting/types'

const FEDERATIONS_SK = 'federations#v1'

// ─── New: list user federations from the new table ──────────────────────────
async function queryUserFeds(pk: string): Promise<UserFederation[]> {
  const items: UserFederation[] = []
  let lastKey: Record<string, unknown> | undefined
  do {
    const resp = await docClient.send(new QueryCommand({
      TableName: POWERLIFTING_USER_FEDERATIONS_TABLE,
      KeyConditionExpression: 'pk = :pk AND begins_with(sk, :prefix)',
      ExpressionAttributeValues: { ':pk': pk, ':prefix': 'FED#' },
      ExclusiveStartKey: lastKey,
    }))
    for (const it of resp.Items ?? []) items.push(it as UserFederation)
    lastKey = resp.LastEvaluatedKey
  } while (lastKey)
  return items
}

export async function listUserFederations(pk: string): Promise<UserFederation[]> {
  return queryUserFeds(pk)
}

// ─── New: patch a single user federation (user_status + notes only) ─────────
export async function patchUserFederation(
  pk: string,
  masterId: string,
  updates: { user_status?: 'active' | 'archived'; notes?: string },
): Promise<void> {
  const sets: string[] = []
  const values: Record<string, unknown> = {}

  if (updates.user_status !== undefined) {
    sets.push('user_status = :st')
    values[':st'] = updates.user_status
  }
  if (updates.notes !== undefined) {
    sets.push('notes = :n')
    values[':n'] = updates.notes
  }

  if (sets.length === 0) return

  sets.push('updated_at = :u')
  values[':u'] = new Date().toISOString()

  await docClient.send(new UpdateCommand({
    TableName: POWERLIFTING_USER_FEDERATIONS_TABLE,
    Key: { pk, sk: `FED#${masterId}` },
    UpdateExpression: 'SET ' + sets.join(', '),
    ExpressionAttributeValues: values,
  }))
}

// ─── Legacy: get federation library (reads from if-health for compat) ───────
function emptyLibrary(pk: string): FederationLibrary {
  return {
    pk,
    sk: FEDERATIONS_SK,
    updated_at: new Date().toISOString(),
    federations: [],
    qualification_standards: [],
  }
}

export async function getFederationLibrary(pk: string): Promise<FederationLibrary> {
  const result = await docClient.send(new GetCommand({
    TableName: TABLE,
    Key: { pk, sk: FEDERATIONS_SK },
  }))

  if (!result.Item) {
    return emptyLibrary(pk)
  }

  return result.Item as FederationLibrary
}

export async function updateFederationLibrary(
  pk: string,
  library: Pick<FederationLibrary, 'federations' | 'qualification_standards'>,
): Promise<FederationLibrary> {
  const nextLibrary: FederationLibrary = {
    pk,
    sk: FEDERATIONS_SK,
    updated_at: new Date().toISOString(),
    federations: library.federations ?? [],
    qualification_standards: library.qualification_standards ?? [],
  }

  await docClient.send(new PutCommand({
    TableName: TABLE,
    Item: nextLibrary,
  }))

  return nextLibrary
}

