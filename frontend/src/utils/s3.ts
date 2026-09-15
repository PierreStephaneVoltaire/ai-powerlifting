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

function uploadToBackend(url: string, body: FormData, onProgress?: (percent: number) => void, idempotencyKey?: string): Promise<VideoUploadResult> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.upload.addEventListener('progress', (event) => {
      if (event.lengthComputable) onProgress?.(Math.round((event.loaded / event.total) * 100))
    })
    xhr.addEventListener('load', () => {
      try {
        const payload = JSON.parse(xhr.responseText)
        if (xhr.status >= 200 && xhr.status < 300 && payload.data?.video_id) resolve({ video: payload.data })
        else reject(new Error(payload.error || `Video upload failed (${xhr.status})`))
      } catch { reject(new Error('Invalid video upload response')) }
    })
    xhr.addEventListener('error', () => reject(new Error('Network error during video upload')))
    xhr.addEventListener('abort', () => reject(new Error('Video upload interrupted; retry the file')))
    xhr.open('POST', url)
    xhr.setRequestHeader('X-Selected-Athlete-Pk', requestAthlete())
    if (idempotencyKey) xhr.setRequestHeader('Idempotency-Key', idempotencyKey)
    xhr.withCredentials = true
    xhr.send(body)
  })
}

export async function uploadVideo(
  version: string,
  options: VideoUploadOptions,
): Promise<VideoUploadResult> {
  const { file, sessionDate, sessionId, exerciseName, setNumber, notes, onProgress, idempotencyKey, lift, angle, targetRevision } = options
  const body = new FormData()
  body.append('file', file)
  if (sessionId) body.append('sessionId', sessionId)
  if (exerciseName) body.append('exerciseName', exerciseName)
  if (setNumber !== undefined) body.append('setNumber', String(setNumber))
  if (notes) body.append('notes', notes)
  if (lift) body.append('lift', lift)
  if (angle) body.append('angle', angle)
  if (targetRevision !== undefined) body.append('targetRevision', String(targetRevision))
  return uploadToBackend(`${API_BASE}/videos/${encodeURIComponent(version)}/${encodeURIComponent(sessionDate)}`, body, onProgress, idempotencyKey)
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
