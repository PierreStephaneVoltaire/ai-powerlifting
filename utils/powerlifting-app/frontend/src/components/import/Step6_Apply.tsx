import React, { useState } from 'react'
import { Stack, Text, Title, Button, Group, LoadingOverlay, Alert, List } from '@mantine/core'
import { CheckCircle, AlertTriangle } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { applyImport } from '../../api/client'
import type { ImportPending, GlossaryExercise } from '@powerlifting/types'
import type { WizardOverrides } from './ImportWizard'

interface Props {
  pendingImport: ImportPending | null
  overrides: WizardOverrides
  onPrev: () => void
  onReset: () => void
  readOnly?: boolean
}

export const Step6_Apply: React.FC<Props> = ({ pendingImport, overrides, onPrev, onReset, readOnly }) => {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)
  const navigate = useNavigate()

  if (!pendingImport) return null

  const confirmedAutoAdds: Array<Partial<GlossaryExercise>> = overrides.autoAdds
    .filter((d) => d.confirmed)
    .map((d) => ({ name: d.name, category: d.category }))

  const hasOverrides =
    !!overrides.classificationOverride ||
    Object.keys(overrides.glossaryOverrides).length > 0 ||
    confirmedAutoAdds.length > 0

  const handleApply = async () => {
    setLoading(true)
    setError(null)
    try {
      await applyImport(pendingImport.import_id, {
        merge_strategy: pendingImport.merge_strategy || 'append',
        classification_override: overrides.classificationOverride || undefined,
        glossary_overrides:
          Object.keys(overrides.glossaryOverrides).length > 0
            ? overrides.glossaryOverrides
            : undefined,
        confirmed_auto_adds: confirmedAutoAdds.length > 0 ? confirmedAutoAdds : undefined,
      })
      setSuccess(true)
    } catch (err: any) {
      setError(err.message || 'Application failed')
    } finally {
      setLoading(false)
    }
  }

  if (success) {
    return (
      <Stack py="xl" align="center">
        <CheckCircle size={48} color="green" />
        <Text size="lg" fw={500}>Import Successful!</Text>
        <Text c="dimmed">Your program has been added to the library.</Text>
        <Group mt="xl">
          <Button onClick={() => navigate(pendingImport.import_type === 'template' ? '/designer/templates' : '/sessions')}>
            Go to {pendingImport.import_type === 'template' ? 'Templates' : 'Sessions'}
          </Button>
          <Button variant="outline" onClick={onReset}>Import Another</Button>
        </Group>
      </Stack>
    )
  }

  return (
    <Stack py="xl">
      <LoadingOverlay visible={loading} />
      <Title order={4}>Ready to Apply</Title>
      <Text>
        You are about to add "{pendingImport.source_filename}" to your account.
      </Text>

      {hasOverrides && (
        <Alert color="blue" title="Overrides applied">
          <List size="sm">
            {overrides.classificationOverride && (
              <List.Item>Classification: {overrides.classificationOverride}</List.Item>
            )}
            {Object.keys(overrides.glossaryOverrides).length > 0 && (
              <List.Item>
                Glossary overrides: {Object.keys(overrides.glossaryOverrides).length}
              </List.Item>
            )}
            {confirmedAutoAdds.length > 0 && (
              <List.Item>New glossary entries to add: {confirmedAutoAdds.length}</List.Item>
            )}
          </List>
        </Alert>
      )}

      {error && (
        <Alert icon={<AlertTriangle size={16} />} title="Error" color="red">
          {error}
        </Alert>
      )}

      <Group justify="space-between" mt="xl">
        <Button variant="outline" onClick={onPrev}>Back</Button>
        <Button size="lg" color="green" onClick={handleApply} disabled={readOnly}>
          Apply Import
        </Button>
      </Group>
    </Stack>
  )
}
