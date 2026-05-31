import { DynamoDBClient } from '@aws-sdk/client-dynamodb'
import { DynamoDBDocumentClient } from '@aws-sdk/lib-dynamodb'

/**
 * DynamoDB client — no hardcoded credentials.
 * In a pod the default credential chain (IAM role / env vars) is used automatically.
 */
const client = new DynamoDBClient({
  region: process.env.AWS_REGION || 'ca-central-1',
})

export const docClient = DynamoDBDocumentClient.from(client)
export const USER_TABLE = process.env.IF_USER_TABLE || 'if-user'
