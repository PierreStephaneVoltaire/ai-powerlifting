import { createSign } from 'node:crypto'

const HOUR_SECONDS = 3600
const DAY_SECONDS = 24 * HOUR_SECONDS

export interface MediaCdnConfig {
  baseUrl: string
  keyPairId: string
  privateKey: string
  videoTtlSeconds: number
}

export function mediaCdnConfig(env: NodeJS.ProcessEnv = process.env): MediaCdnConfig | null {
  const baseUrl = (env.MEDIA_CDN_BASE_URL || '').replace(/\/+$/, '')
  const keyPairId = env.MEDIA_SIGNING_KEY_PAIR_ID || ''
  const privateKey = env.MEDIA_SIGNING_PRIVATE_KEY || ''
  if (!baseUrl || !keyPairId || !privateKey) return null
  const hours = Number(env.MEDIA_VIDEO_URL_TTL_HOURS || 72)
  return { baseUrl, keyPairId, privateKey, videoTtlSeconds: (Number.isFinite(hours) && hours > 0 ? hours : 72) * HOUR_SECONDS }
}

export function isPublicMediaKey(key: string): boolean {
  return key.startsWith('thumbnails/')
}

export function publicMediaUrl(config: Pick<MediaCdnConfig, 'baseUrl'>, key: string): string {
  return `${config.baseUrl}/${key.split('/').map(encodeURIComponent).join('/')}`
}

export function signedUrlExpiry(ttlSeconds: number, nowMs: number): number {
  const now = Math.floor(nowMs / 1000)
  return Math.floor(now / DAY_SECONDS) * DAY_SECONDS + DAY_SECONDS + ttlSeconds
}

function cloudFrontBase64(value: Buffer): string {
  return value.toString('base64').replace(/\+/g, '-').replace(/=/g, '_').replace(/\//g, '~')
}

export function signedMediaUrl(config: MediaCdnConfig, key: string, nowMs: number = Date.now()): string {
  const resource = publicMediaUrl(config, key)
  const expires = signedUrlExpiry(config.videoTtlSeconds, nowMs)
  const policy = JSON.stringify({ Statement: [{ Resource: resource, Condition: { DateLessThan: { 'AWS:EpochTime': expires } } }] })
  const signature = createSign('RSA-SHA1').update(policy).sign(config.privateKey)
  return `${resource}?Expires=${expires}&Signature=${cloudFrontBase64(signature)}&Key-Pair-Id=${encodeURIComponent(config.keyPairId)}`
}
