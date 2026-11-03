export function coachUrl(): string {
  const url = process.env.IF_API_URL
  if (!url) throw new Error('IF_API_URL is not set')
  return url.replace(/\/+$/, '')
}
