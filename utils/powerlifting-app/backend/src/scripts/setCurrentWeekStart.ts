/**
 * Store an explicit week-start day for the current training block.
 *
 * Usage: npm run set:week-start --workspace=backend -- Saturday
 */
import { DynamoDBClient } from '@aws-sdk/client-dynamodb'
import { DynamoDBDocumentClient, GetCommand, UpdateCommand } from '@aws-sdk/lib-dynamodb'
import type { WeekStartDay } from '@powerlifting/types'

const PK = process.env.HEALTH_PROGRAM_PK || 'operator'
const TABLE = process.env.DYNAMO_TABLE || 'if-health'
const WEEK_START_DAYS: WeekStartDay[] = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

const client = new DynamoDBClient({
  region: process.env.AWS_REGION || 'ca-central-1',
  credentials: process.env.AWS_ACCESS_KEY_ID && process.env.AWS_SECRET_ACCESS_KEY
    ? { accessKeyId: process.env.AWS_ACCESS_KEY_ID, secretAccessKey: process.env.AWS_SECRET_ACCESS_KEY }
    : undefined,
})
const docClient = DynamoDBDocumentClient.from(client)

function normalizeDay(raw: string | undefined): WeekStartDay {
  const value = raw ? `${raw.slice(0, 1).toUpperCase()}${raw.slice(1).toLowerCase()}` : ''
  if (WEEK_START_DAYS.includes(value as WeekStartDay)) return value as WeekStartDay
  console.error(`Usage: npm run set:week-start --workspace=backend -- ${WEEK_START_DAYS.join('|')}`)
  process.exit(1)
}

async function resolveVersionSk(): Promise<string> {
  const result = await docClient.send(new GetCommand({
    TableName: TABLE,
    Key: { pk: PK, sk: 'program#current' },
  }))
  if (!result.Item) return 'program#v001'
  return (result.Item as Record<string, unknown>).ref_sk as string || 'program#v001'
}

async function main() {
  const day = normalizeDay(process.argv[2])
  const sk = await resolveVersionSk()
  const result = await docClient.send(new GetCommand({
    TableName: TABLE,
    Key: { pk: PK, sk },
    ProjectionExpression: 'meta',
  }))

  if (!result.Item) {
    console.error(`Program not found: ${sk}`)
    process.exit(1)
  }

  const meta = (result.Item.meta ?? {}) as { block_week_start_days?: Record<string, WeekStartDay> }
  const blockWeekStartDays = {
    ...(meta.block_week_start_days ?? {}),
    current: day,
  }

  await docClient.send(new UpdateCommand({
    TableName: TABLE,
    Key: { pk: PK, sk },
    UpdateExpression: 'SET #meta.program_week_start_day = :day, #meta.block_week_start_days = :blockWeekStartDays, #meta.updated_at = :now',
    ExpressionAttributeNames: { '#meta': 'meta' },
    ExpressionAttributeValues: {
      ':day': day,
      ':blockWeekStartDays': blockWeekStartDays,
      ':now': new Date().toISOString(),
    },
  }))

  console.log(`Stored ${day} as the current block week start on ${sk}.`)
}

main().catch((err) => {
  console.error('Fatal:', err)
  process.exit(1)
})
