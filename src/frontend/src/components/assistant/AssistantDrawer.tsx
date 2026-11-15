import { useCallback, useEffect, useRef, useState } from 'react'
import { Drawer, Stack, Group, Paper, Text, Textarea, Button, Badge, Checkbox, Code, Loader, UnstyledButton, Alert } from '@mantine/core'
import { ChevronDown, ChevronRight, Send } from 'lucide-react'
import {
  approveProposal,
  fetchHistory,
  isTerminal,
  pollTurn,
  rejectProposal,
  submitTurn,
  type AssistantContext,
  type AssistantHistoryTurn,
  type AssistantJob,
  type AssistantProposal,
  type AssistantScope,
} from '@/api/assistant'

interface AssistantDrawerProps {
  opened: boolean
  onClose: () => void
  scope: AssistantScope
  context: AssistantContext
  readOnly?: boolean
}

function errorMessage(error: unknown): string {
  const body = (error as { response?: { data?: { detail?: string; error?: string } } })?.response?.data
  return body?.detail || body?.error || (error as Error)?.message || 'Request failed'
}

function formatDiff(diff: unknown): string {
  if (typeof diff === 'string') return diff
  return JSON.stringify(diff, null, 2)
}

function ProposalCard({ proposal, readOnly, onChange }: { proposal: AssistantProposal; readOnly?: boolean; onChange: (next: AssistantProposal) => void }) {
  const [confirmed, setConfirmed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const pending = proposal.state === 'pending'

  const decide = async (approve: boolean) => {
    setBusy(true)
    setError(null)
    try {
      onChange(approve ? await approveProposal(proposal.id, proposal.destructive ? proposal.target_id : undefined) : await rejectProposal(proposal.id))
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Paper withBorder p="sm" radius="md">
      <Stack gap="xs">
        <Group justify="space-between" wrap="nowrap">
          <Text size="sm" fw={600}>{proposal.summary || proposal.operation}</Text>
          <Group gap={4} wrap="nowrap">
            {proposal.destructive && <Badge color="red" variant="light">Destructive</Badge>}
            <Badge color={pending ? 'yellow' : proposal.state === 'rejected' ? 'gray' : 'green'} variant="light">{proposal.state}</Badge>
          </Group>
        </Group>
        <Code block style={{ maxHeight: 240, overflow: 'auto' }}>{formatDiff(proposal.diff)}</Code>
        {pending && proposal.destructive && (
          <Checkbox
            checked={confirmed}
            onChange={(event) => setConfirmed(event.currentTarget.checked)}
            label={`Delete target ${proposal.target_id}.`}
          />
        )}
        {error && <Text size="xs" c="red">{error}</Text>}
        {pending && (
          <Group gap="xs">
            <Button size="xs" color={proposal.destructive ? 'red' : undefined} loading={busy} disabled={readOnly || (proposal.destructive && !confirmed)} onClick={() => decide(true)}>
              Approve
            </Button>
            <Button size="xs" variant="default" disabled={busy || readOnly} onClick={() => decide(false)}>
              Reject
            </Button>
          </Group>
        )}
      </Stack>
    </Paper>
  )
}

export default function AssistantDrawer({ opened, onClose, scope, context, readOnly }: AssistantDrawerProps) {
  const [turns, setTurns] = useState<AssistantHistoryTurn[]>([])
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [message, setMessage] = useState('')
  const [job, setJob] = useState<AssistantJob | null>(null)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const cancelled = useRef(false)

  const loadHistory = useCallback(async () => {
    try {
      const history = await fetchHistory(scope)
      setTurns([...history.turns].reverse())
    } catch (err) {
      setError(errorMessage(err))
    }
  }, [scope])

  useEffect(() => {
    if (!opened) return
    cancelled.current = false
    setJob(null)
    setError(null)
    setExpanded(new Set())
    void loadHistory()
    return () => { cancelled.current = true }
  }, [opened, loadHistory])

  const toggleTurn = async (turn: AssistantHistoryTurn) => {
    const next = new Set(expanded)
    if (next.has(turn.id)) {
      next.delete(turn.id)
      setExpanded(next)
      return
    }
    next.add(turn.id)
    setExpanded(next)
    if (turn.content) return
    try {
      const history = await fetchHistory(scope, turn.id)
      const full = history.turns.find((item) => item.id === turn.id)
      if (full?.content) setTurns((current) => current.map((item) => (item.id === turn.id ? { ...item, content: full.content } : item)))
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  const send = async () => {
    const text = message.trim()
    if (!text) return
    setSending(true)
    setError(null)
    try {
      const submitted = await submitTurn(scope, text, context)
      setMessage('')
      setJob(submitted)
      const finished = await pollTurn(submitted.job_id, setJob, () => cancelled.current)
      if (!cancelled.current) {
        setJob(finished)
        await loadHistory()
      }
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setSending(false)
    }
  }

  const updateProposal = (next: AssistantProposal) => {
    setJob((current) => (current ? { ...current, proposals: current.proposals.map((item) => (item.id === next.id ? next : item)) } : current))
  }

  const running = job !== null && !isTerminal(job.status)

  return (
    <Drawer opened={opened} onClose={onClose} position="right" size="lg" title="Assistant">
      <Stack gap="md">
        {turns.length === 0 && <Text size="sm" c="dimmed">No turns yet.</Text>}
        <Stack gap={4}>
          {turns.map((turn) => (
            <Paper key={turn.id} withBorder p="xs" radius="sm">
              <UnstyledButton onClick={() => void toggleTurn(turn)} style={{ width: '100%' }}>
                <Group gap="xs" wrap="nowrap">
                  {expanded.has(turn.id) ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                  <Text size="sm" truncate style={{ flex: 1 }}>{turn.summary || 'Turn'}</Text>
                  <Text size="xs" c="dimmed">{new Date(turn.created_at).toLocaleDateString()}</Text>
                </Group>
              </UnstyledButton>
              {expanded.has(turn.id) && (
                <Stack gap={4} mt="xs">
                  {turn.content ? (
                    <>
                      <Text size="sm" fw={600}>{turn.content.request}</Text>
                      <Text size="sm" style={{ whiteSpace: 'pre-wrap' }}>{turn.content.reply}</Text>
                    </>
                  ) : (
                    <Loader size="xs" />
                  )}
                  {turn.error && <Text size="xs" c="red">{turn.error}</Text>}
                </Stack>
              )}
            </Paper>
          ))}
        </Stack>

        {job && (
          <Stack gap="xs">
            {running && <Group gap="xs"><Loader size="xs" /><Text size="sm" c="dimmed">Working.</Text></Group>}
            {job.result?.content && <Text size="sm" style={{ whiteSpace: 'pre-wrap' }}>{job.result.content}</Text>}
            {job.status === 'failed' && job.error && <Alert color="red">{job.error}</Alert>}
            {job.proposals.map((proposal) => (
              <ProposalCard key={proposal.id} proposal={proposal} readOnly={readOnly} onChange={updateProposal} />
            ))}
          </Stack>
        )}

        {error && <Alert color="red">{error}</Alert>}

        <Textarea
          value={message}
          onChange={(event) => setMessage(event.currentTarget.value)}
          placeholder="Write your request."
          autosize
          minRows={2}
          maxRows={6}
          maxLength={8000}
          disabled={readOnly || sending}
        />
        <Group justify="flex-end">
          <Button leftSection={<Send size={16} />} onClick={() => void send()} loading={sending} disabled={readOnly || !message.trim() || running}>
            Send
          </Button>
        </Group>
      </Stack>
    </Drawer>
  )
}
