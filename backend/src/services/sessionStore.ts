import crypto from 'crypto'
import {
  BatchWriteCommand,
  DeleteCommand,
  PutCommand,
  QueryCommand,
} from '@aws-sdk/lib-dynamodb'
import { docClient, SESSION_TABLE } from '../db/dynamo'
import { AppError } from '../middleware/errorHandler'
import type { Phase, Session } from '@powerlifting/types'

const DEFAULT_BLOCK = 'current'

type RawSessionItem = Record<string, any>

function sessionPrefix(programSk: string): string {
  return `session#${programSk}#`
}

function parseWeekNumber(session: Partial<Session>): number {
  if (typeof session.week_number === 'number') return session.week_number
  if (typeof session.week_number === 'string') {
    const parsed = parseInt(session.week_number, 10)
    if (!Number.isNaN(parsed)) return parsed
  }
  const rawWeek = session.week
  if (typeof rawWeek === 'string') {
    const match = rawWeek.match(/W(\d+)/i)
    if (match) return parseInt(match[1], 10)
    const parsed = parseInt(rawWeek, 10)
    return Number.isNaN(parsed) ? 0 : parsed
  }
  return 0
}

function phaseBlock(phase: Phase): string {
  return phase.block ?? DEFAULT_BLOCK
}

function resolvePhase(session: Partial<Session>, phases: Phase[]): Phase {
  const weekNumber = parseWeekNumber(session)
  const block = session.block ?? DEFAULT_BLOCK
  const phase = phases.find(
    (p) => phaseBlock(p) === block && weekNumber >= p.start_week && weekNumber <= p.end_week,
  )
  if (phase) return phase

  if (session.phase && typeof session.phase === 'object') {
    return { ...session.phase, block: session.phase.block ?? block }
  }
  return { name: 'Unscheduled', intent: '', start_week: weekNumber, end_week: weekNumber, block }
}

function phaseRef(phase: Phase): string {
  const block = phase.block ?? DEFAULT_BLOCK
  return `phase#${block}#W${phase.start_week ?? 0}-W${phase.end_week ?? 0}#${(phase.name || 'Unscheduled').replace(/#/g, '-')}`
}

function sortSessions(a: RawSessionItem, b: RawSessionItem): number {
  const dateCompare = String(a.date || '').localeCompare(String(b.date || ''))
  if (dateCompare !== 0) return dateCompare
  const ordinalCompare = Number(a.same_day_ordinal || 0) - Number(b.same_day_ordinal || 0)
  if (ordinalCompare !== 0) return ordinalCompare
  const sourceCompare = Number(a.source_index || 0) - Number(b.source_index || 0)
  if (sourceCompare !== 0) return sourceCompare
  return String(a.sk || '').localeCompare(String(b.sk || ''))
}

function stripUndefined(value: any): any {
  if (value === null || typeof value !== 'object') return value
  if (Array.isArray(value)) return value.map(stripUndefined)
  const out: Record<string, any> = {}
  for (const [key, child] of Object.entries(value)) {
    if (child !== undefined) out[key] = stripUndefined(child)
  }
  return out
}

export const getProxyUrl = (key: string) => `${process.env.CLOUDFRONT_MEDIA_BASE_URL}/${key}`

export function transformVideo(video: any): any {
  return {
    ...video,
    video_url: video.s3_key ? getProxyUrl(video.s3_key) : video.video_url,
    thumbnail_url: video.thumbnail_s3_key ? getProxyUrl(video.thumbnail_s3_key) : video.thumbnail_url,
  }
}

function publicSession(item: RawSessionItem, phases: Phase[]): Session {
  const session: RawSessionItem = { ...item }
  session.id = session.id || session.session_id
  for (const key of [
    'pk',
    'sk',
    'entity_type',
    'source_pk',
    'source_table',
    'program_sk',
    'program_version',
    'program_version_number',
    'source_index',
    'same_day_ordinal',
    'migrated_at',
    'phase_ref',
    'session_id',
  ]) {
    delete session[key]
  }

  const phase = resolvePhase(session, phases)
  session.week_number = parseWeekNumber(session)
  session.block = session.block ?? DEFAULT_BLOCK
  session.phase = phase
  session.phase_name = phase.name
  session.planned_exercises = Array.isArray(session.planned_exercises) ? session.planned_exercises : []
  session.exercises = Array.isArray(session.exercises) ? session.exercises : []
  session.videos = (Array.isArray(session.videos) ? session.videos : []).map(transformVideo)
  session.status = session.status || (session.completed ? 'completed' : 'planned')
  session.completed = Boolean(session.completed || session.status === 'logged' || session.status === 'completed')
  return session as Session
}

function programVersion(programSk: string): string {
  return programSk.startsWith('program#') ? programSk.replace('program#', '') : programSk
}

function programVersionNumber(programSk: string): number | null {
  const match = programSk.match(/^program#v(\d+)$/)
  return match ? parseInt(match[1], 10) : null
}

function mergeVideos(incoming: any[] | undefined, existing: any[] | undefined): any[] | undefined {
  if (!incoming || !Array.isArray(incoming)) return incoming
  if (!existing || !Array.isArray(existing)) return incoming

  return incoming.map(video => {
    const exVideo = existing.find(v => v.video_id === video.video_id)
    if (exVideo && video.thumbnail_status === 'pending' && exVideo.thumbnail_status === 'ready') {
      return {
        ...video,
        thumbnail_status: exVideo.thumbnail_status,
        thumbnail_url: exVideo.thumbnail_url,
        thumbnail_s3_key: exVideo.thumbnail_s3_key
      }
    }
    return video
  })
}

function buildItem(
  pk: string,
  programSk: string,
  session: Partial<Session>,
  phases: Phase[],
  sourceIndex: number,
  sameDayOrdinal: number,
  existing?: RawSessionItem,
): RawSessionItem {
  const date = session.date || 'undated'
  const id = session.id || (session as any).session_id || crypto.randomUUID()
  const block = session.block ?? DEFAULT_BLOCK
  const status = session.status || (session.completed ? 'completed' : 'planned')
  const completed = Boolean(session.completed || status === 'logged' || status === 'completed')
  const phase = resolvePhase({ ...session, block }, phases)
  const preserveSk = Boolean(existing?.sk && String(existing.sk).includes(`#${date}#`))
  const ordinal = preserveSk ? (existing?.same_day_ordinal ?? sameDayOrdinal) : sameDayOrdinal
  const sk = preserveSk
    ? existing?.sk
    : `${sessionPrefix(programSk)}${date}#${String(ordinal).padStart(3, '0')}#${id}`

  return stripUndefined({
    ...session,
    id,
    session_id: id,
    pk,
    sk,
    entity_type: 'session',
    source_pk: pk,
    source_table: process.env.DYNAMO_TABLE || process.env.DYNAMODB_TABLE || 'if-health',
    program_sk: programSk,
    program_version: programVersion(programSk),
    program_version_number: programVersionNumber(programSk),
    source_index: existing?.source_index ?? sourceIndex,
    same_day_ordinal: ordinal,
    date,
    block,
    status,
    completed,
    week_number: parseWeekNumber(session),
    phase,
    phase_name: phase.name,
    phase_ref: phaseRef(phase),
    planned_exercises: Array.isArray(session.planned_exercises) ? session.planned_exercises : [],
    exercises: Array.isArray(session.exercises) ? session.exercises : [],
    videos: mergeVideos(session.videos, existing?.videos),
    updated_at: new Date().toISOString(),
    ...(existing?.migrated_at ? { migrated_at: existing.migrated_at } : {}),
  })
}

async function batchWrite(requests: any[]): Promise<void> {
  for (let index = 0; index < requests.length; index += 25) {
    const batch = requests.slice(index, index + 25)
    if (!batch.length) continue
    await docClient.send(new BatchWriteCommand({
      RequestItems: {
        [SESSION_TABLE]: batch,
      },
    }))
  }
}

export async function listSessionItems(pk: string, programSk: string): Promise<RawSessionItem[]> {
  const items: RawSessionItem[] = []
  let ExclusiveStartKey: Record<string, unknown> | undefined
  do {
    const response = await docClient.send(new QueryCommand({
      TableName: SESSION_TABLE,
      KeyConditionExpression: 'pk = :pk AND begins_with(sk, :prefix)',
      ExpressionAttributeValues: {
        ':pk': pk,
        ':prefix': sessionPrefix(programSk),
      },
      ExclusiveStartKey,
    }))
    items.push(...((response.Items || []) as RawSessionItem[]))
    ExclusiveStartKey = response.LastEvaluatedKey
  } while (ExclusiveStartKey)
  return items.sort(sortSessions)
}

export async function listSessions(pk: string, programSk: string, phases: Phase[]): Promise<Session[]> {
  const items = await listSessionItems(pk, programSk)
  return items.map((item) => publicSession(item, phases))
}

async function findSessionItem(pk: string, programSk: string, date: string, index?: number): Promise<RawSessionItem> {
  const items = await listSessionItems(pk, programSk)
  if (index !== undefined) {
    if (index < 0 || index >= items.length) throw new AppError(`Session at index ${index} not found`, 404)
    const item = items[index]
    if (item.date !== date) {
      throw new AppError(`Session at index ${index} has date ${item.date}, expected ${date}`, 409)
    }
    return item
  }
  const item = items.find((candidate) => candidate.date === date)
  if (!item) throw new AppError(`Session with date ${date} not found`, 404)
  return item
}

async function nextSameDayOrdinal(pk: string, programSk: string, date: string, ignoreSk?: string): Promise<number> {
  const items = await listSessionItems(pk, programSk)
  return items.filter((item) => item.date === date && item.sk !== ignoreSk).length + 1
}

export async function getSession(
  pk: string,
  programSk: string,
  date: string,
  index: number,
  phases: Phase[],
): Promise<Session> {
  return publicSession(await findSessionItem(pk, programSk, date, index), phases)
}

export async function createSession(
  pk: string,
  programSk: string,
  session: Session,
  phases: Phase[],
): Promise<Session> {
  const existing = await listSessionItems(pk, programSk)
  if (existing.some((item) => item.date === session.date)) {
    throw new AppError(`Session with date ${session.date} already exists`, 400)
  }
  const item = buildItem(pk, programSk, session, phases, existing.length, 1)
  await docClient.send(new PutCommand({
    TableName: SESSION_TABLE,
    Item: item,
    ConditionExpression: 'attribute_not_exists(pk) AND attribute_not_exists(sk)',
  }))
  return publicSession(item, phases)
}

export async function replaceSessionAt(
  pk: string,
  programSk: string,
  date: string,
  index: number,
  session: Session,
  phases: Phase[],
): Promise<Session> {
  const existing = await findSessionItem(pk, programSk, date, index)
  const targetDate = session.date || date
  if (targetDate !== existing.date) {
    const conflict = (await listSessionItems(pk, programSk)).some(
      (item) => item.date === targetDate && item.sk !== existing.sk,
    )
    if (conflict) throw new AppError(`Session with date ${targetDate} already exists`, 400)
  }
  const ordinal = await nextSameDayOrdinal(pk, programSk, targetDate, existing.sk)
  const item = buildItem(pk, programSk, session, phases, Number(existing.source_index || index), ordinal, existing)
  await docClient.send(new PutCommand({ TableName: SESSION_TABLE, Item: item }))
  if (item.sk !== existing.sk) {
    await docClient.send(new DeleteCommand({ TableName: SESSION_TABLE, Key: { pk, sk: existing.sk } }))
  }
  return publicSession(item, phases)
}

export async function patchSessionAt(
  pk: string,
  programSk: string,
  date: string,
  index: number,
  patch: Partial<Session>,
  phases: Phase[],
): Promise<Session> {
  const existing = await findSessionItem(pk, programSk, date, index)
  return replaceSessionAt(pk, programSk, date, index, { ...publicSession(existing, phases), ...patch }, phases)
}

export async function patchSessionByDate(
  pk: string,
  programSk: string,
  date: string,
  patch: Partial<Session>,
  phases: Phase[],
): Promise<Session> {
  const existing = await findSessionItem(pk, programSk, date)
  const sessions = await listSessionItems(pk, programSk)
  const index = sessions.findIndex((item) => item.sk === existing.sk)
  return patchSessionAt(pk, programSk, date, index, patch, phases)
}

export async function deleteSessionAt(pk: string, programSk: string, date: string, index: number): Promise<void> {
  const item = await findSessionItem(pk, programSk, date, index)
  await docClient.send(new DeleteCommand({
    TableName: SESSION_TABLE,
    Key: { pk, sk: item.sk },
  }))
}

export async function replaceProgramSessions(
  pk: string,
  programSk: string,
  sessions: Session[],
  phases: Phase[],
): Promise<void> {
  const existing = await listSessionItems(pk, programSk)
  const requests: any[] = existing.map((item) => ({ DeleteRequest: { Key: { pk, sk: item.sk } } }))
  const ordinals = new Map<string, number>()
  sessions.forEach((session, index) => {
    const date = session.date || 'undated'
    const ordinal = (ordinals.get(date) || 0) + 1
    ordinals.set(date, ordinal)
    requests.push({
      PutRequest: {
        Item: buildItem(pk, programSk, session, phases, index, ordinal),
      },
    })
  })
  await batchWrite(requests)
}
