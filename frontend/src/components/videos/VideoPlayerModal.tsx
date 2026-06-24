import { useState } from 'react'
import { Modal, Group, Button, ActionIcon, Text, Box, Stack } from '@mantine/core'
import { Trash2 } from 'lucide-react'
import { useUiStore } from '@/store/uiStore'
import { useProgramStore } from '@/store/programStore'
import * as api from '@/api/client'
import { getMediaUrl } from '@/utils/media'
import type { VideoLibraryItem } from '@powerlifting/types'

interface VideoPlayerModalProps {
  item: VideoLibraryItem | null
  onClose: () => void
  onDeleted?: () => void
  readOnly?: boolean
}

export default function VideoPlayerModal({ item, onClose, onDeleted, readOnly = false }: VideoPlayerModalProps) {
  const { pushToast } = useUiStore()
  const { version } = useProgramStore()
  const [showConfirm, setShowConfirm] = useState(false)

  if (!item) return null

  const { video, session_date, day, week_number, phase_name } = item

  async function handleDelete() {
    if (readOnly) return
    try {
      await api.removeSessionVideo(version, session_date, video.video_id)
      pushToast({ message: 'Video deleted', type: 'success' })
      onDeleted?.()
      onClose()
    } catch (err) {
      console.error('Delete failed:', err)
      pushToast({ message: 'Failed to delete video', type: 'error' })
    }
  }

  return (
    <Modal
      opened={item !== null}
      onClose={onClose}
      size="xl"
      withCloseButton
      title={
        <Box>
          <Text fw={600}>{video.exercise_name}</Text>
          <Text size="xs" c="dimmed">
            {session_date} · {day} · W{week_number} · {phase_name}
          </Text>
        </Box>
      }
      styles={{
        body: { padding: 0 },
      }}
    >
      {/* Video */}
      <Box bg="black">
        <Box
          component="video"
          src={getMediaUrl(video.s3_key)}
          controls
          autoPlay
          style={{ width: '100%', maxHeight: '70vh', display: 'block' }}
        />
      </Box>

      {/* Footer */}
      <Box p={16}>
        <Stack gap={8}>
          {video.notes && (
            <Text size="sm" fs="italic" c="dimmed">{video.notes}</Text>
          )}
          <Group justify="flex-end">
            {showConfirm ? (
              <Group gap={8}>
                <Button
                  variant="default"
                  size="compact-sm"
                  onClick={() => setShowConfirm(false)}
                >
                  Cancel
                </Button>
                <Button
                  color="red"
                  size="compact-sm"
                  leftSection={<Trash2 size={14} />}
                  onClick={handleDelete}
                  disabled={readOnly}
                >
                  Confirm Delete
                </Button>
              </Group>
            ) : (
              <Button
                variant="subtle"
                color="red"
                size="compact-sm"
                leftSection={<Trash2 size={14} />}
                onClick={() => setShowConfirm(true)}
                disabled={readOnly}
              >
                Delete Video
              </Button>
            )}
          </Group>
        </Stack>
      </Box>
    </Modal>
  )
}
