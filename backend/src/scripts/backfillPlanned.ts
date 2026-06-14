/**
 * Backfill planned_exercises from exercises for a given week.
 *
 * Usage: npx tsx src/scripts/backfillPlanned.ts <week_number>
 *
 * For each session in the current block matching the given week_number that has
 * no planned_exercises but has exercises, copies exercises[] → planned_exercises[]
 * (stripping notes/failed). Works for both completed and planned sessions.
 */
import { DynamoDBClient } from '@aws-sdk/client-dynamodb'
import { DynamoDBDocumentClient, GetCommand, UpdateCommand } from '@aws-sdk/lib-dynamodb'

const PK = 'operator'
const TABLE = process.env.DYNAMO_TABLE || 'if-health'

const client = new DynamoDBClient({
  region: process.env.AWS_REGION || 'ca-central-1',
  credentials: process.env.AWS_ACCESS_KEY_ID && process.env.AWS_SECRET_ACCESS_KEY
    ? { accessKeyId: process.env.AWS_ACCESS_KEY_ID, secretAccessKey: process.env.AWS_SECRET_ACCESS_KEY }
    : undefined,
})
const docClient = DynamoDBDocumentClient.from(client)

async function resolveVersionSk(): Promise<string> {
  const result = await docClient.send(new GetCommand({
    TableName: TABLE,
    Key: { pk: PK, sk: 'program#current' },
  }))
  if (!result.Item) return 'program#v001'
  return (result.Item as Record<string, unknown>).ref_sk as string || 'program#v001'
}

async function main() {
  const weekArg = process.argv[2]
  if (!weekArg) {
    console.error('Usage: npx tsx src/scripts/backfillPlanned.ts <week_number>')
    process.exit(1)
  }

  const weekNumber = parseInt(weekArg, 10)
  if (isNaN(weekNumber) || weekNumber < 1) {
    console.error(`Invalid week number: ${weekArg}`)
    process.exit(1)
  }

  const sk = await resolveVersionSk()
  console.log(`Using program: ${sk}`)

  const result = await docClient.send(new GetCommand({
    TableName: TABLE,
    Key: { pk: PK, sk },
    ProjectionExpression: 'sessions',
  }))

  if (!result.Item) {
    console.error('Program not found')
    process.exit(1)
  }

  const sessions = (result.Item.sessions ?? []) as Array<Record<string, unknown>>

  let updated = 0
  const updatedSessions = sessions.map((s) => {
    const block = (s.block as string) ?? 'current'
    const sWeek = s.week_number as number
    const completed = s.completed as boolean
    const exercises = (s.exercises as Array<Record<string, unknown>>) ?? []

    const hasPlanned = (s.planned_exercises as Array<unknown>)?.length > 0

    if (block !== 'current' || sWeek !== weekNumber || exercises.length === 0 || hasPlanned) {
      return s
    }

    const planned = exercises.map((e) => ({
      name: e.name,
      sets: e.sets,
      reps: e.reps,
      kg: e.kg ?? null,
    }))

    updated++
    console.log(`  ${s.date} (${s.day}): ${exercises.length} exercises → planned_exercises`)

    return { ...s, planned_exercises: planned }
  })

  if (updated === 0) {
    console.log(`No sessions without planned_exercises found for week ${weekNumber} in current block.`)
    return
  }

  await docClient.send(new UpdateCommand({
    TableName: TABLE,
    Key: { pk: PK, sk },
    UpdateExpression: 'SET sessions = :sessions',
    ExpressionAttributeValues: { ':sessions': updatedSessions },
  }))

  console.log(`\nDone: ${updated} session(s) updated.`)
}

main().catch((err) => {
  console.error('Fatal:', err)
  process.exit(1)
})
