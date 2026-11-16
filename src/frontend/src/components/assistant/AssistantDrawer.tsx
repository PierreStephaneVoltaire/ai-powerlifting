import { useCallback, useEffect, useRef, useState } from 'react'
import { Drawer, Stack, Group, Paper, Text, Textarea, Button, Badge, Checkbox, Code, Loader, UnstyledButton, Alert } from '@mantine/core'
import { ChevronDown, ChevronRight, Send, Square } from 'lucide-react'
import {
  approveProposal,
  cancelJob,
  fetchHistory,
  fetchJob,
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
import AssistantProgress from './AssistantProgress'

interface AssistantDrawerProps {
  opened: boolean
  onClose: () => void
  scope: AssistantScope
  context: AssistantContext
  readOnly?: boolean
  conversationId?: string
  onApplied?: () => Promise<void>
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

export default function AssistantDrawer({ opened, onClose, scope, context, readOnly, conversationId, onApplied }: AssistantDrawerProps) {
  const [turns, setTurns] = useState<AssistantHistoryTurn[]>([])
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [message, setMessage] = useState('')
  const [job, setJob] = useState<AssistantJob | null>(null)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const applied = useRef(new Set<string>())
  const scroller = useRef<HTMLDivElement>(null)
  const pinned = useRef(true)

  const loadHistory = useCallback(async (expand?: string) => {
    try {
      const history = await fetchHistory(scope, expand, conversationId)
      const ordered = [...history.turns].reverse()
      setTurns((current) => ordered.map((turn) => ({ ...turn, content: turn.content || current.find((item) => item.id === turn.id)?.content })))
      const newest = ordered[ordered.length - 1]
      if (newest) {
        setExpanded((current) => new Set([...current, newest.id]))
        if (!newest.content) {
          const full = await fetchHistory(scope, newest.id, conversationId)
          const found = full.turns.find((item) => item.id === newest.id)
          if (found?.content) setTurns((current) => current.map((item) => (item.id === newest.id ? { ...item, content: found.content } : item)))
        }
      }
      return ordered
    } catch (err) {
      setError(errorMessage(err))
    }
  }, [scope, conversationId])

  useEffect(() => {
    if (!opened) return
    setJob(null)
    setTurns([])
    setError(null)
    setExpanded(new Set())
    pinned.current = true
    let cancelled = false
    void loadHistory().then(async (history) => {
      const newest = history?.at(-1)
      if (newest && !conversationId) {
        const active = await fetchJob(newest.id)
        if (!cancelled) setJob(active)
      }
    }).catch((err) => { if (!cancelled) setError(errorMessage(err)) })
    return () => { cancelled = true }
  }, [opened, loadHistory])

  useEffect(() => {
    if (!opened || !job || isTerminal(job.status)) return
    let cancelled = false
    void pollTurn(job.job_id, (next) => { if (!cancelled) setJob(next) }, () => cancelled)
      .then(async () => { if (!cancelled) await loadHistory(job.job_id) })
      .catch((err) => { if (!cancelled) setError(errorMessage(err)) })
    return () => { cancelled = true }
  }, [opened, job?.job_id, loadHistory])

  useEffect(() => {
    if (!onApplied) return
    const committed = job?.proposals.filter((proposal) => ['committed', 'applied'].includes(proposal.state) && !applied.current.has(proposal.id)) || []
    if (!committed.length) return
    committed.forEach((proposal) => applied.current.add(proposal.id))
    void onApplied().catch((err) => setError(`Change applied, but refreshing the page failed: ${errorMessage(err)}`))
  }, [job, onApplied])

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
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setSending(false)
    }
  }

  const updateProposal = (next: AssistantProposal, turnId?: string) => {
    setJob((current) => (current ? { ...current, proposals: current.proposals.map((item) => (item.id === next.id ? next : item)) } : current))
    setTurns((current) => current.map((turn) => turn.content ? { ...turn, content: { ...turn.content, proposals: turn.content.proposals?.map((item) => item.id === next.id ? next : item) } } : turn))
    if (turnId && turnId !== job?.job_id) void fetchJob(turnId).then(setJob).catch((err) => setError(errorMessage(err)))
  }

  const running = job !== null && !isTerminal(job.status)
  const jobInHistory = turns.some((turn) => turn.id === job?.job_id && isTerminal(turn.status) && turn.content)
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
                      {(turn.id !== job?.job_id || jobInHistory) && <AssistantProgress progress={turn.content.progress} />}
                      <Text size="sm" style={wrapText}>{turn.content.reply}</Text>
                      {(turn.id !== job?.job_id || jobInHistory) && turn.content.proposals?.map((proposal) => (
                        <ProposalCard key={proposal.id} proposal={proposal} readOnly={readOnly} onChange={(next) => updateProposal(next, turn.id)} />
                      ))}
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

        {job && !jobInHistory && (
          <Stack gap="xs">
            <AssistantProgress progress={job.progress} running={running} activity={activity} />
            {running && (
              <Group gap="xs" justify="space-between" wrap="nowrap">
                <Button size="compact-xs" variant="default" leftSection={<Square size={12} />} onClick={() => void stop()}>Stop</Button>
              </Group>
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
