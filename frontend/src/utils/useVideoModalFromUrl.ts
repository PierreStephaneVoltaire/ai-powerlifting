import { useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import type { VideoLibraryItem } from '@powerlifting/types'

export function useVideoModalFromUrl(videos: VideoLibraryItem[], ready: boolean) {
  const [searchParams, setSearchParams] = useSearchParams()
  const videoIdFromUrl = searchParams.get('video')

  const selectedVideo = useMemo<VideoLibraryItem | null>(() => {
    if (!videoIdFromUrl || !ready) return null
    return videos.find((item) => item.video.video_id === videoIdFromUrl) ?? null
  }, [videoIdFromUrl, videos, ready])

  const openVideo = useCallback((videoId: string) => {
    setSearchParams(
      (current) => {
        const next = new URLSearchParams(current)
        next.set('video', videoId)
        return next
      },
      { replace: false },
    )
  }, [setSearchParams])

  const closeVideo = useCallback(() => {
    setSearchParams(
      (current) => {
        if (!current.has('video')) return current
        const next = new URLSearchParams(current)
        next.delete('video')
        return next
      },
      { replace: true },
    )
  }, [setSearchParams])

  return { selectedVideo, openVideo, closeVideo }
}
