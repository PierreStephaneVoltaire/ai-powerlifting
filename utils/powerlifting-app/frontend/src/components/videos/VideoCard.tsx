import { Box, Text, UnstyledButton } from '@mantine/core'
import { Play } from 'lucide-react'
import type { VideoLibraryItem } from '@powerlifting/types'
import { useSettingsStore } from '@/store/settingsStore'
import { displayWeight } from '@/utils/units'

interface VideoCardProps {
  item: VideoLibraryItem
  onClick: () => void
}

export default function VideoCard({ item, onClick }: VideoCardProps) {
  const { unit } = useSettingsStore()
  const { video, session_date, day, week_number, phase_name, exercise_sets, exercise_reps, exercise_kg } = item
  const hasThumbnail = video.thumbnail_url && video.thumbnail_status === 'ready'
  const load = typeof exercise_kg === 'number' && exercise_kg > 0
    ? `${displayWeight(exercise_kg, unit)} x ${exercise_reps || '--'}`
    : exercise_sets && exercise_reps
      ? `${exercise_sets} x ${exercise_reps}`
      : null

  return (
    <UnstyledButton onClick={onClick} w="100%" style={{ textAlign: 'left' }}>
      <Box className="if-video-tile">
        <Box className="if-video-thumb">
          {hasThumbnail ? (
            <Box component="img" src={video.thumbnail_url} alt={video.exercise_name} />
          ) : (
            <Box style={{ alignItems: 'center', display: 'flex', flexDirection: 'column', gap: 4 }}>
              <Play size={28} />
              <Text size="xs" c="var(--text-secondary)">Processing</Text>
            </Box>
          )}
          <span className="if-video-play">
            <Play size={18} fill="currentColor" />
          </span>
        </Box>
        <Box p="xs">
          <Text size="sm" fw={600} c="var(--text-primary)" lineClamp={1}>{video.exercise_name}</Text>
          {load && (
            <Text size="xs" className="if-num" c="var(--text-secondary)" mt={2}>
              {load}
            </Text>
          )}
          {video.notes && (
            <Text size="xs" c="var(--status-info-text)" mt={2} lineClamp={1}>{video.notes}</Text>
          )}
          <Text size="xs" c="var(--text-secondary)" mt={4} lineClamp={1}>
            {session_date} - {day} - W{week_number}{phase_name ? ` - ${phase_name}` : ''}
          </Text>
        </Box>
      </Box>
    </UnstyledButton>
  )
}
