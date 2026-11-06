import { create } from 'zustand'
import type { SessionVideo } from '@powerlifting/types'
import type { VideoUploadOptions } from '@/utils/s3'
import { useUiStore } from '@/store/uiStore'

export interface BackgroundUpload {
  id: string
  fileName: string
  size: number
  status: 'uploading' | 'done'
  sessionDate?: string
  sessionId?: string
  progress: number
  video?: SessionVideo
}

interface TrackedUpload {
  id?: string
  file: File
  sessionDate?: string
  sessionId?: string
}

interface VideoUploadState {
  uploads: BackgroundUpload[]
  start: (version: string, options: Omit<VideoUploadOptions, 'onProgress'> & { uploadId?: string }) => Promise<SessionVideo | null>
  track: <T>(upload: TrackedUpload, run: (onProgress: (progress: number) => void) => Promise<T>) => Promise<T>
  consume: (id: string) => void
}

export function uploadBelongsTo(upload: BackgroundUpload, session: { date: string; id?: string }): boolean {
  if (upload.sessionId && session.id) return upload.sessionId === session.id
  return upload.sessionDate === session.date
}

export function activeUploads(uploads: BackgroundUpload[]): BackgroundUpload[] {
  return uploads.filter((upload) => upload.status === 'uploading')
}

export function overallProgress(uploads: BackgroundUpload[]): number {
  const total = uploads.reduce((sum, upload) => sum + Math.max(upload.size, 1), 0)
  if (!total) return 0
  return Math.round(uploads.reduce((sum, upload) => sum + upload.progress * Math.max(upload.size, 1), 0) / total)
}

export const useVideoUploadStore = create<VideoUploadState>()((set, get) => {
  const patch = (id: string, change: Partial<BackgroundUpload>) =>
    set((state) => ({ uploads: state.uploads.map((upload) => upload.id === id ? { ...upload, ...change } : upload) }))
  const remove = (id: string) => set((state) => ({ uploads: state.uploads.filter((upload) => upload.id !== id) }))

  const track: VideoUploadState['track'] = async ({ id = globalThis.crypto.randomUUID(), file, sessionDate, sessionId }, run) => {
    set((state) => ({
      uploads: [...state.uploads.filter((upload) => upload.id !== id), { id, fileName: file.name, size: file.size, status: 'uploading', sessionDate, sessionId, progress: 0 }],
    }))
    try {
      const result = await run((progress) => patch(id, { progress }))
      if (sessionDate) patch(id, { progress: 100, status: 'done' })
      else remove(id)
      return result
    } catch (err) {
      remove(id)
      throw err
    }
  }

  return {
    uploads: [],
    track,
    start: async (version, options) => {
      const { uploadId, ...upload } = options
      const id = uploadId || globalThis.crypto.randomUUID()
      try {
        const { uploadVideo } = await import('@/utils/s3')
        const { video } = await track({ id, file: options.file, sessionDate: options.sessionDate, sessionId: options.sessionId }, (onProgress) =>
          uploadVideo(version, { ...upload, onProgress }))
        patch(id, { video })
        useUiStore.getState().pushToast({ message: `Video uploaded: ${options.file.name}`, type: 'success' })
        return video
      } catch (err) {
        console.error('Upload failed:', err)
        useUiStore.getState().pushToast({ message: `Failed to upload video: ${options.file.name}`, type: 'error' })
        return null
      }
    },
    consume: (id) => {
      if (get().uploads.find((upload) => upload.id === id)?.status === 'done') remove(id)
    },
  }
})
