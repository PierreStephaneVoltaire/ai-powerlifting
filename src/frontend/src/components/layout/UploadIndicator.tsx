import { useEffect } from 'react'
import { Popover, Progress, Stack, Text, UnstyledButton } from '@mantine/core'
import { Upload } from 'lucide-react'
import { activeUploads, overallProgress, useVideoUploadStore } from '@/store/videoUploadStore'
import { formatFileSize } from '@/utils/s3'

export function UploadIndicator() {
  const all = useVideoUploadStore((state) => state.uploads)
  const uploads = activeUploads(all)
  const count = uploads.length
  const overall = overallProgress(uploads)

  useEffect(() => {
    if (!count) return
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [count])

  if (!count) return null

  return (
    <Popover position="bottom-end" width={300} shadow="md" withArrow>
      <Popover.Target>
        <UnstyledButton aria-label={`Uploading ${count} video${count === 1 ? '' : 's'}, ${overall}%`} data-testid="upload-indicator">
          <Stack gap={2} w={150}>
            <Text size="xs" fw={500} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <Upload size={12} />
              Uploading {count} video{count === 1 ? '' : 's'} · {overall}%
            </Text>
            <Progress value={overall} color="green" size="sm" animated striped />
          </Stack>
        </UnstyledButton>
      </Popover.Target>
      <Popover.Dropdown>
        <Stack gap="sm">
          <Text size="xs" c="dimmed">Keep this tab open until uploads finish.</Text>
          {uploads.map((upload) => (
            <Stack key={upload.id} gap={2}>
              <Text size="xs" truncate>{upload.fileName}</Text>
              <Progress value={upload.progress} color="green" size="sm" animated />
              <Text size="xs" c="dimmed">{upload.progress}% of {formatFileSize(upload.size)}</Text>
            </Stack>
          ))}
        </Stack>
      </Popover.Dropdown>
    </Popover>
  )
}
