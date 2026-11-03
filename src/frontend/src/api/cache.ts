import { openDB, type IDBPDatabase } from 'idb'
import axios from 'axios'
import { requestPartition } from './context'

interface CacheEntry {
  url: string
  partition: string
  data: unknown
  domains: string[]
}

interface SessionMeta {
  userPk: string
  permissions: string
}

export interface CachedIdentity<T = unknown> {
  partition: string
  person_pk: string
  athlete_pk: string
  data: T
  verified_at: string
}

const DB_NAME = 'pl-api-cache'
const DB_VERSION = 2
const STORE_RESPONSES = 'responses'
const STORE_META = '_meta'

let dbPromise: Promise<IDBPDatabase> | null = null

function getDB(): Promise<IDBPDatabase> {
  if (!dbPromise) {
    dbPromise = openDB(DB_NAME, DB_VERSION, {
      upgrade(db, oldVersion, _newVersion, tx) {
        if (!db.objectStoreNames.contains(STORE_RESPONSES)) {
          const store = db.createObjectStore(STORE_RESPONSES, { keyPath: 'url' })
          store.createIndex('byDomain', 'domains', { multiEntry: true })
        }
        const responses = tx.objectStore(STORE_RESPONSES)
        if (!responses.indexNames.contains('byPartition')) responses.createIndex('byPartition', 'partition')
        if (oldVersion < 2) responses.clear()
        if (!db.objectStoreNames.contains(STORE_META)) {
          db.createObjectStore(STORE_META)
        }
      },
    })
  }
  return dbPromise
}


export async function clearContextCache(partition = requestPartition()): Promise<void> {
  const db = await getDB()
  const tx = db.transaction(STORE_RESPONSES, 'readwrite')
  let cursor = await tx.store.index('byPartition').openCursor(partition)
  while (cursor) {
    await cursor.delete()
    cursor = await cursor.continue()
  }
  await tx.done
}

export async function checkSession(userPk: string, permissions: string[] = []): Promise<void> {
  const partition = requestPartition()
  try {
    const db = await getDB()
    const scope = [...permissions].sort().join(',')
    const stored = (await db.get(STORE_META, partition)) as SessionMeta | undefined
    if (!stored || stored.userPk !== userPk || stored.permissions !== scope) await clearContextCache(partition)
    await db.put(STORE_META, { userPk, permissions: scope } satisfies SessionMeta, partition)
  } catch {}
}

export async function saveVerifiedIdentity<T>(data: T, person_pk: string, athlete_pk: string): Promise<void> {
  try {
    const db = await getDB()
    await db.put(STORE_META, { partition: JSON.stringify([person_pk, athlete_pk]), person_pk, athlete_pk, data, verified_at: new Date().toISOString() } satisfies CachedIdentity<T>, 'last-verified-identity')
  } catch {}
}

export async function readVerifiedIdentity<T = unknown>(): Promise<CachedIdentity<T> | undefined> {
  try { return await (await getDB()).get(STORE_META, 'last-verified-identity') as CachedIdentity<T> | undefined } catch { return undefined }
}

export async function clearDelegatedCachedRecords(partition = requestPartition()): Promise<void> {
  await clearContextCache(partition).catch(() => {})
  try { await (await getDB()).delete(STORE_META, 'last-verified-identity') } catch {}
}

export async function clearCache(): Promise<void> {
  try {
    const db = await getDB()
    await db.clear(STORE_RESPONSES)
    await db.clear(STORE_META)
  } catch { /* no-op */ }
}


export async function getCached<T = unknown>(url: string): Promise<T | undefined> {
  const key = requestPartition() + '\0' + url
  try {
    const db = await getDB()
    const entry = (await db.get(STORE_RESPONSES, key)) as CacheEntry | undefined
    return entry?.data as T | undefined
  } catch { return undefined }
}

export async function setCached(url: string, data: unknown, domains: string[]): Promise<void> {
  const partition = requestPartition()
  try {
    const db = await getDB()
    await db.put(STORE_RESPONSES, { url: partition + '\0' + url, partition, data, domains: domains.map(domain => partition + '\0' + domain) } satisfies CacheEntry)
  } catch { /* no-op */ }
}


export async function invalidateDomain(domain: string): Promise<void> {
  const key = requestPartition() + '\0' + domain
  try {
    const db = await getDB()
    const tx = db.transaction(STORE_RESPONSES, 'readwrite')
    const index = tx.store.index('byDomain')
    let cursor = await index.openCursor(key)
    while (cursor) {
      await tx.store.delete(cursor.primaryKey)
      cursor = await cursor.continue()
    }
    await tx.done
  } catch { /* no-op */ }
}

export async function invalidateDomains(domains: string[]): Promise<void> {
  await Promise.all(domains.map((d) => invalidateDomain(d)))
}


export async function patchSessionInCachedProgram(
  programUrl: string,
  date: string,
  index: number,
  patcher: (session: any) => any,
  sessionId?: string,
): Promise<void> {
  try {
    const db = await getDB()
    const entry = (await db.get(STORE_RESPONSES, requestPartition() + '\0' + programUrl)) as CacheEntry | undefined
    if (!entry) return
    const envelope = entry.data as any
    if (!envelope?.data?.sessions) return
    const sessions = envelope.data.sessions as any[]
    const idx = sessionId
      ? sessions.findIndex((s) => s.id === sessionId)
      : sessions.findIndex((s) => s.date === date && (s._index ?? 0) === index)
    if (idx === -1) { await invalidateDomain('program:current'); return }
    sessions[idx] = patcher(sessions[idx])
    envelope.data.sessions = sessions
    entry.data = envelope
    await db.put(STORE_RESPONSES, entry)
  } catch { await invalidateDomain('program:current').catch(() => {}) }
}

export async function addSessionToCachedProgram(programUrl: string, session: any): Promise<void> {
  try {
    const db = await getDB()
    const entry = (await db.get(STORE_RESPONSES, requestPartition() + '\0' + programUrl)) as CacheEntry | undefined
    if (!entry) return
    const envelope = entry.data as any
    if (!envelope?.data?.sessions) return
    envelope.data.sessions = [...envelope.data.sessions, session]
    entry.data = envelope
    await db.put(STORE_RESPONSES, entry)
  } catch { await invalidateDomain('program:current').catch(() => {}) }
}

export async function removeSessionFromCachedProgram(
  programUrl: string, date: string, index: number, sessionId?: string,
): Promise<void> {
  try {
    const db = await getDB()
    const entry = (await db.get(STORE_RESPONSES, requestPartition() + '\0' + programUrl)) as CacheEntry | undefined
    if (!entry) return
    const envelope = entry.data as any
    if (!envelope?.data?.sessions) return
    envelope.data.sessions = envelope.data.sessions.filter(
      (s: any) => sessionId ? s.id !== sessionId : !(s.date === date && (s._index ?? 0) === index),
    )
    entry.data = envelope
    await db.put(STORE_RESPONSES, entry)
  } catch { await invalidateDomain('program:current').catch(() => {}) }
}

export async function updateProgramRevisionInCachedProgram(
  programUrl: string,
  revision: number | undefined,
): Promise<void> {
  if (typeof revision !== 'number' || !Number.isInteger(revision) || revision < 0) return
  try {
    const db = await getDB()
    const entry = (await db.get(STORE_RESPONSES, requestPartition() + '\0' + programUrl)) as CacheEntry | undefined
    if (!entry) return
    const envelope = entry.data as any
    if (!envelope?.data?.meta) return
    envelope.data.meta = { ...envelope.data.meta, revision }
    entry.data = envelope
    await db.put(STORE_RESPONSES, entry)
  } catch { await invalidateDomain('program:current').catch(() => {}) }
}


export async function cachedGet(
  axiosInstance: any,
  url: string,
  domains: string[],
): Promise<any> {
  const partition = requestPartition()
  const cached = await getCached(url)
  if (partition !== requestPartition()) throw new axios.CanceledError('The Person or Athlete context changed')
  if (!navigator.onLine && cached !== undefined) return cached
  try {
    const res = await axiosInstance.get(url)
    if (partition !== requestPartition()) throw new axios.CanceledError('The Person or Athlete context changed')
    await setCached(url, res.data, domains)
    return res.data
  } catch (error) {
    if (partition === requestPartition() && (!axios.isAxiosError(error) || !error.response)) {
      if (cached !== undefined) return cached
    }
    throw error
  }
}
