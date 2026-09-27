import { requestAthlete } from '../api/context'

const MEDIA_CDN_BASE_URL = (import.meta.env.VITE_CLOUDFRONT_MEDIA_BASE_URL || '').replace(/\/+$/, '')

function encodeKey(s3Key: string): string {
  return s3Key.split('/').map(encodeURIComponent).join('/')
}

export function getMediaUrl(s3Key: string | null | undefined, athletePk?: string): string {
  if (!s3Key) return ''
  if (MEDIA_CDN_BASE_URL && s3Key.startsWith('thumbnails/')) return `${MEDIA_CDN_BASE_URL}/${encodeKey(s3Key)}`
  const domain = s3Key.startsWith('budget/') ? 'budget' : s3Key.startsWith('profiles/') ? 'profiles' : 'videos'
  const owner = domain === 'profiles' ? s3Key.split('/')[1] : athletePk || requestAthlete()
  return `/api/${domain}/media/${encodeKey(s3Key)}?athlete=${encodeURIComponent(owner)}`
}

export function resolveAvatarUrl(value: string | null | undefined): string {
  if (!value) return ''
  if (/^https?:\/\//i.test(value)) {
    const url = new URL(value)
    return url.hostname.endsWith('.cloudfront.net') ? getMediaUrl(decodeURIComponent(url.pathname.slice(1))) : value
  }
  return getMediaUrl(value)
}
