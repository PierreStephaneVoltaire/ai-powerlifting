import React, { useCallback, useState } from 'react'
import { useDropzone } from 'react-dropzone'
import { Text, Group, Paper, Stack, LoadingOverlay, Button } from '@mantine/core'
import { uploadImport } from '../../api/client'

interface Props {
  onUpload: (importId: string) => void
  readOnly?: boolean
}

export const Step1_Upload: React.FC<Props> = ({ onUpload, readOnly }) => {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const onDrop = useCallback(async (acceptedFiles: File[]) => {
    if (acceptedFiles.length === 0) return
    
    setLoading(true)
    setError(null)
    
    try {
      const result = await uploadImport(acceptedFiles[0])
      onUpload(result.import_id)
    } catch (err: any) {
      setError(err.message || 'Upload failed')
    } finally {
      setLoading(false)
    }
  }, [onUpload])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    disabled: readOnly,
    accept: {
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
      'text/csv': ['.csv']
    },
    multiple: false
  })

  return (
    <Stack py="xl">
      <Paper
        {...getRootProps()}
        withBorder
        p="xl"
        radius="md"
        style={{
          cursor: readOnly ? 'not-allowed' : 'pointer',
          backgroundColor: isDragActive ? 'var(--mantine-color-blue-light)' : undefined,
          borderStyle: 'dashed',
        }}
      >
        <LoadingOverlay visible={loading} />
        <input {...getInputProps()} />
        
        <Group justify="center" gap="xl" style={{ minHeight: 120 }}>
          <Stack align="center" gap="xs">
            <Text size="xl" fw={500}>
              {isDragActive ? 'Drop file here' : 'Click or drag training program here'}
            </Text>
            <Text c="dimmed" size="sm">
              Supports .xlsx (Excel) and .csv files
            </Text>
          </Stack>
        </Group>
      </Paper>
      
      {error && (
        <Text c="red" ta="center" size="sm">
          {error}
        </Text>
      )}
    </Stack>
  )
}
