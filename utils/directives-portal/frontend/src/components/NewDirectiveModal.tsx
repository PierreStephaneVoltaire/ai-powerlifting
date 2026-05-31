import { useState } from 'react'
import { Modal, Stack, Text, Select, Textarea, TagsInput, Button, Switch, useMantineTheme } from '@mantine/core'
import { useMediaQuery } from '@mantine/hooks'
import { CreateDirectiveInput } from '../api/client'

interface NewDirectiveModalProps {
  opened: boolean
  onClose: () => void
  onCreate: (input: CreateDirectiveInput) => Promise<void>
  isOperator: boolean
}

export function NewDirectiveModal({ opened, onClose, onCreate, isOperator }: NewDirectiveModalProps) {
  const [submitting, setSubmitting] = useState(false)
  const theme = useMantineTheme()
  const smBreakpoint = typeof theme.breakpoints.sm === 'string' ? parseFloat(theme.breakpoints.sm) : theme.breakpoints.sm
  const isMobile = useMediaQuery(`(max-width: ${(smBreakpoint * 16) - 1}px)`)

  const [alpha, setAlpha] = useState('0')
  const [label, setLabel] = useState('')
  const [content, setContent] = useState('')
  const [types, setTypes] = useState<string[]>(['core'])
  const [globalDirective, setGlobalDirective] = useState(false)

  const handleSubmit = async () => {
    if (!alpha || !label.trim() || !content.trim()) return
    setSubmitting(true)
    try {
      await onCreate({
        alpha: parseInt(alpha, 10),
        label: label.trim(),
        content: content.trim(),
        types,
        global_directive: isOperator ? globalDirective : false,
      })
      setAlpha('0')
      setLabel('')
      setContent('')
      setTypes(['core'])
      setGlobalDirective(false)
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
      size={isMobile ? '100%' : 'md'}
      fullScreen={isMobile}
      classNames={{
        content: isMobile ? undefined : 'if-designer-modal-content',
        header: 'if-designer-modal-header',
        title: 'if-designer-modal-title',
        body: 'if-designer-modal-body',
      }}
    >
      <Stack gap="sm">
        <Select
          label="Tier"
          placeholder="Select tier..."
          data={TIER_OPTIONS}
          required
          value={alpha}
          onChange={v => setAlpha(v ?? '0')}
        />
        <Textarea
          label="Label"
          placeholder="UPPER_SNAKE_CASE"
          required
          value={label}
          onChange={e => setLabel(e.target.value)}
          error={label && !label.trim() ? 'Label required' : null}
        />
        <Textarea
          label="Content"
          placeholder="Full directive text..."
          minRows={6}
          autosize
          required
          value={content}
          onChange={e => setContent(e.target.value)}
          error={content && !content.trim() ? 'Content required' : null}
        />
        <TagsInput
          label="Types"
          placeholder="Add type..."
          value={types}
          onChange={setTypes}
          data={['core', 'code', 'health', 'finance', 'memory', 'security', 'style', 'tool', 'metacognition', 'architecture']}
        />

        {isOperator && (
          <Switch
            label="Global directive"
            description="Global directives apply to ALL users and are enforced as safety guardrails. Only operator can modify them."
            checked={globalDirective}
            onChange={e => setGlobalDirective(e.currentTarget.checked)}
            color="orange"
          />
        )}

        <Text size="xs" c="dimmed">
          Beta will be auto-assigned by the server.
        </Text>
        <Button
          variant="gradient"
          gradient={{ from: 'violet.6', to: 'violet.4' }}
          onClick={handleSubmit}
          loading={submitting}
          disabled={!alpha || !label.trim() || !content.trim()}
          fullWidth
          mt="xs"
        >
          Create Directive
        </Button>
      </Stack>
    </Modal>
  )
}
