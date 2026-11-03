import type { LiftProfileVideoAngle, SessionVideo } from '@powerlifting/types'
import { requestAthlete } from '../api/context'

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api'

export interface VideoUploadOptions {
  file: File
  sessionDate: string
  sessionId?: string
  exerciseName?: string
  setNumber?: number
  notes?: string
  onProgress?: (percent: number) => void
  idempotencyKey?: string
  lift?: 'squat' | 'bench' | 'deadlift'
  angle?: LiftProfileVideoAngle
  targetRevision?: number
}

export interface VideoUploadResult {
  video: SessionVideo
}

interface VideoUploadSession {
  videoId: string
  s3Key: string
  uploadId: string
  partSize: number
  partCount: number
}

interface UploadedPart {
  partNumber: number
  etag: string
}

const PART_ATTEMPTS = 3

function uploadHeaders(idempotencyKey?: string): Record<string, string> {
  return {
    'X-Selected-Athlete-Pk': requestAthlete(),
    ...(idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : {}),
  }
}

async function uploadRequest<T>(url: string, method: string, body: unknown, idempotencyKey?: string): Promise<T> {
  const response = await fetch(url, {
    method,
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...uploadHeaders(idempotencyKey) },
    body: JSON.stringify(body),
  })
  const payload = await response.json().catch(() => null)
  if (!response.ok || !payload?.data) throw new Error(payload?.error || `Video upload failed (${response.status})`)
  return payload.data as T
}

function uploadPart(url: string, chunk: Blob, onProgress: (loaded: number) => void): Promise<UploadedPart> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.upload.addEventListener('progress', (event) => onProgress(event.loaded))
    xhr.addEventListener('load', () => {
      try {
        const payload = JSON.parse(xhr.responseText)
        if (xhr.status >= 200 && xhr.status < 300 && payload.data?.etag) resolve(payload.data)
        else reject(new Error(payload.error || `Video part upload failed (${xhr.status})`))
      } catch { reject(new Error(`Video part upload failed (${xhr.status})`)) }
    })
    xhr.addEventListener('error', () => reject(new Error('Network error during video upload')))
    xhr.addEventListener('abort', () => reject(new Error('Video upload interrupted; retry the file')))
    xhr.open('PUT', url)
    xhr.setRequestHeader('Content-Type', 'application/octet-stream')
    xhr.setRequestHeader('X-Selected-Athlete-Pk', requestAthlete())
    xhr.withCredentials = true
    xhr.send(chunk)
  })
}

async function uploadPartWithRetry(url: string, chunk: Blob, onProgress: (loaded: number) => void): Promise<UploadedPart> {
  for (let attempt = 1; ; attempt += 1) {
    try {
      return await uploadPart(url, chunk, onProgress)
    } catch (err) {
      onProgress(0)
      if (attempt >= PART_ATTEMPTS) throw err
    }
  }
}

export async function uploadVideo(
  version: string,
  options: VideoUploadOptions,
): Promise<VideoUploadResult> {
  const { file, sessionDate, sessionId, exerciseName, setNumber, notes, onProgress, idempotencyKey, lift, angle, targetRevision } = options
  const base = `${API_BASE}/videos/${encodeURIComponent(version)}/${encodeURIComponent(sessionDate)}/uploads`
  const target = { sessionId, lift, angle, targetRevision, idempotencyKey }
  const session = await uploadRequest<VideoUploadSession>(base, 'POST', {
    ...target, filename: file.name, mimeType: file.type, size: file.size,
  }, idempotencyKey)
  const ref = `uploadId=${encodeURIComponent(session.uploadId)}&s3Key=${encodeURIComponent(session.s3Key)}`
  const videoBase = `${base}/${encodeURIComponent(session.videoId)}`
  const loaded = new Array<number>(session.partCount).fill(0)
  const parts: UploadedPart[] = []
  try {
    for (let index = 0; index < session.partCount; index += 1) {
      const chunk = file.slice(index * session.partSize, Math.min(file.size, (index + 1) * session.partSize))
      parts.push(await uploadPartWithRetry(`${videoBase}/parts/${index + 1}?${ref}`, chunk, (bytes) => {
        loaded[index] = bytes
        onProgress?.(Math.min(99, Math.round((loaded.reduce((sum, value) => sum + value, 0) / file.size) * 100)))
      }))
    }
  } catch (err) {
    await fetch(`${videoBase}?${ref}`, { method: 'DELETE', credentials: 'include', headers: uploadHeaders() }).catch(() => undefined)
    throw err
  }
  const video = await uploadRequest<SessionVideo>(`${videoBase}/complete`, 'POST', {
    ...target, uploadId: session.uploadId, s3Key: session.s3Key, parts, exerciseName, setNumber, notes,
  }, idempotencyKey)
  if (!video.video_id) throw new Error('Invalid video upload response')
  onProgress?.(100)
  return { video }
}

export function isValidVideoType(file: File): boolean {
  return ['video/mp4', 'video/quicktime', 'video/webm', 'video/x-msvideo'].includes(file.type)
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
}

export const MAX_VIDEO_SIZE = 500 * 1024 * 1024
