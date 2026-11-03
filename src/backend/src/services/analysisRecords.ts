import { DynamoDBClient } from '@aws-sdk/client-dynamodb'
import { DynamoDBDocumentClient, GetCommand, PutCommand } from '@aws-sdk/lib-dynamodb'
import { gzipSync, gunzipSync } from 'node:zlib'

const client = DynamoDBDocumentClient.from(new DynamoDBClient({ region: process.env.AWS_REGION || 'ca-central-1' }), { marshallOptions: { removeUndefinedValues: true } })
const TableName = process.env.ANALYSIS_CACHE_TABLE_NAME || 'if-powerlifting-analysis-cache'

export async function readAnalysisRecord<T>(athlete: string, key: string): Promise<T | null> {
  const { Item } = await client.send(new GetCommand({ TableName, Key: { pk: `analysis#${athlete}`, sk: key }, ConsistentRead: true }))
  if (!Item?.payload) return null
  return JSON.parse(gunzipSync(Buffer.from(Item.payload, 'base64')).toString()) as T
}

export async function writeAnalysisRecord(athlete: string, key: string, value: unknown, createOnly = false): Promise<boolean> {
  const payload = gzipSync(JSON.stringify(value)).toString('base64')
  if (Buffer.byteLength(payload) > 350000) throw new Error('Analysis record exceeds the storage limit')
  try {
    await client.send(new PutCommand({ TableName, Item: { pk: `analysis#${athlete}`, sk: key, payload }, ...(createOnly ? { ConditionExpression: 'attribute_not_exists(pk)' } : {}) }))
    return true
  } catch (error) {
    if (createOnly && error instanceof Error && error.name === 'ConditionalCheckFailedException') return false
    throw error
  }
}
