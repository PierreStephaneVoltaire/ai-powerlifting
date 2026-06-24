import { Box, Text, UnstyledButton } from '@mantine/core'
import { Play } from 'lucide-react'
import type { VideoLibraryItem } from '@powerlifting/types'
import { useSettingsStore } from '@/store/settingsStore'
import { getMediaUrl } from '@/utils/media'
import { displayWeight } from '@/utils/units'

interface VideoCardProps {
  item: VideoLibraryItem
  onClick: () => void
}

export default function VideoCard({ item, onClick }: VideoCardProps) {
  const { unit } = useSettingsStore()
  const { video, session_date, day, week_number, phase_name, exercise_sets, exercise_reps, exercise_kg } = item
  const thumbnailUrl = getMediaUrl(video.thumbnail_s3_key)
  const hasThumbnail = !!thumbnailUrl && video.thumbnail_status === 'ready'
  const load = typeof exercise_kg === 'number' && exercise_kg > 0
    ? `${displayWeight(exercise_kg, unit)} x ${exercise_reps || '--'}`
    : exercise_sets && exercise_reps
      ? `${exercise_sets} x ${exercise_reps}`
      : null

  return (
    <UnstyledButton onClick={onClick} w="100%" h="100%" style={{ textAlign: 'left' }}>
      <Box className="if-video-tile">
        <Box className="if-video-thumb">
          {hasThumbnail ? (
            <Box component="img" src={thumbnailUrl} alt={video.exercise_name} />
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
        <Box className="if-video-body" p="xs">
          <Text size="sm" fw={600} c="var(--text-primary)" lineClamp={1}>{video.exercise_name}</Text>
          <Text
            size="xs"
            className="if-num"
            c="var(--text-secondary)"
            mt={2}
            lineClamp={1}
            // Always reserve a line for the load so the card height stays uniform
            // when this lift has no recorded sets/reps/weight.
            style={{ visibility: load ? 'visible' : 'hidden', minHeight: '1.25em' }}
          >
            {load ?? '\u00a0'}
          </Text>
          <Text
            size="xs"
            c="var(--status-info-text)"
            mt={2}
            lineClamp={1}
            // Reserve a line for the "comments" (notes) so cards with notes
            // don't grow taller than cards without them.
            style={{ visibility: video.notes ? 'visible' : 'hidden', minHeight: '1.25em' }}
          >
            {video.notes ?? '\u00a0'}
          </Text>
          {/*
            The bottom block has two stacked lines: the date on its own line
            (slightly larger / bolder so it reads as the primary anchor) and
            the day / week / phase context on a separate line below. The
            `.if-video-meta` class is a flex column that pins both lines to
            the bottom of the card without clipping.
          */}
          <Box className="if-video-meta" mt={4}>
            <Text
              size="sm"
              fw={500}
              c="var(--text-primary)"
              lineClamp={1}
            >
              {session_date}
            </Text>
            <Text
              size="xs"
              c="var(--text-secondary)"
              lineClamp={1}
            >
              {day} - W{week_number}{phase_name ? ` - ${phase_name}` : ''}
            </Text>
          </Box>
        </Box>
      </Box>
    </UnstyledButton>
  )
}
