export const MAX_VIDEO_BYTES = 500 * 1024 * 1024
export const VIDEO_PART_BYTES = 90 * 1024 * 1024
export const MAX_VIDEO_PARTS = Math.ceil(MAX_VIDEO_BYTES / VIDEO_PART_BYTES)

export interface UploadedPart {
  partNumber: number
  etag: string
}

export function partCount(size: number): number {
  return Math.max(1, Math.ceil(size / VIDEO_PART_BYTES))
}

export function isUploadKeyFor(s3Key: string, sessionDate: string, videoId: string): boolean {
  const prefix = `videos/${sessionDate}/${videoId}.`
  return s3Key.startsWith(prefix) && /^[A-Za-z0-9]+$/.test(s3Key.slice(prefix.length))
}

export function parsePartNumber(value: unknown): number | null {
  const partNumber = Number(value)
  return Number.isInteger(partNumber) && partNumber >= 1 && partNumber <= MAX_VIDEO_PARTS ? partNumber : null
}

export function normalizeParts(value: unknown): UploadedPart[] | null {
  if (!Array.isArray(value) || value.length === 0 || value.length > MAX_VIDEO_PARTS) return null
  const parts: UploadedPart[] = []
  for (const entry of value) {
    const partNumber = parsePartNumber((entry as UploadedPart)?.partNumber)
    const etag = (entry as UploadedPart)?.etag
    if (partNumber === null || typeof etag !== 'string' || !etag) return null
    parts.push({ partNumber, etag })
  }
  parts.sort((a, b) => a.partNumber - b.partNumber)
  return parts.every((part, index) => part.partNumber === index + 1) ? parts : null
}
