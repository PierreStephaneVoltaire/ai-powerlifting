import { useState, useMemo, useEffect } from 'react'
import {
  SimpleGrid,
  ActionIcon,
  Center,
  Text,
  Modal,
  Box,
  Paper,
  Stack,
  Group,
  Button,
  Select,
  TextInput,
} from '@mantine/core'
import { Play, Trash2, Loader2, Film, AlertCircle, Save } from 'lucide-react'
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
  const { version, removeSessionVideo, updateSessionVideo } = useProgramStore()
  const [playingVideo, setPlayingVideo] = useState<SessionVideo | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [isSaving, setIsSaving] = useState(false)

  // Editable fields mirrored from the currently selected video. Kept in sync
  // whenever the modal target changes so the form always reflects the video
  // being viewed.
  const [editExercise, setEditExercise] = useState('')
  const [editSetNumber, setEditSetNumber] = useState<number | undefined>()
  const [editNotes, setEditNotes] = useState('')

  const videos = session.videos || []

  // Exercise options with index + cumulative set range, matching the upload
  // modal so assigning the correct set number stays consistent.
  const exerciseOptions = useMemo(() => {
    const byName = new Map<string, string[]>()
    let cumulative = 0
    session.exercises.forEach((e, i) => {
      const setCount = Math.max(0, Math.round(Number(e.sets) || 0))
      const start = cumulative + 1
      const end = cumulative + setCount
      cumulative = end
      const range = setCount > 1 ? `sets ${start}-${end}` : setCount === 1 ? `set ${start}` : ''
      const part = range ? `#${i + 1} (${range})` : `#${i + 1}`
      const arr = byName.get(e.name) || []
      arr.push(part)
      byName.set(e.name, arr)
    })
    return Array.from(byName.entries()).map(([name, parts]) => ({
      value: name,
      label: `${name} — ${parts.join(', ')}`,
    }))
  }, [session.exercises])

  useEffect(() => {
    if (playingVideo) {
      setEditExercise(playingVideo.exercise_name || '')
      setEditSetNumber(playingVideo.set_number)
      setEditNotes(playingVideo.notes || '')
    }
  }, [playingVideo])

  async function handleDelete(video: SessionVideo) {
    if (!confirm('Delete this video?')) return

    setDeletingId(video.video_id)

    try {
      await api.removeSessionVideo(version, session.date, video.video_id)
      removeSessionVideo(session.date, video.video_id)
      pushToast({ message: 'Video deleted', type: 'success' })
      if (playingVideo?.video_id === video.video_id) {
        setPlayingVideo(null)
      }
    } catch (err) {
      console.error('Failed to delete video:', err)
      pushToast({ message: 'Failed to delete video', type: 'error' })
    } finally {
      setDeletingId(null)
    }
  }

  async function handleSaveEdits() {
    if (!playingVideo) return
    setIsSaving(true)
    try {
      const updated = await api.updateSessionVideo(version, session.date, playingVideo.video_id, {
        exerciseName: editExercise,
        setNumber: editSetNumber,
        notes: editNotes,
      })
      updateSessionVideo(session.date, playingVideo.video_id, updated)
      // Reflect the saved values in the modal's own state.
      setPlayingVideo(updated)
      pushToast({ message: 'Video details updated', type: 'success' })
    } catch (err) {
      console.error('Failed to update video:', err)
      pushToast({ message: 'Failed to update video details', type: 'error' })
    } finally {
      setIsSaving(false)
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

      {/* Video Player + Edit Modal */}
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

            {/* Editable video details */}
            <Paper mt={8} p="md" bg="var(--mantine-color-dark-8)" radius="md" style={{ color: '#fff' }}>
              <Stack gap="sm">
                <Select
                  label="Exercise"
                  data={exerciseOptions}
                  value={editExercise}
                  onChange={(value) => setEditExercise(value ?? '')}
                  placeholder="Select exercise..."
                  clearable
                  disabled={isSaving}
                  styles={{
                    label: { color: 'rgba(255,255,255,0.7)' },
                    input: { background: 'rgba(255,255,255,0.1)', borderColor: 'rgba(255,255,255,0.2)', color: '#fff' },
                  }}
                />
                <TextInput
                  type="number"
                  label="Set Number (optional)"
                  value={editSetNumber ?? ''}
                  onChange={(e) => setEditSetNumber(e.currentTarget.value ? Number(e.currentTarget.value) : undefined)}
                  placeholder="e.g., 1, 2, 3..."
                  disabled={isSaving}
                  styles={{
                    label: { color: 'rgba(255,255,255,0.7)' },
                    input: { background: 'rgba(255,255,255,0.1)', borderColor: 'rgba(255,255,255,0.2)', color: '#fff' },
                  }}
                />
                <TextInput
                  label="Notes (optional)"
                  value={editNotes}
                  onChange={(e) => setEditNotes(e.target.value)}
                  placeholder="Form notes, observations..."
                  disabled={isSaving}
                  styles={{
                    label: { color: 'rgba(255,255,255,0.7)' },
                    input: { background: 'rgba(255,255,255,0.1)', borderColor: 'rgba(255,255,255,0.2)', color: '#fff' },
                  }}
                />
                <Group justify="space-between">
                  <Button
                    color="red"
                    variant="light"
                    onClick={() => handleDelete(playingVideo)}
                    loading={deletingId === playingVideo.video_id}
                    disabled={deletingId === playingVideo.video_id || isSaving}
                    leftSection={<Trash2 size={16} />}
                  >
                    Delete
                  </Button>
                  <Button
                    onClick={handleSaveEdits}
                    loading={isSaving}
                    disabled={isSaving || deletingId === playingVideo.video_id}
                    leftSection={<Save size={16} />}
                  >
                    Save changes
                  </Button>
                </Group>
              </Stack>
            </Paper>
          </Box>
        )}
      </Modal>
    </>
  )
}
