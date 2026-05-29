import { useState } from 'react'
import {
  Modal, Stack, Text, Group, Textarea, TextInput, TagsInput,
  Button, Badge, Divider, ScrollArea, Loader, Box,
} from '@mantine/core'
import { Directive, DirectiveHistoryResponse, ReviseDirectiveInput } from '../api/client'

interface DirectiveDetailModalProps {
  directive: Directive | null
  history: DirectiveHistoryResponse | null
  historyLoading: boolean
  onClose: () => void
  onSave: (alpha: number, beta: number, input: ReviseDirectiveInput) => Promise<void>
  onDelete: (alpha: number, beta: number) => Promise<void>
  onFetchHistory: (alpha: number, beta: number) => void
  onClearHistory: () => void
}

export function DirectiveDetailModal({
  directive, history, historyLoading,
  onClose, onSave, onDelete, onFetchHistory, onClearHistory,
}: DirectiveDetailModalProps) {
  const [editing, setEditing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [showHistory, setShowHistory] = useState(false)

  const [label, setLabel] = useState('')
  const [content, setContent] = useState('')
  const [types, setTypes] = useState<string[]>([])

  if (!directive) return null

  // Sync form when directive changes
  if (label !== directive.label || content !== directive.content) {
    setLabel(directive.label)
    setContent(directive.content)
    setTypes(directive.types ?? [])
  }

  const handleSave = async () => {
    if (!label.trim() || !content.trim()) return
    setSaving(true)
    try {
      await onSave(directive.alpha, directive.beta, {
        content, label, types,
      })
      setEditing(false)
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async () => {
    setDeleting(true)
    try {
      await onDelete(directive.alpha, directive.beta)
      onClose()
    } finally {
      setDeleting(false)
    }
  }

  const handleShowHistory = () => {
    if (!history) onFetchHistory(directive.alpha, directive.beta)
    setShowHistory(s => !s)
  }

  const isProtected = directive.alpha === 0 && directive.beta === 1

  return (
    <Modal
      opened={!!directive}
      onClose={() => { onClose(); onClearHistory(); setEditing(false); setShowHistory(false) }}
      title={
        <Group gap={8}>
          <Text fw={700} ff="'IBM Plex Mono', monospace" size="lg" c="violet.6">
            {directive.alpha}-{directive.beta}
          </Text>
          <Text fw={600}>{directive.label}</Text>
        </Group>
      }
      size="lg"
    >
      <Stack gap="md">
        <Group gap="xs">
          <Badge variant="light" color="violet">v{directive.version}</Badge>
          {directive.types?.map(t => (
            <Badge key={t} size="xs" variant="light" color="gray">{t}</Badge>
          ))}
          <Text size="xs" c="dimmed">
            by {directive.created_by} · {new Date(directive.created_at).toLocaleDateString()}
          </Text>
        </Group>

        <Divider />

        {editing ? (
          <Stack gap="sm">
            <TextInput
              label="Label"
              placeholder="UPPER_SNAKE_CASE"
              value={label}
              onChange={e => setLabel(e.target.value)}
              error={!label.trim() ? 'Label required' : null}
            />
            <Textarea
              label="Content"
              placeholder="Full directive text..."
              minRows={6}
              autosize
              value={content}
              onChange={e => setContent(e.target.value)}
              error={!content.trim() ? 'Content required' : null}
            />
            <TagsInput
              label="Types"
              placeholder="Add type..."
              defaultValue={types}
              onChange={setTypes}
              data={['core', 'code', 'health', 'finance', 'memory', 'security', 'style', 'tool', 'metacognition', 'architecture']}
            />
            <Group justify="flex-end" mt="sm">
              <Button variant="subtle" onClick={() => setEditing(false)}>Cancel</Button>
              <Button
                variant="gradient"
                gradient={{ from: 'violet.6', to: 'violet.4' }}
                onClick={handleSave}
                loading={saving}
              >
                Save Changes
              </Button>
            </Group>
          </Stack>
        ) : (
          <Stack gap="sm">
            <ScrollArea.Autosize mah={300}>
              <Text size="sm" style={{ whiteSpace: 'pre-wrap', fontFamily: "'IBM Plex Mono', monospace" }}>
                {directive.content}
              </Text>
            </ScrollArea.Autosize>

            <Divider />

            <Group justify="space-between">
              <Button variant="subtle" size="xs" onClick={handleShowHistory}>
                {showHistory ? 'Hide History' : 'Show History'}
              </Button>
              <Group gap="xs">
                {!isProtected && (
                  <Button
                    variant="subtle"
                    color="red"
                    size="xs"
                    onClick={handleDelete}
                    loading={deleting}
                  >
                    Delete
                  </Button>
                )}
                <Button
                  variant="gradient"
                  gradient={{ from: 'violet.6', to: 'violet.4' }}
                  size="xs"
                  onClick={() => setEditing(true)}
                >
                  Edit
                </Button>
              </Group>
            </Group>

            {showHistory && (
              <Stack gap="xs" mt="xs">
                {historyLoading ? (
                  <Group justify="center" py="md"><Loader size="sm" /></Group>
                ) : history ? (
                  <>
                    <Text size="xs" fw={600} c="dimmed">
                      Version History ({history.versions.length} total)
                    </Text>
                    {history.versions.map(v => (
                      <Box
                        key={v.version}
                        style={{
                          border: '1px solid var(--border-default)',
                          borderRadius: 6,
                          padding: '8px 10px',
                          opacity: v.active ? 1 : 0.5,
                        }}
                      >
                        <Group justify="space-between" mb={4}>
                          <Group gap={6}>
                            <Badge size="xs" variant="light" color={v.active ? 'green' : 'gray'}>
                              v{v.version}
                            </Badge>
                            {v.active && <Badge size="xs" color="violet">current</Badge>}
                          </Group>
                          <Text size="xs" c="dimmed">
                            {new Date(v.created_at).toLocaleDateString()}
                          </Text>
                        </Group>
                        <Text size="xs" c="dimmed">
                          by {v.created_by}
                          {v.superseded_at && ` · superseded ${new Date(v.superseded_at).toLocaleDateString()}`}
                        </Text>
                      </Box>
                    ))}
                  </>
                ) : null}
              </Stack>
            )}
          </Stack>
        )}
      </Stack>
    </Modal>
  )
}
