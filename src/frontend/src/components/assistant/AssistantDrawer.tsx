import { useCallback, useEffect, useRef, useState } from 'react'
import { Drawer, Stack, Group, Paper, Text, Textarea, Button, Badge, Checkbox, Code, Loader, UnstyledButton, Alert } from '@mantine/core'
import { ChevronDown, ChevronRight, Send, Square } from 'lucide-react'
import {
  approveProposal,
  cancelJob,
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
  conversationId?: string
}

const wrapText = { whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', wordBreak: 'break-word' } as const

function errorMessage(error: unknown): string {
  const body = (error as { response?: { data?: { detail?: string; error?: string } } })?.response?.data
  return body?.detail || body?.error || (error as Error)?.message || 'Request failed'
}

function formatDiff(diff: unknown): string {
  if (typeof diff === 'string') return diff
  return JSON.stringify(diff, null, 2)
}

function stateLabel(state: string) {
  switch (state) {
    case 'committed':
    case 'applied':
      return 'Applied'
    case 'rejected':
      return 'Rejected'
    case 'failed':
    case 'stale':
      return 'Failed'
  }
  return state
}

function stateColor(state: string) {
  switch (state) {
    case 'pending':
      return 'yellow'
    case 'committed':
    case 'applied':
      return 'green'
    case 'failed':
    case 'stale':
      return 'red'
  }
  return 'gray'
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
            <Badge color={stateColor(proposal.state)} variant="light">{stateLabel(proposal.state)}</Badge>
          </Group>
        </Group>
        <Code block style={{ ...wrapText, maxHeight: '40dvh', overflowY: 'auto', overflowX: 'hidden' }}>{formatDiff(proposal.diff)}</Code>
        {pending && proposal.destructive && (
          <Checkbox
            checked={confirmed}
            onChange={(event) => setConfirmed(event.currentTarget.checked)}
            label={`Delete target ${proposal.target_id}.`}
          />
        )}
        {(proposal.state === 'failed' || proposal.state === 'stale') && (
          <Stack gap={2}>
            <Text size="sm" fw={600} c="red">Approved, but the write failed</Text>
            {proposal.commit_error && <Text size="xs" c="red" style={wrapText}>{proposal.commit_error}</Text>}
          </Stack>
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

export default function AssistantDrawer({ opened, onClose, scope, context, readOnly, conversationId }: AssistantDrawerProps) {
  const [turns, setTurns] = useState<AssistantHistoryTurn[]>([])
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [message, setMessage] = useState('')
  const [job, setJob] = useState<AssistantJob | null>(null)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [progressOpen, setProgressOpen] = useState(true)
  const cancelled = useRef(false)
  const scroller = useRef<HTMLDivElement>(null)
  const pinned = useRef(true)

  const loadHistory = useCallback(async () => {
    try {
      const history = await fetchHistory(scope, undefined, conversationId)
      const ordered = [...history.turns].reverse()
      setTurns(ordered)
      const newest = ordered[ordered.length - 1]
      if (newest) {
        setExpanded(new Set([newest.id]))
        if (!newest.content) {
          const full = await fetchHistory(scope, newest.id, conversationId)
          const found = full.turns.find((item) => item.id === newest.id)
          if (found?.content) setTurns((current) => current.map((item) => (item.id === newest.id ? { ...item, content: found.content } : item)))
        }
      }
    } catch (err) {
      setError(errorMessage(err))
    }
  }, [scope, conversationId])

  useEffect(() => {
    if (!opened) return
    cancelled.current = false
    setJob(null)
    setError(null)
    setExpanded(new Set())
    pinned.current = true
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
      const history = await fetchHistory(scope, turn.id, conversationId)
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
  const progressBox = useRef<HTMLDivElement>(null)
  const progressText = job?.progress?.text || ''
  useEffect(() => {
    const node = progressBox.current
    if (node) node.scrollTop = node.scrollHeight
  }, [progressText, progressOpen])
  const activity = job?.activity?.length ? job.activity[job.activity.length - 1].label : 'working'

  useEffect(() => {
    const node = scroller.current
    if (node && pinned.current) node.scrollTop = node.scrollHeight
  }, [turns, expanded, job])

  const onScroll = () => {
    const node = scroller.current
    if (node) pinned.current = node.scrollHeight - node.scrollTop - node.clientHeight < 48
  }

  const stop = async () => {
    if (!job) return
    try {
      setJob(await cancelJob(job.job_id))
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  const summaryOf = (turn: AssistantHistoryTurn) =>
    turn.summary || turn.content?.reply?.split('\n').find((line) => line.trim()) || 'Turn'

  return (
    <Drawer
      opened={opened}
      onClose={onClose}
      position="right"
      size="lg"
      title="Assistant"
      styles={{ content: { display: 'flex', flexDirection: 'column' }, body: { display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0 } }}
    >
      <Stack gap="md" style={{ flex: 1, minHeight: 0 }}>
        <Stack gap="md" ref={scroller} onScroll={onScroll} style={{ flex: 1, minHeight: 0, overflowY: 'auto', overflowX: 'hidden' }}>
        {turns.length === 0 && <Text size="sm" c="dimmed">No turns yet.</Text>}
        <Stack gap={4}>
          {turns.map((turn) => (
            <Paper key={turn.id} withBorder p="xs" radius="sm">
              <UnstyledButton onClick={() => void toggleTurn(turn)} style={{ width: '100%' }}>
                <Group gap="xs" wrap="nowrap">
                  {expanded.has(turn.id) ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                  <Text size="sm" truncate style={{ flex: 1 }}>{summaryOf(turn)}</Text>
                  <Text size="xs" c="dimmed">{new Date(turn.created_at).toLocaleDateString()}</Text>
                </Group>
              </UnstyledButton>
              {expanded.has(turn.id) && (
                <Stack gap={4} mt="xs">
                  {turn.content ? (
                    <>
                      <Text size="sm" fw={600}>{turn.content.request}</Text>
                      <Text size="sm" style={wrapText}>{turn.content.reply}</Text>
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
            {running && (
              <Group gap="xs" justify="space-between" wrap="nowrap">
                <UnstyledButton onClick={() => setProgressOpen((open) => !open)} style={{ flex: 1, minWidth: 0 }}>
                  <Group gap="xs" wrap="nowrap">
                    {progressOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                    <Loader size="xs" />
                    <Text size="xs" c="dimmed" truncate>{job.progress?.stage || activity}</Text>
                  </Group>
                </UnstyledButton>
                <Button size="compact-xs" variant="default" leftSection={<Square size={12} />} onClick={() => void stop()}>Stop</Button>
              </Group>
            )}
            {running && progressOpen && progressText && (
              <div ref={progressBox} style={{ maxHeight: '35dvh', overflowY: 'auto', overflowX: 'hidden' }}>
                <Text size="sm" c="dimmed" style={wrapText}>{progressText}</Text>
              </div>
            )}
            {job.status === 'cancelled' && <Text size="sm" c="dimmed">Stopped</Text>}
            {job.result?.content && <Text size="sm" style={wrapText}>{job.result.content}</Text>}
            {job.status === 'failed' && job.error && <Alert color="red">{job.error}</Alert>}
            {job.proposals.map((proposal) => (
              <ProposalCard key={proposal.id} proposal={proposal} readOnly={readOnly} onChange={updateProposal} />
            ))}
          </Stack>
        )}

        {error && <Alert color="red">{error}</Alert>}
        </Stack>

        {!conversationId && <Textarea
          value={message}
          onChange={(event) => setMessage(event.currentTarget.value)}
          placeholder="Write your request."
          autosize
          minRows={2}
          maxRows={6}
          maxLength={8000}
          disabled={readOnly || sending}
        />}
        {!conversationId && <Group justify="flex-end">
          <Button leftSection={<Send size={16} />} onClick={() => void send()} loading={sending} disabled={readOnly || !message.trim() || running}>
            Send
          </Button>
        </Group>}
      </Stack>
    </Drawer>
  )
}
