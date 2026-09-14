import type { SessionVideo } from '@powerlifting/types'

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api'

export interface VideoUploadOptions {
  file: File
  sessionDate: string
  exerciseName?: string
  setNumber?: number
  notes?: string
  onProgress?: (percent: number) => void
}

export interface VideoUploadResult {
  video: SessionVideo
}

async function responseJson<T>(response: Response): Promise<T> {
  const body = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(body.error || 'Video upload failed')
  return body.data as T
}

function uploadToBackend(url: string, body: FormData, onProgress?: (percent: number) => void): Promise<VideoUploadResult> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.upload.addEventListener('progress', (event) => {
      if (event.lengthComputable) onProgress?.(Math.round((event.loaded / event.total) * 100))
    })
    xhr.addEventListener('load', () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve(JSON.parse(xhr.responseText).data)
      else reject(new Error(`Video upload failed (${xhr.status})`))
    })
    xhr.addEventListener('error', () => reject(new Error('Network error during video upload')))
    xhr.open('POST', url)
    xhr.withCredentials = true
    xhr.send(body)
  })
}

export async function uploadVideo(
  version: string,
  options: VideoUploadOptions,
): Promise<VideoUploadResult> {
  const { file, sessionDate, exerciseName, setNumber, notes, onProgress } = options
  const body = new FormData()
  body.append('file', file)
  if (exerciseName) body.append('exerciseName', exerciseName)
  if (setNumber !== undefined) body.append('setNumber', String(setNumber))
  if (notes) body.append('notes', notes)
  return uploadToBackend(`${API_BASE}/videos/${version}/${sessionDate}`, body, onProgress)
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
