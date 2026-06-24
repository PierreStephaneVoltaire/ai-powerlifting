/**
 * Build-time CloudFront media base URL.
 *
 * The frontend resolves video/thumbnail/avatar media URLs directly from S3
 * keys using this base, so media traffic never touches the backend — it is
 * served straight from the CloudFront distribution.
 */
const MEDIA_BASE_URL = import.meta.env.VITE_CLOUDFRONT_MEDIA_BASE_URL || ''

/**
 * Resolve a raw S3 key (e.g. "videos/2026-01-15/abc.mp4") to a fully-qualified
 * CloudFront URL. Returns an empty string when no base URL is configured so
 * callers can fall back gracefully (e.g. show a placeholder).
 */
export function getMediaUrl(s3Key: string | null | undefined): string {
  if (!s3Key) return ''
  if (!MEDIA_BASE_URL) return ''
  return `${MEDIA_BASE_URL}/${s3Key}`
}

/**
 * Resolve an avatar URL. Accepts either a raw S3 key (new style) or a
 * pre-built CloudFront/S3 URL (legacy data stored before the migration).
 */
export function resolveAvatarUrl(value: string | null | undefined): string {
  if (!value) return ''
  // Already a full URL (legacy data or external avatar) — return as-is
  if (/^https?:\/\//i.test(value)) return value
  // Raw S3 key — resolve via CloudFront
  return getMediaUrl(value)
}