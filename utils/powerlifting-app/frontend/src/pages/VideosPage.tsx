import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { Calendar, Film } from 'lucide-react'
import { Select, Loader, Paper, Stack, Text, Group, Button, Center, Box } from '@mantine/core'
import { useProgramStore } from '@/store/programStore'
import * as api from '@/api/client'
import VideoCard from '@/components/videos/VideoCard'
import VideoPlayerModal from '@/components/videos/VideoPlayerModal'
import type { VideoLibraryItem } from '@powerlifting/types'

export default function VideosPage() {
  const { version } = useProgramStore()
  const [videos, setVideos] = useState<VideoLibraryItem[]>([])
  const [exercises, setExercises] = useState<string[]>([])
  const [exerciseFilter, setExerciseFilter] = useState<string | null>(null)
  const [sortOrder, setSortOrder] = useState<'newest' | 'oldest'>('newest')
  const [isLoading, setIsLoading] = useState(true)
  const [selectedItem, setSelectedItem] = useState<VideoLibraryItem | null>(null)

  const loadVideos = useCallback(async () => {
    setIsLoading(true)
    try {
      const result = await api.getVideos(version, exerciseFilter || undefined, sortOrder)
      setVideos(result.videos)
      setExercises(result.exercises)
    } catch (err) {
      console.error('Failed to load videos:', err)
    } finally {
      setIsLoading(false)
    }
  }, [version, exerciseFilter, sortOrder])

  useEffect(() => {
    loadVideos()
  }, [loadVideos])

  return (
    <Stack gap="md">
      <div className="if-page-header">
        <Stack gap={2}>
          <Group gap="xs">
            <Film size={22} />
            <Text component="h1" className="if-page-title">Videos</Text>
            {videos.length > 0 && (
              <Text size="sm" c="var(--text-secondary)">({videos.length})</Text>
            )}
          </Group>
          <Text className="if-page-subtitle">Review lift videos uploaded from sessions.</Text>
        </Stack>
        {exercises.length > 0 && (
          <Group gap="xs" className="if-toolbar">
            <Select
              value={exerciseFilter}
              onChange={setExerciseFilter}
              data={[
                { value: '', label: 'All exercises' },
                ...exercises.map((name) => ({ value: name, label: name })),
              ]}
              clearable={false}
              w={220}
              size="sm"
            />
            <Button
              variant="default"
              size="sm"
              onClick={() => setSortOrder(sortOrder === 'newest' ? 'oldest' : 'newest')}
              title={sortOrder === 'newest' ? 'Show oldest first' : 'Show newest first'}
            >
              {sortOrder === 'newest' ? 'Newest' : 'Oldest'}
            </Button>
          </Group>
        )}
      </div>

      {isLoading && (
        <Center py={80}>
          <Loader size="sm" />
        </Center>
      )}

      {!isLoading && videos.length === 0 && (
        <Center py={80}>
          <Paper withBorder p="xl" radius="md" className="if-card">
            <Stack align="center" gap="xs">
              <Film size={42} color="var(--text-muted)" />
              <Text fw={500} c="var(--text-secondary)">No videos uploaded yet</Text>
              <Button component={Link} to="/sessions" variant="light" leftSection={<Calendar size={14} />}>
                Go to Sessions
              </Button>
            </Stack>
          </Paper>
        </Center>
      )}

      {!isLoading && videos.length > 0 && (
        <Box className="if-video-grid">
          {videos.map((item) => (
            <VideoCard
              key={item.video.video_id}
              item={item}
              onClick={() => setSelectedItem(item)}
            />
          ))}
        </Box>
      )}

      <VideoPlayerModal
        item={selectedItem}
        onClose={() => setSelectedItem(null)}
        onDeleted={loadVideos}
      />
    </Stack>
  )
}
