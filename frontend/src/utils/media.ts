import { requestAthlete } from '../api/context'

export function getMediaUrl(s3Key: string | null | undefined, athletePk?: string): string {
  if (!s3Key) return ''
  const domain = s3Key.startsWith('budget/') ? 'budget' : s3Key.startsWith('profiles/') ? 'profiles' : 'videos'
  const owner = domain === 'profiles' ? s3Key.split('/')[1] : athletePk || requestAthlete()
  return `/api/${domain}/media/${s3Key.split('/').map(encodeURIComponent).join('/')}?athlete=${encodeURIComponent(owner)}`
}

export function resolveAvatarUrl(value: string | null | undefined): string {
  if (!value) return ''
  if (/^https?:\/\//i.test(value)) {
    const url = new URL(value)
    return url.hostname.endsWith('.cloudfront.net') ? getMediaUrl(decodeURIComponent(url.pathname.slice(1))) : value
  }
  return getMediaUrl(value)
}
