import { createClient, type RedisClientType } from 'redis'
import { logger } from './logger'

const VALKEY_URL = process.env.VALKEY_URL || 'redis://pl-valkey:6379'

let clientPromise: Promise<RedisClientType> | null = null

export function valkey(): Promise<RedisClientType> {
  if (!clientPromise) {
    const client = createClient({ url: VALKEY_URL }) as RedisClientType
    client.on('error', (err) => logger.warn({ err }, 'Valkey connection error'))
    clientPromise = client.connect().then(() => client).catch((err) => {
      clientPromise = null
      throw err
    })
  }
  return clientPromise
}
