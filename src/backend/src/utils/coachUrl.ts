export function coachUrl(): string {
  const url = process.env.IF_API_URL
  if (!url) throw new Error('IF_API_URL is not set')
  return url.replace(/\/+$/, '')
}

export function assistantUrl(): string {
  const url = process.env.ASSISTANT_URL || 'http://pl-assistant.powerlifting.svc.cluster.local:8000'
  return url.replace(/\/+$/, '')
}
