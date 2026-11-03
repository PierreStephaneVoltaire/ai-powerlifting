import { create } from 'zustand'
import type { SessionVideo } from '@powerlifting/types'
import { uploadVideo, type VideoUploadOptions } from '@/utils/s3'
import { useUiStore } from '@/store/uiStore'

export interface BackgroundUpload {
  id: string
  sessionDate: string
  sessionId?: string
  progress: number
  video?: SessionVideo
}

interface VideoUploadState {
  uploads: BackgroundUpload[]
  start: (version: string, options: Omit<VideoUploadOptions, 'onProgress'>) => Promise<SessionVideo | null>
  consume: (id: string) => void
}

export function uploadBelongsTo(upload: BackgroundUpload, session: { date: string; id?: string }): boolean {
  if (upload.sessionId && session.id) return upload.sessionId === session.id
  return upload.sessionDate === session.date
}

export const useVideoUploadStore = create<VideoUploadState>()((set) => {
  const patch = (id: string, change: Partial<BackgroundUpload>) =>
    set((state) => ({ uploads: state.uploads.map((upload) => upload.id === id ? { ...upload, ...change } : upload) }))
  const remove = (id: string) => set((state) => ({ uploads: state.uploads.filter((upload) => upload.id !== id) }))

  return {
    uploads: [],
    start: async (version, options) => {
      const id = options.idempotencyKey || globalThis.crypto.randomUUID()
      set((state) => ({ uploads: [...state.uploads.filter((upload) => upload.id !== id), { id, sessionDate: options.sessionDate, sessionId: options.sessionId, progress: 0 }] }))
      try {
        const { video } = await uploadVideo(version, { ...options, idempotencyKey: id, onProgress: (progress) => patch(id, { progress }) })
        patch(id, { progress: 100, video })
        useUiStore.getState().pushToast({ message: `Video uploaded: ${options.file.name}`, type: 'success' })
        return video
      } catch (err) {
        console.error('Upload failed:', err)
        remove(id)
        useUiStore.getState().pushToast({ message: `Failed to upload video: ${options.file.name}`, type: 'error' })
        return null
      }
    },
    consume: remove,
  }
})
