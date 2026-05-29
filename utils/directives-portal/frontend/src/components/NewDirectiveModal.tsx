import { useState } from 'react'
import { Modal, Stack, Text, Select, Textarea, TagsInput, Button } from '@mantine/core'
import { useForm } from '@mantine/form'
import { CreateDirectiveInput } from '../api/client'

interface NewDirectiveModalProps {
  opened: boolean
  onClose: () => void
  onCreate: (input: CreateDirectiveInput) => Promise<void>
}

export function NewDirectiveModal({ opened, onClose, onCreate }: NewDirectiveModalProps) {
  const [submitting, setSubmitting] = useState(false)

  const form = useForm({
    initialValues: {
      alpha: '0',
      label: '',
      content: '',
      types: ['core'] as string[],
    },
    validate: {
      alpha: v => (!v ? 'Tier required' : null),
      label: v => (!v.trim() ? 'Label required' : null),
      content: v => (!v.trim() ? 'Content required' : null),
    },
  })

  const handleSubmit = async () => {
    if (form.validate().hasErrors) return
    setSubmitting(true)
    try {
      await onCreate({
        alpha: parseInt(form.values.alpha, 10),
        label: form.values.label,
        content: form.values.content,
        types: form.values.types,
      })
      form.reset()
      onClose()
    } finally {
      setSubmitting(false)
    }
  }

  const TIER_OPTIONS = [
    { value: '0', label: 'Tier 0 — Fundamental (Never break)' },
    { value: '1', label: 'Tier 1 — Critical (Only bypass with explicit request)' },
    { value: '2', label: 'Tier 2 — Standard (Recommended)' },
    { value: '3', label: 'Tier 3 — Preference (Optional but encouraged)' },
    { value: '4', label: 'Tier 4 — Advisory (Consider)' },
    { value: '5', label: 'Tier 5 — Notes (Background context)' },
  ]

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title={<Text fw={700}>New Directive</Text>}
      size="md"
    >
      <Stack gap="sm">
        <Select
          label="Tier"
          placeholder="Select tier..."
          data={TIER_OPTIONS}
          required
          {...form.getInputProps('alpha')}
        />
        <Textarea
          label="Label"
          placeholder="UPPER_SNAKE_CASE"
          required
          {...form.getInputProps('label')}
        />
        <Textarea
          label="Content"
          placeholder="Full directive text..."
          minRows={6}
          autosize
          required
          {...form.getInputProps('content')}
        />
        <TagsInput
          label="Types"
          placeholder="Add type..."
          defaultValue={['core']}
          onChange={v => form.setFieldValue('types', v)}
          data={['core', 'code', 'health', 'finance', 'memory', 'security', 'style', 'tool', 'metacognition', 'architecture']}
        />
        <Text size="xs" c="dimmed">
          Beta will be auto-assigned by the server.
        </Text>
        <Button
          variant="gradient"
          gradient={{ from: 'violet.6', to: 'violet.4' }}
          onClick={handleSubmit}
          loading={submitting}
          fullWidth
          mt="xs"
        >
          Create Directive
        </Button>
      </Stack>
    </Modal>
  )
}