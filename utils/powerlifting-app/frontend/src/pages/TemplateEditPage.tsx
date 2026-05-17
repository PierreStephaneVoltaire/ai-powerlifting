import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { Save, X } from 'lucide-react'
import {
  Stack, Group, Title, Text, Button, Alert, LoadingOverlay, Divider,
} from '@mantine/core'
import { fetchTemplate, updateTemplate } from '../api/client'
import { TemplateMetaEditor } from '../components/templates/TemplateMetaEditor'
import { TemplatePhasesEditor } from '../components/templates/TemplatePhasesEditor'
import { TemplateSessionsEditor } from '../components/templates/TemplateSessionsEditor'
import type { Template } from '@powerlifting/types'
import { templateDetailRoute } from '../utils/templateRoutes'
import { useAuth } from '@/auth/AuthProvider'

export default function TemplateEditPage() {
  const { readOnly } = useAuth()
  const { sk } = useParams<{ sk: string }>()
  const [searchParams] = useSearchParams()
  const resolvedSk = sk ?? searchParams.get('sk') ?? undefined
  const navigate = useNavigate()
  const [template, setTemplate] = useState<Template | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!resolvedSk) {
      setLoading(false)
      return
    }
    fetchTemplate(resolvedSk)
      .then(setTemplate)
      .catch((e) => setError(e?.message ?? 'Failed to load template'))
      .finally(() => setLoading(false))
  }, [resolvedSk])

  async function handleSave() {
    if (readOnly || !resolvedSk || !template) return
    if (!template.meta.name.trim()) {
      setError('Template name is required')
      return
    }
    setSaving(true)
    setError(null)
    try {
      await updateTemplate(resolvedSk, template)
      navigate(templateDetailRoute(resolvedSk))
    } catch (e: any) {
      setError(e?.message ?? 'Failed to save template')
      setSaving(false)
    }
  }

  return (
    <Stack gap="lg" style={{ position: 'relative' }}>
      <LoadingOverlay visible={loading} />

      <Group justify="space-between">
        <Group gap="xs">
          <Text component={Link} to="/designer" size="sm" c="dimmed" style={{ textDecoration: 'none' }}>
            Designer
          </Text>
          <Text c="dimmed">/</Text>
          <Text component={Link} to="/designer/templates" size="sm" c="dimmed" style={{ textDecoration: 'none' }}>
            Template Library
          </Text>
          <Text c="dimmed">/</Text>
          <Title order={2}>{template?.meta.name ?? 'Edit Template'}</Title>
        </Group>
        <Group gap="xs">
          <Button
            variant="default"
            leftSection={<X size={16} />}
            onClick={() => resolvedSk && navigate(templateDetailRoute(resolvedSk))}
            disabled={saving}
          >
            Cancel
          </Button>
          <Button
            leftSection={<Save size={16} />}
            onClick={handleSave}
            loading={saving}
            disabled={saving || !template || readOnly}
          >
            Save
          </Button>
        </Group>
      </Group>

      {error && (
        <Alert color="red" title="Error">
          {error}
        </Alert>
      )}

      {template && (
        <Stack gap="lg">
          <Stack gap="sm">
            <Title order={3}>Details</Title>
            <TemplateMetaEditor
              meta={template.meta}
              onChange={(meta) => setTemplate(t => t ? { ...t, meta } : t)}
              disabled={readOnly}
            />
          </Stack>

          <Divider />

          <Stack gap="sm">
            <Title order={3}>Phases</Title>
            <TemplatePhasesEditor
              phases={template.phases}
              onChange={(phases) => setTemplate(t => t ? { ...t, phases } : t)}
              disabled={readOnly}
            />
          </Stack>

          <Divider />

          <Stack gap="sm">
            <Title order={3}>Sessions</Title>
            <TemplateSessionsEditor
              sessions={template.sessions}
              onChange={(sessions) => setTemplate(t => t ? { ...t, sessions } : t)}
              disabled={readOnly}
            />
          </Stack>
        </Stack>
      )}
    </Stack>
  )
}
