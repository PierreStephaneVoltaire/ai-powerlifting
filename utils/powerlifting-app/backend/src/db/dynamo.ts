import { DynamoDBClient } from '@aws-sdk/client-dynamodb'
import { DynamoDBDocumentClient } from '@aws-sdk/lib-dynamodb'

const client = new DynamoDBClient({
  region: process.env.AWS_REGION || 'ca-central-1',
  credentials: process.env.AWS_ACCESS_KEY_ID && process.env.AWS_SECRET_ACCESS_KEY
    ? {
        accessKeyId: process.env.AWS_ACCESS_KEY_ID,
        secretAccessKey: process.env.AWS_SECRET_ACCESS_KEY,
      }
    : undefined,
})

export const docClient = DynamoDBDocumentClient.from(client)
export const TABLE = process.env.DYNAMO_TABLE || process.env.DYNAMODB_TABLE || 'if-health'
export const SESSION_TABLE = process.env.IF_SESSIONS_TABLE_NAME || 'if-sessions'
export const USER_TABLE = process.env.IF_USER_TABLE || 'if-user'
