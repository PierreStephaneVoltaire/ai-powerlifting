import { useState } from 'react'
import {
  Modal, Stack, Text, Group, Textarea, TextInput, TagsInput,
  Button, Badge, Divider, ScrollArea, Loader, Box, Switch, Tooltip,
  useMantineTheme,
} from '@mantine/core'
import { useMediaQuery } from '@mantine/hooks'
import { Globe, Lock, User } from 'lucide-react'
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
  isOperator: boolean
  onSetGlobal?: (alpha: number, beta: number, next: boolean) => Promise<void> | void
  globalTogglePending?: boolean
}

export function DirectiveDetailModal({
  directive, history, historyLoading,
  onClose, onSave, onDelete, onFetchHistory, onClearHistory,
  isOperator, onSetGlobal, globalTogglePending = false,
}: DirectiveDetailModalProps) {
  const [editing, setEditing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [showHistory, setShowHistory] = useState(false)

  const [label, setLabel] = useState('')
  const [content, setContent] = useState('')
  const [types, setTypes] = useState<string[]>([])

  const theme = useMantineTheme()
  const smBreakpoint = typeof theme.breakpoints.sm === 'string' ? parseFloat(theme.breakpoints.sm) : theme.breakpoints.sm
  const isMobile = useMediaQuery(`(max-width: ${(smBreakpoint * 16) - 1}px)`)

  if (!directive) return null

  const isReadOnly = directive.read_only
  const canEdit = !isReadOnly || isOperator
  const isProtected = directive.alpha === 0 && directive.beta === 1
  const isTier0Locked = directive.alpha === 0
  const isGlobal = directive.global_directive || isTier0Locked
  const canToggleGlobal = !!onSetGlobal && isOperator
  const globalTooltip = !isOperator
    ? 'Read-only — only the operator can set the global flag'
    : isTier0Locked
      ? 'Tier 0 directives are always global by rule'
      : (isGlobal ? 'Click to make local' : 'Click to make global')

  // Sync form when directive changes
  const needsSync = label !== directive.label || content !== directive.content
  if (needsSync) {
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
      size={isMobile ? '100%' : 'lg'}
      fullScreen={isMobile}
      classNames={{
        content: isMobile ? undefined : 'if-designer-modal-content',
        header: 'if-designer-modal-header',
        title: 'if-designer-modal-title',
        body: 'if-designer-modal-body',
      }}
    >
      <Stack gap="md">
        <Group gap="xs">
          <Badge variant="light" color="violet">v{directive.version}</Badge>
          {directive.global_directive && (
            <Badge size="xs" variant="light" color="orange" leftSection={<Globe size={10} />}>global</Badge>
          )}
          {isReadOnly && (
            <Badge size="xs" variant="light" color="gray" leftSection={<Lock size={10} />}>read-only</Badge>
          )}
          {directive.types?.map(t => (
            <Badge key={t} size="xs" variant="light" color="gray">{t}</Badge>
          ))}
          <Text size="xs" c="dimmed">
            by {directive.created_by} · {new Date(directive.created_at).toLocaleDateString()}
          </Text>
        </Group>

        {isReadOnly && !isOperator && (
          <Box p="sm" style={{ background: 'var(--status-warning-bg)', borderRadius: 8, border: '0.5px solid var(--status-warning-border)' }}>
            <Text size="xs" c="var(--status-warning-text)" fw={600}>
              This is a global safety directive. It applies to all users and can only be modified by the operator.
            </Text>
          </Box>
        )}

        <Group
          justify="space-between"
          align="center"
          p="sm"
          style={{
            background: isGlobal
              ? 'rgba(249, 115, 22, 0.10)'
              : 'rgba(107, 114, 128, 0.08)',
            border: isGlobal
              ? '0.5px solid rgba(249, 115, 22, 0.40)'
              : '0.5px solid var(--border-subtle)',
            borderRadius: 8,
          }}
        >
          <Group gap={8} align="center">
            {isGlobal
              ? <Globe size={14} color="#ea580c" />
              : <User size={14} color="#6b7280" />}
            <Box>
              <Text size="sm" fw={600} c={isGlobal ? '#ea580c' : 'var(--text-primary)'}>
                {isGlobal ? 'Global directive' : 'Local directive'}
              </Text>
              <Text size="xs" c="dimmed">
                {isTier0Locked
                  ? 'Tier 0 — always global by rule.'
                  : isGlobal
                    ? 'Applies to ALL users as a safety guardrail.'
                    : 'Applies only to this user.'}
              </Text>
            </Box>
          </Group>
          {canToggleGlobal ? (
            <Tooltip label={globalTooltip} position="top" withArrow>
              <Switch
                size="md"
                color="orange"
                checked={isGlobal}
                disabled={isTier0Locked || globalTogglePending}
                onChange={e => onSetGlobal?.(directive.alpha, directive.beta, e.currentTarget.checked)}
                aria-label={isGlobal ? 'Toggle to local' : 'Toggle to global'}
              />
            </Tooltip>
          ) : (
            <Tooltip label={globalTooltip} position="top" withArrow>
              <Lock size={14} color="var(--text-muted)" />
            </Tooltip>
          )}
        </Group>

        <Divider />

        {editing && canEdit ? (
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
              value={types}
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
            <ScrollArea.Autosize mah={400}>
              <Text size="sm" style={{ whiteSpace: 'pre-wrap', fontFamily: "'IBM Plex Mono', monospace" }}>
                {directive.content}
              </Text>
            </ScrollArea.Autosize>

            <Divider />

            <Group justify="space-between">
              <Button variant="subtle" size="xs" onClick={handleShowHistory}>
                {showHistory ? 'Hide History' : 'Show History'}
              </Button>
              {canEdit && (
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
              )}
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
