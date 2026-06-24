import { useState } from 'react'
import {
  SimpleGrid,
  ActionIcon,
  Center,
  Text,
  Modal,
  Box,
} from '@mantine/core'
import { Play, Trash2, X, Loader2, Film, AlertCircle } from 'lucide-react'
import { useUiStore } from '@/store/uiStore'
import { useProgramStore } from '@/store/programStore'
import * as api from '@/api/client'
import { getMediaUrl } from '@/utils/media'
import VideoPlayer from './VideoPlayer'
import type { Session, SessionVideo } from '@powerlifting/types'

interface VideoGridProps {
  session: Session
}

export default function VideoGrid({ session }: VideoGridProps) {
  const { pushToast } = useUiStore()
  const { version, removeSessionVideo } = useProgramStore()
  const [playingVideo, setPlayingVideo] = useState<SessionVideo | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)

  const videos = session.videos || []

  async function handleDelete(video: SessionVideo) {
    if (!confirm('Delete this video?')) return

    setDeletingId(video.video_id)

    try {
      await api.removeSessionVideo(version, session.date, video.video_id)
      removeSessionVideo(session.date, video.video_id)
      pushToast({ message: 'Video deleted', type: 'success' })
    } catch (err) {
      console.error('Failed to delete video:', err)
      pushToast({ message: 'Failed to delete video', type: 'error' })
    } finally {
      setDeletingId(null)
    }
  }

  if (videos.length === 0) {
    return null
  }

  return (
    <>
      <SimpleGrid cols={{ base: 2, md: 3, lg: 4 }} spacing="sm">
        {videos.map((video) => (
          <Box
            key={video.video_id}
            className="if-video-tile"
          >
            <Box
              component="button"
              className="if-video-thumb"
              onClick={() => setPlayingVideo(video)}
              style={{
                width: '100%',
                border: 'none',
                cursor: 'pointer',
                padding: 0,
              }}
            >
              {video.thumbnail_status === 'pending' ? (
                <Center pos="absolute" inset={0}>
                  <Loader2 size={24} style={{ animation: 'spin 1s linear infinite' }} />
                </Center>
              ) : video.thumbnail_status === 'failed' ? (
                <Center
                  pos="absolute"
                  inset={0}
                  bg="var(--mantine-color-red-0)"
                >
                  <AlertCircle size={24} color="var(--mantine-color-red-6)" />
                </Center>
              ) : getMediaUrl(video.thumbnail_s3_key) ? (
                <Box
                  component="img"
                  src={getMediaUrl(video.thumbnail_s3_key)}
                  alt={video.exercise_name || 'Video thumbnail'}
                  style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                />
              ) : (
                <Center pos="absolute" inset={0}>
                  <Film size={24} color="var(--text-muted)" />
                </Center>
              )}

              <span className="if-video-play">
                <Play size={18} fill="currentColor" />
              </span>
            </Box>

            <Box p={8}>
              <Text size="sm" fw={600} c="var(--text-primary)" truncate>
                {video.exercise_name || 'Video'}
              </Text>
              <Box style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                {video.set_number && (
                  <Text size="xs" c="var(--text-secondary)">
                    Set {video.set_number}
                  </Text>
                )}
                <ActionIcon
                  variant="subtle"
                  color="red"
                  size="sm"
                  onClick={(e) => {
                    e.stopPropagation()
                    handleDelete(video)
                  }}
                  loading={deletingId === video.video_id}
                  disabled={deletingId === video.video_id}
                >
                  <Trash2 size={16} />
                </ActionIcon>
              </Box>
            </Box>
          </Box>
        ))}
      </SimpleGrid>

      {/* Video Player Modal */}
      <Modal
        opened={playingVideo !== null}
        onClose={() => setPlayingVideo(null)}
        size="xl"
        withCloseButton
        overlayProps={{ backgroundOpacity: 0.8, color: '#000' }}
        styles={{
          content: { background: 'transparent', boxShadow: 'none' },
          body: { padding: 0 },
        }}
      >
        {playingVideo && (
          <Box>
            <VideoPlayer
              src={getMediaUrl(playingVideo.s3_key)}
              thumbnailUrl={getMediaUrl(playingVideo.thumbnail_s3_key)}
            />

            {/* Video Info */}
            <Box mt={8}>
              <Text fw={500} c="white">
                {playingVideo.exercise_name || 'Video'}
                {playingVideo.set_number && ` - Set ${playingVideo.set_number}`}
              </Text>
              {playingVideo.notes && (
                <Text size="sm" c="rgba(255, 255, 255, 0.7)">
                  {playingVideo.notes}
                </Text>
              )}
            </Box>
          </Box>
        )}
      </Modal>
    </>
  )
}
