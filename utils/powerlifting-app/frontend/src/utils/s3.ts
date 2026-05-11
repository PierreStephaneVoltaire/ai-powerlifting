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

/**
 * Upload a video via the backend API (server proxy)
 */
export async function uploadVideo(
  version: string,
  options: VideoUploadOptions
): Promise<VideoUploadResult> {
  const { file, sessionDate, exerciseName, setNumber, notes, onProgress } = options

  const formData = new FormData()
  formData.append('video', file)
  if (exerciseName) formData.append('exerciseName', exerciseName)
  if (setNumber) formData.append('setNumber', String(setNumber))
  if (notes) formData.append('notes', notes)

  // Use XMLHttpRequest for progress tracking
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.withCredentials = true

    xhr.upload.addEventListener('progress', (event) => {
      if (event.lengthComputable && onProgress) {
        const percent = Math.round((event.loaded / event.total) * 100)
        onProgress(percent)
      }
    })

    xhr.addEventListener('load', () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          const response = JSON.parse(xhr.responseText)
          resolve({ video: response.data })
        } catch {
          reject(new Error('Invalid response from server'))
        }
      } else {
        try {
          const response = JSON.parse(xhr.responseText)
          reject(new Error(response.error || 'Upload failed'))
        } catch {
          reject(new Error('Upload failed'))
        }
      }
    })

    xhr.addEventListener('error', () => {
      reject(new Error('Network error during upload'))
    })

    xhr.open('POST', `${API_BASE}/videos/${version}/${sessionDate}`)
    xhr.send(formData)
  })
}

/**
 * Check if file is a valid video type
 */
export function isValidVideoType(file: File): boolean {
  const validTypes = ['video/mp4', 'video/quicktime', 'video/webm', 'video/x-msvideo']
  return validTypes.includes(file.type)
}

/**
 * Format file size for display
 */
export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
}

/**
 * Max video file size (500MB)
 */
export const MAX_VIDEO_SIZE = 500 * 1024 * 1024
