import React, { useCallback, useState } from 'react'
import { useDropzone } from 'react-dropzone'
import { useNavigate } from 'react-router-dom'
import { Radio, Text, Textarea, Group, Paper, Stack, LoadingOverlay } from '@mantine/core'
import { uploadImport, uploadTemplateImport } from '../../api/client'
import type { ImportType } from '@powerlifting/types'

interface Props {
  onUpload: (importId: string) => void
  readOnly?: boolean
}

export const Step1_Upload: React.FC<Props> = ({ onUpload, readOnly }) => {
  const navigate = useNavigate()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [importType, setImportType] = useState<ImportType | null>(null)
  const [instructions, setInstructions] = useState('')

  const onDrop = useCallback(async (acceptedFiles: File[]) => {
    if (acceptedFiles.length === 0) return
    
    setLoading(true)
    setError(null)
    
    try {
      if (!importType) return
      if (importType === 'template') {
        const job = await uploadTemplateImport(acceptedFiles[0], instructions)
        navigate(`/designer/templates/import?job_id=${encodeURIComponent(job.job_id)}`)
        return
      }
      const result = await uploadImport(acceptedFiles[0], importType, instructions)
      onUpload(result.import_id)
    } catch (err: any) {
      setError(err.message || 'Upload failed')
    } finally {
      setLoading(false)
    }
  }, [importType, instructions, navigate, onUpload])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    disabled: readOnly || loading || !importType,
    accept: {
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
      'text/csv': ['.csv']
    },
    multiple: false
  })

  return (
    <Stack py="xl" gap="md">
      <Radio.Group
        label="Import as"
        description="Choose how to interpret this file before it is parsed."
        value={importType ?? ''}
        onChange={(value) => setImportType(value as ImportType)}
        withAsterisk
      >
        <Group mt="xs">
          <Radio value="template" label="Reusable template" disabled={readOnly || loading} />
          <Radio value="session_import" label="Dated session import" disabled={readOnly || loading} />
        </Group>
      </Radio.Group>

      <Textarea
        label="Import instructions"
        description="Tell the parser how to interpret ambiguous rows, exercise labels, or dates."
        value={instructions}
        onChange={(event) => setInstructions(event.currentTarget.value)}
        maxLength={4000}
        autosize
        minRows={2}
        disabled={readOnly || loading}
      />

      <Paper
        {...getRootProps()}
        withBorder
        p="xl"
        radius="md"
        style={{
          cursor: readOnly || !importType ? 'not-allowed' : 'pointer',
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
