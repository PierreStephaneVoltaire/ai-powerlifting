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

export const POWERLIFTING_MASTER_COMPETITIONS_TABLE = process.env.POWERLIFTING_MASTER_COMPETITIONS_TABLE || 'if-powerlifting-master-competitions'
export const POWERLIFTING_USER_COMPETITIONS_TABLE = process.env.POWERLIFTING_USER_COMPETITIONS_TABLE || 'if-powerlifting-user-competitions'
export const POWERLIFTING_MASTER_FEDERATIONS_TABLE = process.env.POWERLIFTING_MASTER_FEDERATIONS_TABLE || 'if-powerlifting-master-federations'
export const POWERLIFTING_USER_FEDERATIONS_TABLE = process.env.POWERLIFTING_USER_FEDERATIONS_TABLE || 'if-powerlifting-user-federations'
export const POWERLIFTING_GOALS_TABLE = process.env.POWERLIFTING_GOALS_TABLE || 'if-powerlifting-goals'
export const POWERLIFTING_BUDGET_TABLE = process.env.POWERLIFTING_BUDGET_TABLE || 'if-powerlifting-budget'
export const BUDGET_MEDIA_BUCKET = process.env.BUDGET_MEDIA_BUCKET || 'powerlifting-budget-media'
