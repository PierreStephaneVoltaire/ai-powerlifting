import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Stack, Group, Title, Text, TextInput, Textarea, Button, Alert } from '@mantine/core'
import { createBlankTemplate } from '../api/client'
import { templateEditRoute } from '../utils/templateRoutes'

export default function TemplateCreatePage() {
  const navigate = useNavigate()
  const [form, setForm] = useState({ name: '', description: '', estimated_weeks: 4, days_per_week: 3 })
  const [nameError, setNameError] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleCreate() {
    if (!form.name.trim()) {
      setNameError(true)
      return
    }
    setNameError(false)
    setSaving(true)
    setError(null)
    try {
      const { sk } = await createBlankTemplate({
        name: form.name.trim(),
        description: form.description || undefined,
        estimated_weeks: form.estimated_weeks,
        days_per_week: form.days_per_week,
      })
      navigate(templateEditRoute(sk))
    } catch (e: any) {
      setError(e?.message ?? 'Failed to create template')
      setSaving(false)
    }
  }

  return (
    <Stack gap="lg" maw={600}>
      <Group gap="xs">
        <Text component={Link} to="/designer" size="sm" c="dimmed" style={{ textDecoration: 'none' }}>
          Designer
        </Text>
        <Text c="dimmed">/</Text>
        <Text component={Link} to="/designer/templates" size="sm" c="dimmed" style={{ textDecoration: 'none' }}>
          Template Library
        </Text>
        <Text c="dimmed">/</Text>
        <Title order={2}>New Template</Title>
      </Group>

      {error && (
        <Alert color="red" title="Error">
          {error}
        </Alert>
      )}

      <Stack gap="md">
        <TextInput
          label="Name"
          required
          value={form.name}
          onChange={(e) => {
            const val = e.currentTarget.value;
            setForm(f => ({ ...f, name: val }));
          }}
          error={nameError ? 'Name is required' : undefined}
        />
        <Textarea
          label="Description"
          value={form.description}
          onChange={(e) => {
            const val = e.currentTarget.value;
            setForm(f => ({ ...f, description: val }));
          }}
          autosize
          minRows={2}
        />
        <TextInput
          type="number"
          label="Estimated Weeks"
          value={form.estimated_weeks}
          onChange={(e) => setForm(f => ({ ...f, estimated_weeks: Number(e.currentTarget.value) || 4 }))}
        />
        <TextInput
          type="number"
          label="Days Per Week"
          value={form.days_per_week}
          onChange={(e) => setForm(f => ({ ...f, days_per_week: Number(e.currentTarget.value) || 3 }))}
        />
      </Stack>

      <Group gap="xs">
        <Button onClick={handleCreate} loading={saving} disabled={saving}>
          Create Template
        </Button>
        <Button variant="default" component={Link} to="/designer/templates">
          Cancel
        </Button>
      </Group>
    </Stack>
  )
}
