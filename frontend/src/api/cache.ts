/**
 * IndexedDB-backed API response cache.
 *
 * No TTL, no background revalidation. The cache is always fresh until a write
 * invalidates the dirty domain, or a login-session change wipes everything.
 *
 * Cache key  = full request URL (path + query string).
 * Cache value = raw res.data (the { data, error } envelope from the backend),
 *               tagged with domain strings for targeted invalidation.
 */

import { openDB, type IDBPDatabase } from 'idb'

interface CacheEntry {
  url: string
  data: unknown
  domains: string[]
}

interface SessionMeta {
  userPk: string
}

const DB_NAME = 'pl-api-cache'
const DB_VERSION = 1
const STORE_RESPONSES = 'responses'
const STORE_META = '_meta'

let dbPromise: Promise<IDBPDatabase> | null = null

function getDB(): Promise<IDBPDatabase> {
  if (!dbPromise) {
    dbPromise = openDB(DB_NAME, DB_VERSION, {
      upgrade(db) {
        if (!db.objectStoreNames.contains(STORE_RESPONSES)) {
          const store = db.createObjectStore(STORE_RESPONSES, { keyPath: 'url' })
          store.createIndex('byDomain', 'domains', { multiEntry: true })
        }
        if (!db.objectStoreNames.contains(STORE_META)) {
          db.createObjectStore(STORE_META)
        }
      },
    })
  }
  return dbPromise
}


export async function checkSession(userPk: string): Promise<void> {
  try {
    const db = await getDB()
    const stored = (await db.get(STORE_META, 'session')) as SessionMeta | undefined
    if (stored && stored.userPk === userPk) return
    await db.clear(STORE_RESPONSES)
    await db.put(STORE_META, { userPk } satisfies SessionMeta, 'session')
  } catch { /* IndexedDB unavailable */ }
}

export async function clearCache(): Promise<void> {
  try {
    const db = await getDB()
    await db.clear(STORE_RESPONSES)
    await db.clear(STORE_META)
  } catch { /* no-op */ }
}


export async function getCached<T = unknown>(url: string): Promise<T | undefined> {
  try {
    const db = await getDB()
    const entry = (await db.get(STORE_RESPONSES, url)) as CacheEntry | undefined
    return entry?.data as T | undefined
  } catch { return undefined }
}

export async function setCached(url: string, data: unknown, domains: string[]): Promise<void> {
  try {
    const db = await getDB()
    await db.put(STORE_RESPONSES, { url, data, domains } satisfies CacheEntry)
  } catch { /* no-op */ }
}


export async function invalidateDomain(domain: string): Promise<void> {
  try {
    const db = await getDB()
    const tx = db.transaction(STORE_RESPONSES, 'readwrite')
    const index = tx.store.index('byDomain')
    let cursor = await index.openCursor(domain)
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
): Promise<void> {
  try {
    const db = await getDB()
    const entry = (await db.get(STORE_RESPONSES, programUrl)) as CacheEntry | undefined
    if (!entry) return
    const envelope = entry.data as any
    if (!envelope?.data?.sessions) return
    const sessions = envelope.data.sessions as any[]
    const idx = sessions.findIndex((s) => s.date === date && (s._index ?? 0) === index)
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
    const entry = (await db.get(STORE_RESPONSES, programUrl)) as CacheEntry | undefined
    if (!entry) return
    const envelope = entry.data as any
    if (!envelope?.data?.sessions) return
    envelope.data.sessions = [...envelope.data.sessions, session]
    entry.data = envelope
    await db.put(STORE_RESPONSES, entry)
  } catch { await invalidateDomain('program:current').catch(() => {}) }
}

export async function removeSessionFromCachedProgram(
  programUrl: string, date: string, index: number,
): Promise<void> {
  try {
    const db = await getDB()
    const entry = (await db.get(STORE_RESPONSES, programUrl)) as CacheEntry | undefined
    if (!entry) return
    const envelope = entry.data as any
    if (!envelope?.data?.sessions) return
    envelope.data.sessions = envelope.data.sessions.filter(
      (s: any) => !(s.date === date && (s._index ?? 0) === index),
    )
    entry.data = envelope
    await db.put(STORE_RESPONSES, entry)
  } catch { await invalidateDomain('program:current').catch(() => {}) }
}


export async function cachedGet(
  axiosInstance: any,
  url: string,
  domains: string[],
): Promise<any> {
  const cached = await getCached(url)
  if (cached !== undefined) return cached
  const res = await axiosInstance.get(url)
  await setCached(url, res.data, domains)
  return res.data
}
