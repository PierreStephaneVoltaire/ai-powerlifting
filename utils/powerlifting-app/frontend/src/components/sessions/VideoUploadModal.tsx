import { useState, useRef } from 'react'
import {
  Modal,
  Button,
  Group,
  Stack,
  Paper,
  Select,
  TextInput,
  Progress,
  Text,
} from '@mantine/core'
import { Upload, Film, Loader2 } from 'lucide-react'
import { useUiStore } from '@/store/uiStore'
import { useProgramStore } from '@/store/programStore'
import {
  uploadVideo,
  isValidVideoType,
  formatFileSize,
  MAX_VIDEO_SIZE,
} from '@/utils/s3'
import type { Session, SessionVideo } from '@powerlifting/types'

interface VideoUploadModalProps {
  session: Session
  isOpen: boolean
  onClose: () => void
  onUploaded: (video: SessionVideo) => void
}

export default function VideoUploadModal({
  session,
  isOpen,
  onClose,
  onUploaded,
}: VideoUploadModalProps) {
  const { pushToast } = useUiStore()
  const { version } = useProgramStore()
  const [file, setFile] = useState<File | null>(null)
  const [exerciseName, setExerciseName] = useState<string>('')
  const [setNumber, setSetNumber] = useState<number | undefined>()
  const [notes, setNotes] = useState('')
  const [uploadProgress, setUploadProgress] = useState(0)
  const [isUploading, setIsUploading] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  if (!isOpen) return null

  const exerciseOptions = Array.from(new Set(session.exercises.map((e) => e.name)))

  function handleFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const selectedFile = e.target.files?.[0]
    if (!selectedFile) return

    if (!isValidVideoType(selectedFile)) {
      pushToast({
        message: 'Invalid file type. Please use MP4, MOV, or WebM.',
        type: 'error',
      })
      return
    }

    if (selectedFile.size > MAX_VIDEO_SIZE) {
      pushToast({
        message: `File too large. Maximum size is ${formatFileSize(MAX_VIDEO_SIZE)}.`,
        type: 'error',
      })
      return
    }

    setFile(selectedFile)
  }

  async function handleUpload() {
    if (!file) return

    setIsUploading(true)
    setUploadProgress(0)

    try {
      const { video } = await uploadVideo(version, {
        file,
        sessionDate: session.date,
        exerciseName,
        setNumber,
        notes: notes || undefined,
        onProgress: setUploadProgress,
      })

      pushToast({ message: 'Video uploaded successfully', type: 'success' })
      onUploaded(video)
      onClose()
    } catch (err) {
      console.error('Upload failed:', err)
      pushToast({ message: 'Failed to upload video', type: 'error' })
    } finally {
      setIsUploading(false)
      setUploadProgress(0)
    }
  }

  return (
    <Modal opened={isOpen} onClose={onClose} title="Upload Video" centered size="md">
      <Stack gap="md">
        {/* File Input */}
        <div>
          <Text size="sm" c="dimmed">
            Video File
          </Text>
          <input
            ref={fileInputRef}
            type="file"
            accept="video/mp4,video/quicktime,video/webm"
            onChange={handleFileSelect}
            style={{ display: 'none' }}
            disabled={isUploading}
          />
          <Paper
            withBorder
            p="lg"
            ta="center"
            mt={4}
            style={{
              borderStyle: 'dashed',
              cursor: isUploading ? 'not-allowed' : 'pointer',
              opacity: isUploading ? 0.5 : 1,
            }}
            onClick={() => !isUploading && fileInputRef.current?.click()}
          >
            <Stack gap="xs" align="center">
              <Film size={32} style={{ opacity: 0.5 }} />
              {file ? (
                <div>
                  <Text fw={500}>{file.name}</Text>
                  <Text size="xs" c="dimmed">
                    {formatFileSize(file.size)}
                  </Text>
                </div>
              ) : (
                <Text size="sm" c="dimmed">
                  Click to select a video (MP4, MOV, WebM)
                </Text>
              )}
            </Stack>
          </Paper>
        </div>

        {/* Exercise Dropdown */}
        <Select
          label="Exercise"
          data={exerciseOptions}
          value={exerciseName}
          onChange={(value) => setExerciseName(value ?? '')}
          placeholder="Select exercise..."
          clearable
          disabled={isUploading}
        />

        {/* Set Number */}
        <TextInput
          type="number"
          label="Set Number (optional)"
          value={setNumber ?? ''}
          onChange={(e) => setSetNumber(e.currentTarget.value ? Number(e.currentTarget.value) : undefined)}
          placeholder="e.g., 1, 2, 3..."
          disabled={isUploading}
        />

        {/* Notes */}
        <TextInput
          label="Notes (optional)"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Form notes, observations..."
          disabled={isUploading}
        />

        {/* Upload Progress */}
        {isUploading && (
          <Stack gap="xs">
            <Group justify="space-between">
              <Text size="sm" c="dimmed">
                Uploading...
              </Text>
              <Text size="sm" ff="monospace">
                {uploadProgress}%
              </Text>
            </Group>
            <Progress value={uploadProgress} animated />
          </Stack>
        )}
      </Stack>

      {/* Footer */}
      <Group justify="flex-end" mt="md" pt="md" style={{ borderTop: '1px solid var(--mantine-color-default-border)' }}>
        <Button variant="default" onClick={onClose} disabled={isUploading}>
          Cancel
        </Button>
        <Button
          onClick={handleUpload}
          disabled={!file || isUploading || !exerciseName}
          leftSection={isUploading ? <Loader2 size={16} className="animate-spin" /> : <Upload size={16} />}
        >
          {isUploading ? 'Uploading...' : 'Upload'}
        </Button>
      </Group>
    </Modal>
  )
}
