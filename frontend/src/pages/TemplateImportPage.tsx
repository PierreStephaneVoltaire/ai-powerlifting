import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useDropzone } from 'react-dropzone'
import { Alert, Button, Group, LoadingOverlay, Paper, Stack, Text, Title } from '@mantine/core'
import { Upload } from 'lucide-react'
import { fetchTemplateImport, uploadTemplateImport } from '../api/client'
import type { TemplateImportJob } from '@powerlifting/types'
import { templateEditRoute } from '../utils/templateRoutes'
import { useAuth } from '@/auth/AuthProvider'

export default function TemplateImportPage() {
  const { readOnly } = useAuth()
  const navigate = useNavigate()
  const [job, setJob] = useState<TemplateImportJob | null>(null)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const onDrop = useCallback(async (acceptedFiles: File[]) => {
    if (!acceptedFiles.length || readOnly) return
    setUploading(true)
    setError(null)
    try {
      const created = await uploadTemplateImport(acceptedFiles[0])
      setJob(created)
    } catch (err: any) {
      setError(err?.message ?? 'Template import failed')
    } finally {
      setUploading(false)
    }
  }, [readOnly])

  useEffect(() => {
    if (!job?.job_id || ['succeeded', 'failed'].includes(job.status)) return
    const timer = window.setInterval(async () => {
      try {
        setJob(await fetchTemplateImport(job.job_id))
      } catch (err: any) {
        setError(err?.message ?? 'Failed to poll template import')
      }
    }, 3000)
    return () => window.clearInterval(timer)
  }, [job?.job_id, job?.status])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    disabled: readOnly || uploading,
    multiple: false,
    accept: {
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
      'application/vnd.ms-excel': ['.xls'],
      'text/csv': ['.csv'],
    },
  })

  return (
    <Stack gap="lg">
      <Group gap="xs">
        <Text component={Link} to="/designer" size="sm" c="dimmed" style={{ textDecoration: 'none' }}>
          Designer
        </Text>
        <Text c="dimmed">/</Text>
        <Text component={Link} to="/designer/templates" size="sm" c="dimmed" style={{ textDecoration: 'none' }}>
          Template Library
        </Text>
        <Text c="dimmed">/</Text>
        <Title order={2}>Import Template</Title>
      </Group>

      {error && <Alert color="red" title="Error">{error}</Alert>}

      <Paper
        {...getRootProps()}
        withBorder
        p="xl"
        radius="md"
        style={{
          cursor: readOnly ? 'not-allowed' : 'pointer',
          borderStyle: 'dashed',
          backgroundColor: isDragActive ? 'var(--mantine-color-blue-light)' : undefined,
          position: 'relative',
        }}
      >
        <LoadingOverlay visible={uploading || Boolean(job && !['succeeded', 'failed'].includes(job.status))} />
        <input {...getInputProps()} />
        <Group justify="center" gap="md" style={{ minHeight: 140 }}>
          <Upload size={24} />
          <Stack gap={4} align="center">
            <Text fw={500}>{isDragActive ? 'Drop file here' : 'Click or drag template spreadsheet here'}</Text>
            <Text size="sm" c="dimmed">Supports .xlsx, .xls, and .csv</Text>
          </Stack>
        </Group>
      </Paper>

      {job && (
        <Paper withBorder p="md" radius="md">
          <Stack gap="xs">
            <Text fw={500}>Status: {job.status}</Text>
            {job.filename && <Text size="sm" c="dimmed">{job.filename}</Text>}
            {job.error && <Alert color="red">{job.error}</Alert>}
            {job.status === 'succeeded' && job.template_sk && (
              <Group>
                <Button onClick={() => navigate(templateEditRoute(job.template_sk!))}>
                  Review Draft
                </Button>
                <Button variant="default" onClick={() => navigate('/designer/templates')}>
                  Template Library
                </Button>
              </Group>
            )}
          </Stack>
        </Paper>
      )}
    </Stack>
  )
}
