import { GetCommand, PutCommand } from '@aws-sdk/lib-dynamodb'
import { docClient, TABLE } from '../db/dynamo'
import type { WeightEntry, WeightLogStore } from '@powerlifting/types'

/**
 * Get weight log for a program version
 */
export async function getWeightLog(pk: string, version: string): Promise<WeightLogStore> {
  const command = new GetCommand({
    TableName: TABLE,
    Key: {
      pk,
      sk: `weight_log#${version}`,
    },
  })

  const result = await docClient.send(command)

  if (!result.Item) {
    // Return empty log if not found
    return {
      pk,
      sk: `weight_log#${version}`,
      entries: [],
      updated_at: new Date().toISOString(),
    }
  }

  return result.Item as WeightLogStore
}

/**
 * Add a weight entry
 */
export async function addWeightEntry(
  pk: string,
  version: string,
  entry: WeightEntry
): Promise<void> {
  const log = await getWeightLog(pk, version)

  // Check if entry for this date already exists
  const existingIndex = log.entries.findIndex(e => e.date === entry.date)

  if (existingIndex >= 0) {
    // Update existing entry
    log.entries[existingIndex] = entry
  } else {
    // Add new entry
    log.entries.push(entry)
  }

  // Sort by date descending
  log.entries.sort((a, b) => b.date.localeCompare(a.date))
  log.updated_at = new Date().toISOString()

  const command = new PutCommand({
    TableName: TABLE,
    Item: log,
  })

  await docClient.send(command)
}

/**
 * Remove a weight entry by date
 */
export async function removeWeightEntry(
  pk: string,
  version: string,
  date: string
): Promise<void> {
  const log = await getWeightLog(pk, version)

  log.entries = log.entries.filter(e => e.date !== date)
  log.updated_at = new Date().toISOString()

  const command = new PutCommand({
    TableName: TABLE,
    Item: log,
  })

  await docClient.send(command)
}
