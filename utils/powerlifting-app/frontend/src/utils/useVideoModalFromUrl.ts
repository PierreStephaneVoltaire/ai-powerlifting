import { useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import type { VideoLibraryItem } from '@powerlifting/types'

/**
 * Drive the VideoPlayerModal state from a `?video=<id>` query-string param so
 * each card click is a shareable / reload-safe URL.
 *
 * - On `openVideo(id)`, the `video` query param is set (other params preserved).
 * - On `closeVideo()`, the `video` param is removed (other params preserved).
 * - `selectedVideo` is the matching item from `videos` if the URL has a
 *   `?video=<id>` that resolves to a known video, otherwise `null`. It is
 *   also `null` while `videos` has not yet loaded, so the modal stays closed
 *   until a matching item actually exists.
 *
 * Pages that host video cards (ProfilePage, VideosPage, ProfilesPage) wire
 * this hook to their existing card list and render VideoPlayerModal with
 * the returned `selectedVideo` and `closeVideo`.
 */
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
