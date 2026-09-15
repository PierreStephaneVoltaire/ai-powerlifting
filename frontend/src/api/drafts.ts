import { openDB, type IDBPDatabase } from 'idb'
import { requestAthlete, requestPartition, requestPerson } from './context'

export interface Draft<T = unknown> { id: string; partition: string; value: T; updated_at: string }
export type MutationStatus = 'pending' | 'failed' | 'conflict' | 'blocked'
export interface PendingMutation {
  id: string; partition: string; person_pk: string; athlete_pk: string; method: string; url: string; data: unknown
  expected_revision: number; idempotency_key: string; fingerprint: string; created_at: string; updated_at: string
  status: MutationStatus; error?: string
  conflict?: { status: number; code?: string; current_revision?: number; current_record?: unknown }
}

export function sessionDraftKey(version: string, sessionId: string): string {
  return `session:${version}:${sessionId}`
}

export function legacySessionDraftKey(version: string, date: string, index: number): string {
  return `session:${version}:${date}:${index}`
}

let database: Promise<IDBPDatabase> | undefined
function db(): Promise<IDBPDatabase> {
  if (!database) database = openDB('pl-offline', 1, {
    upgrade(db) {
      if (!db.objectStoreNames.contains('drafts')) {
        const drafts = db.createObjectStore('drafts', { keyPath: 'id' })
        drafts.createIndex('byPartition', 'partition')
      }
      if (!db.objectStoreNames.contains('mutations')) {
        const mutations = db.createObjectStore('mutations', { keyPath: 'id' })
        mutations.createIndex('byPartition', 'partition')
      }
    },
  })
  return database
}

export async function saveDraft<T>(record: string, value: T, partition = requestPartition()): Promise<Draft<T>> {
  const draft = { id: `${partition}\0${record}`, partition, value, updated_at: new Date().toISOString() } satisfies Draft<T>
  await (await db()).put('drafts', draft)
  return draft
}
export async function readDraft<T>(record: string, partition = requestPartition()): Promise<Draft<T> | undefined> {
  return (await db()).get('drafts', `${partition}\0${record}`)
}
export async function removeDraft(record: string, partition = requestPartition()): Promise<void> {
  await (await db()).delete('drafts', `${partition}\0${record}`)
}

function sameDraftValue(left: unknown, right: unknown): boolean {
  return JSON.stringify(ordered(left)) === JSON.stringify(ordered(right))
}

export async function removeDraftIfMatch<T>(record: string, expected: Draft<T>, partition = requestPartition()): Promise<boolean> {
  const transaction = (await db()).transaction('drafts', 'readwrite')
  const current = await transaction.store.get(`${partition}\0${record}`) as Draft<T> | undefined
  if (!current || current.updated_at !== expected.updated_at || !sameDraftValue(current.value, expected.value)) {
    await transaction.done
    return false
  }
  await transaction.store.delete(`${partition}\0${record}`)
  await transaction.done
  return true
}

export async function removeDraftIfValue<T>(record: string, value: T, partition = requestPartition()): Promise<boolean> {
  const current = await readDraft<T>(record, partition)
  return current ? removeDraftIfMatch(record, { ...current, value }, partition) : false
}

function ordered(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(ordered)
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value as Record<string, unknown>).sort(([a], [b]) => a.localeCompare(b)).map(([key, item]) => [key, ordered(item)]))
  return value
}

export function mutationFingerprint(method: string, url: string, data: unknown): string {
  const payload = data && typeof data === 'object' ? { ...(data as Record<string, unknown>) } : data
  if (payload && typeof payload === 'object') delete (payload as Record<string, unknown>).idempotency_key
  return JSON.stringify([method.toUpperCase(), url, ordered(payload)])
}

export interface MutationInput { method: string; url: string; data: unknown; expected_revision: number; idempotency_key: string }
export async function prepareMutation(input: MutationInput, partition = requestPartition()): Promise<PendingMutation> {
  const [person_pk, athlete_pk] = JSON.parse(partition) as [string, string]
  const fingerprint = mutationFingerprint(input.method, input.url, input.data)
  const transaction = (await db()).transaction('mutations', 'readwrite')
  const store = transaction.store
  const existing = (await store.index('byPartition').getAll(partition)).find(record => record.fingerprint === fingerprint)
  if (existing) return existing
  const now = new Date().toISOString()
  const record: PendingMutation = {
    id: `${partition}\0${input.idempotency_key}`, partition, person_pk, athlete_pk,
    method: input.method.toUpperCase(), url: input.url, data: input.data, expected_revision: input.expected_revision,
    idempotency_key: input.idempotency_key, fingerprint, created_at: now, updated_at: now, status: 'pending',
  }
  await store.put(record)
  await transaction.done
  window.dispatchEvent(new Event('powerlifting-queue-changed'))
  return record
}

export async function listMutations(partition = requestPartition()): Promise<PendingMutation[]> {
  return (await db()).getAllFromIndex('mutations', 'byPartition', partition)
}
export async function pendingMutationCount(partition = requestPartition()): Promise<number> {
  return (await listMutations(partition)).filter(record => record.status !== 'conflict').length
}
export async function updateMutation(id: string, patch: Partial<PendingMutation>): Promise<void> {
  const database = await db(); const current = await database.get('mutations', id)
  if (!current) return
  await database.put('mutations', { ...current, ...patch, updated_at: new Date().toISOString() })
  window.dispatchEvent(new Event('powerlifting-queue-changed'))
}
export async function removeMutation(id: string): Promise<void> {
  await (await db()).delete('mutations', id)
  window.dispatchEvent(new Event('powerlifting-queue-changed'))
}
export async function resumeMutations(partition = requestPartition()): Promise<void> {
  await Promise.all((await listMutations(partition)).filter(record => record.status === 'blocked' || record.status === 'failed').map(record => updateMutation(record.id, { status: 'pending', error: undefined })))
}
export async function markMutationFailure(id: string, error: string): Promise<void> { await updateMutation(id, { status: 'failed', error }) }
export async function markMutationBlocked(id: string): Promise<void> { await updateMutation(id, { status: 'blocked', error: 'Access must be reauthorized before this change can sync' }) }
export async function markMutationConflict(id: string, response: { status: number; data?: any }): Promise<void> {
  const data = response.data && typeof response.data === 'object' ? response.data : {}
  await updateMutation(id, { status: 'conflict', conflict: { status: response.status, code: data.code, current_revision: data.current_revision ?? data.currentRevision, current_record: data.current_record ?? data.currentRecord } })
}

export async function resolveMutation(record: PendingMutation, changes: Record<string, unknown>): Promise<void> {
  const revision = record.conflict?.current_revision
  if (record.partition !== requestPartition() || !Number.isInteger(revision)) throw new Error('Verify this Athlete and reload the current record before retrying')
  const idempotency_key = crypto.randomUUID()
  const original = record.data && typeof record.data === 'object' ? record.data as Record<string, unknown> : {}
  const data = { ...(typeof original.session_id === 'string' && !('session_id' in changes) ? { session_id: original.session_id } : {}), ...changes, expected_revision: revision!, idempotency_key }
  if (!isQueueableMutation(record.method, record.url, data)) throw new Error('A stable Session identity is required before retrying this change')
  await prepareMutation({ method: record.method, url: record.url, data, expected_revision: revision!, idempotency_key }, record.partition)
  await removeMutation(record.id)
}
export function isQueueableMutation(method: string, url: string, data: unknown): boolean {
  if (!['POST', 'PUT', 'PATCH', 'DELETE'].includes(method.toUpperCase()) || typeof data !== 'object' || data === null || Array.isArray(data)) return false
  const body = data as Record<string, unknown>
  if (!Number.isInteger(body.expected_revision) || Number(body.expected_revision) < 0 || typeof body.idempotency_key !== 'string' || !body.idempotency_key.trim()) return false
  const hasSessionId = typeof body.session_id === 'string' && body.session_id.trim().length > 0
  if (/^\/sessions\//.test(url) && !(method.toUpperCase() === 'POST' && /^\/sessions\/[^/]+$/.test(url)) && !hasSessionId) return false
  if (/^\/programs\/[^/]+\/designer\//.test(url) && !hasSessionId) return false
  return /^\/competitions\/[^/]+(?:\/complete)?$/.test(url) || /^\/sessions\//.test(url) || /^\/programs\/[^/]+\/(meta|body-weight|phases|lift-profiles|archive|unarchive|blocks\/transition|designer\/)/.test(url) || /^\/(maxes|supplements|diet-notes|block-notes)\//.test(url) || /^\/authored-notes\/(private|share|detach)$/.test(url) || /^\/attempts\//.test(url)
}

export interface MutationSender { (record: PendingMutation): Promise<{ status: number; data?: unknown }> }
let synchronizing = false
export async function synchronizePendingMutations(send: MutationSender, partition = requestPartition()): Promise<void> {
  if (synchronizing || !navigator.onLine) return
  synchronizing = true
  try {
    for (const record of (await listMutations(partition)).filter(item => item.status === 'pending' || item.status === 'failed').sort((left, right) => left.created_at.localeCompare(right.created_at) || left.id.localeCompare(right.id))) {
      if (record.person_pk !== requestPerson() || record.athlete_pk !== requestAthlete()) continue
      try {
        const response = await send(record)
        if (response.status >= 200 && response.status < 300) {
          await removeMutation(record.id)
          const sessionMatch = /^\/sessions\/([^/]+)\//.exec(record.url)
          const sessionData = record.data && typeof record.data === 'object' ? record.data as Record<string, unknown> : undefined
          const sessionId = typeof sessionData?.id === 'string' ? sessionData.id : typeof sessionData?.session_id === 'string' ? sessionData.session_id : ''
          if (sessionMatch && sessionData && sessionId) {
            const sameSession = (item: PendingMutation) => {
              const itemMatch = /^\/sessions\/([^/]+)\//.exec(item.url)
              const itemData = item.data && typeof item.data === 'object' ? item.data as Record<string, unknown> : undefined
              return itemMatch?.[1] === sessionMatch[1] && (itemData?.id ?? itemData?.session_id) === sessionId
            }
            if (!(await listMutations(record.partition)).some(sameSession)) {
              const { expected_revision: _expected_revision, idempotency_key: _idempotency_key, session_id: _session_id, ...session } = sessionData
              await removeDraftIfValue(sessionDraftKey(sessionMatch[1], sessionId), session, record.partition)
            }
          }
          if (record.url === '/authored-notes/private' && record.data && typeof record.data === 'object') {
            const { expected_revision: _expected_revision, idempotency_key: _idempotency_key, ...note } = record.data as Record<string, unknown>
            const noteId = String(note.note_id || '')
            const sameNote = (item: PendingMutation) => item.url === record.url && item.data && typeof item.data === 'object' && (item.data as Record<string, unknown>).note_id === noteId
            if (!(await listMutations(record.partition)).some(sameNote)) await removeDraftIfValue(noteId ? `authored-note:${noteId}` : 'authored-note:new', note, record.partition)
          }
        }
      } catch (cause: any) {
        const status = cause?.response?.status
        if (status === 409) { await markMutationConflict(record.id, { status, data: cause.response.data }); break }
        if (status === 401 || status === 403) { await updateMutation(record.id, { status: 'blocked', error: 'Access must be reauthorized before this change can sync' }); window.dispatchEvent(new Event('powerlifting-access-changed')); break }
        await markMutationFailure(record.id, cause instanceof Error ? cause.message : 'Could not synchronize this change')
        break
      }
    }
  } finally { synchronizing = false }
}
