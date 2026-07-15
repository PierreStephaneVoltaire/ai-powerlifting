/**
 * Redis/Valkey-backed cache for powerlifting backend responses.
 *
 * Purpose: speed up pulls on a new device. The frontend IndexedDB cache is wiped
 * on login/logout, but the backend cache survives across devices and users (until
 * its 1-week TTL expires). Frontend writes must invalidate the matching domains
 * here so the next read goes to the source.
 *
 * Keys are namespaced by mapped_pk so different users sharing the cluster don't
 * see each other's data. Domains mirror the frontend's IndexedDB tagging scheme.
 */

import { createClient, type RedisClientType } from 'redis'
import { logger } from './logger'

const VALKEY_URL = process.env.VALKEY_URL || 'redis://pl-valkey:6379'
const CACHE_TTL_SECONDS = 7 * 24 * 60 * 60 // 1 week
const KEY_PREFIX = 'pl:cache:'

let clientPromise: Promise<RedisClientType> | null = null
let connected = false

function getClient(): Promise<RedisClientType> {
  if (!clientPromise) {
    const client = createClient({ url: VALKEY_URL }) as RedisClientType
    client.on('error', (err) => {
      if (connected) logger.warn({ err }, 'Valkey cache connection error')
    })
    client.on('connect', () => {
      connected = true
      logger.info({ url: VALKEY_URL }, 'Valkey cache connected')
    })
    client.on('end', () => {
      connected = false
    })
    clientPromise = client.connect().then(() => client).catch((err) => {
      logger.warn({ err, url: VALKEY_URL }, 'Valkey cache unavailable - reads/writes will be skipped')
      clientPromise = null
      throw err
    })
  }
  return clientPromise
}

function keyFor(mappedPk: string, domain: string): string {
  return `${KEY_PREFIX}${mappedPk}:domain:${domain}`
}

function itemKey(mappedPk: string, url: string): string {
  return `${KEY_PREFIX}${mappedPk}:item:${encodeURIComponent(url)}`
}

function indexKey(mappedPk: string, url: string): string {
  return `${KEY_PREFIX}${mappedPk}:idx:${encodeURIComponent(url)}`
}

async function safe<T>(fn: () => Promise<T>, fallback: T): Promise<T> {
  try {
    return await fn()
  } catch (err) {
    if (connected) logger.warn({ err }, 'Valkey cache op failed')
    return fallback
  }
}

export async function getCached<T = unknown>(
  mappedPk: string,
  url: string,
): Promise<{ data: T; domains: string[] } | undefined> {
  return safe(async () => {
    const client = await getClient()
    const [dataRaw, domainsRaw] = await Promise.all([
      client.get(itemKey(mappedPk, url)),
      client.sMembers(indexKey(mappedPk, url)),
    ])
    if (!dataRaw) return undefined
    return { data: JSON.parse(dataRaw) as T, domains: domainsRaw }
  }, undefined)
}

export async function setCached(
  mappedPk: string,
  url: string,
  data: unknown,
  domains: string[],
): Promise<void> {
  return safe(async () => {
    const client = await getClient()
    const iKey = itemKey(mappedPk, url)
    const idxKey = indexKey(mappedPk, url)
    const payload = JSON.stringify(data)
    const multi = client.multi()
    multi.set(iKey, payload, { EX: CACHE_TTL_SECONDS })
    multi.del(idxKey)
    for (const d of domains) {
      multi.sAdd(idxKey, d)
      multi.sAdd(keyFor(mappedPk, d), iKey)
    }
    multi.expire(idxKey, CACHE_TTL_SECONDS)
    await multi.exec()
    // Refresh per-domain set TTLs separately so they don't drift
    await Promise.all(
      domains.map((d) => client.expire(keyFor(mappedPk, d), CACHE_TTL_SECONDS + 60)),
    )
  }, undefined)
}

export async function invalidateDomains(
  mappedPk: string,
  domains: string[],
): Promise<void> {
  if (domains.length === 0) return
  return safe(async () => {
    const client = await getClient()
    const urlKeys = new Set<string>()
    for (const domain of domains) {
      const members = await client.sMembers(keyFor(mappedPk, domain))
      for (const m of members) urlKeys.add(m)
      await client.del(keyFor(mappedPk, domain))
    }
    if (urlKeys.size === 0) return
    const itemKeys = Array.from(urlKeys)
    await Promise.all(itemKeys.map((k) => client.del(k)))
    const idxKeys = itemKeys.map((k) => k.replace(':item:', ':idx:'))
    await Promise.all(idxKeys.map((k) => client.del(k)))
  }, undefined)
}

export async function invalidateAllForUser(mappedPk: string): Promise<void> {
  return safe(async () => {
    const client = await getClient()
    let cursor = 0
    const toDelete: string[] = []
    do {
      const res = await client.scan(cursor, { MATCH: `${KEY_PREFIX}${mappedPk}:*`, COUNT: 200 })
      cursor = Number(res.cursor)
      toDelete.push(...res.keys)
    } while (cursor !== 0)
    if (toDelete.length > 0) {
      await client.del(toDelete)
    }
  }, undefined)
}

export async function ping(): Promise<boolean> {
  return safe(async () => {
    const client = await getClient()
    return (await client.ping()) === 'PONG'
  }, false)
}
