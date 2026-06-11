import { useState, useEffect } from 'react'
import {
  Box,
  Button,
  Group,
  Modal,
  Select,
  Stack,
  Text,
  Textarea,
  TextInput,
} from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { useProposalsStore } from '../store/proposalsStore'
import {
  TYPE_LABELS,
  type CreateProposalInput,
  type Directive,
  type ProposalType,
} from '../types'

interface NewProposalModalProps {
  isOpen: boolean
  onClose: () => void
}

const TYPE_OPTIONS = Object.entries(TYPE_LABELS).map(([value, label]) => ({
  value,
  label,
}))

export function NewProposalModal({ isOpen, onClose }: NewProposalModalProps) {
  const [type, setType] = useState<ProposalType>('system_observation')
  const [title, setTitle] = useState('')
  const [rationale, setRationale] = useState('')
  const [content, setContent] = useState('')
  const [targetId, setTargetId] = useState<string | null>(null)
  const [error, setError] = useState('')

  const { createProposal, loadDirectives, directives, loading } = useProposalsStore()

  useEffect(() => {
    if (isOpen) {
      loadDirectives()
    }
  }, [isOpen, loadDirectives])

  const showTargetSelect = type === 'rewrite_directive' || type === 'deprecate_directive'
  const requiresContent = type !== 'system_observation'

  const resetForm = () => {
    setType('system_observation')
    setTitle('')
    setRationale('')
    setContent('')
    setTargetId(null)
    setError('')
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')

    if (!title.trim()) {
      setError('Title is required')
      return
    }
    if (!rationale.trim()) {
      setError('Rationale is required')
      return
    }
    if (requiresContent && !content.trim()) {
      setError('Content is required for this proposal type')
      return
    }
    if (showTargetSelect && !targetId) {
      setError('Target directive is required for this proposal type')
      return
    }

    try {
      const input: CreateProposalInput = {
        type,
        title: title.trim(),
        rationale: rationale.trim(),
        content: content.trim(),
      }
      if (targetId) input.target_id = targetId
      await createProposal(input)
      resetForm()
      onClose()
      notifications.show({
        title: 'Proposal created',
        message: `${title.trim()} is now in the pending column`,
        color: 'blue',
      })
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Could not create proposal'
      setError(message)
      notifications.show({ title: 'Create failed', message, color: 'red' })
    }
  }

  const handleClose = () => {
    resetForm()
    onClose()
  }

  const directiveOptions = (directives as Directive[]).map((d) => ({
    value: d.sk,
    label: `${d.label} (v${d.version})`,
  }))

  return (
    <Modal
      opened={isOpen}
      onClose={handleClose}
      title={<Text fw={700}>New Proposal</Text>}
      size="lg"
      centered
    >
      <form onSubmit={handleSubmit}>
        <Stack gap="sm">
          {error && (
            <Box
              p="xs"
              style={{
                background: 'var(--status-danger-bg)',
                border: '0.5px solid var(--status-danger-border)',
                borderRadius: 'var(--border-radius-md)',
              }}
            >
              <Text size="sm" c="var(--status-danger-text)">{error}</Text>
            </Box>
          )}

          <Select
            label="Type"
            data={TYPE_OPTIONS}
            value={type}
            onChange={(value) => setType((value as ProposalType) ?? 'system_observation')}
            allowDeselect={false}
            required
          />

          {showTargetSelect && (
            <Select
              label="Target Directive"
              placeholder="Select a directive..."
              data={directiveOptions}
              value={targetId}
              onChange={setTargetId}
              searchable
              required
            />
          )}

          <TextInput
            label="Title"
            placeholder="e.g., CONTEXT_WINDOW_DISCIPLINE"
            value={title}
            onChange={(e) => setTitle(e.currentTarget.value)}
            required
          />

          <Textarea
            label="Rationale"
            placeholder="Why should this proposal be implemented?"
            value={rationale}
            onChange={(e) => setRationale(e.currentTarget.value)}
            autosize
            minRows={3}
            required
          />

          <Textarea
            label={
              <Group gap={4}>
                <Text size="sm" fw={500}>Proposed Content</Text>
                {requiresContent && <Text size="sm" c="red">*</Text>}
              </Group>
            }
            placeholder="The actual proposed text (directive content, tool spec, etc.)"
            value={content}
            onChange={(e) => setContent(e.currentTarget.value)}
            autosize
            minRows={6}
            styles={{ input: { fontFamily: "'IBM Plex Mono', monospace", fontSize: 13 } }}
            required={requiresContent}
          />

          <Group justify="flex-end" mt="sm">
            <Button variant="subtle" color="gray" onClick={handleClose}>
              Cancel
            </Button>
            <Button
              type="submit"
              variant="gradient"
              gradient={{ from: 'blue.6', to: 'blue.4' }}
              loading={loading}
            >
              Create Proposal
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  )
}