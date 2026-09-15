import { useEffect, useRef, useState } from 'react'
import { Alert, Button, Group, Modal, NumberInput, Select, Stack, Text, TextInput } from '@mantine/core'
import { useNavigate } from 'react-router-dom'
import type { BlockTransitionInput, TemplateListEntry, WeekStartDay } from '@powerlifting/types'
import { confirmApplyTemplate, fetchTemplates, transitionBlock } from '@/api/client'
import { useAuth } from '@/auth/AuthProvider'
import { useProgramStore } from '@/store/programStore'

const weekdays: WeekStartDay[] = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
const lifts = ['squat', 'bench', 'deadlift'] as const

export default function BlockTransitionPanel() {
  const { program, version, isDirty, loadProgram, loadVersions } = useProgramStore()
  const { permissions } = useAuth()
  const navigate = useNavigate()
  const [action, setAction] = useState<BlockTransitionInput['action'] | null>(null)
  const [name, setName] = useState('Next Block')
  const [currentName, setCurrentName] = useState('')
  const [startDate, setStartDate] = useState(new Date().toISOString().slice(0, 10))
  const [weekStart, setWeekStart] = useState<WeekStartDay>('Monday')
  const [maxes, setMaxes] = useState<Record<string, number>>({})
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  const [template, setTemplate] = useState('designer')
  const [templates, setTemplates] = useState<TemplateListEntry[]>([])
  const [renameId, setRenameId] = useState('')
  const attempt = useRef({ payload: '', key: '' })
  useEffect(() => {
    if (action && permissions.includes('templates:read')) void fetchTemplates().then(setTemplates).catch(() => setError('Templates could not be loaded. Retry when connected.'))
  }, [action, permissions])
  if (!program || version !== 'current' || !permissions.includes('program:write')) return null
  const blocks = program.meta.blocks || []
  const active = blocks.find(block => block.status === 'active')
  const hasActive = Boolean(active || !blocks.length)
  const sourceId = hasActive ? active?.id || 'current' : blocks.filter(block => block.status === 'completed').at(-1)?.id
  const unfinished = program.sessions.filter(session => (session.block || 'current') === 'current' && !session.completed && session.status !== 'skipped').length

  function open(nextAction: BlockTransitionInput['action']) {
    setAction(nextAction)
    setWeekStart(program!.meta.program_week_start_day || 'Monday')
    setCurrentName(blocks.find(block => block.id === sourceId)?.name || program!.meta.program_name || '')
    setRenameId(sourceId || 'current')
    setMaxes(Object.fromEntries(lifts.map(lift => [lift, program!.current_maxes?.[lift] || 0])))
    setError('')
  }

  async function submit() {
    if (!action || !sourceId) return
    const starting = action === 'start_next' || action === 'complete_and_start'
    const payload = {
      action, block_id: action === 'rename' ? renameId : sourceId, expected_revision: program!.meta.revision ?? 0,
      current_name: currentName.trim() || undefined,
      ...(action === 'rename' ? { name: currentName.trim() } : {}),
      ...(starting ? { name: name.trim(), start_date: startDate, week_start_day: weekStart, start_maxes_kg: maxes, next_program: { phases: [], sessions: [] } } : {}),
    }
    const serialized = JSON.stringify([payload, template])
    if (attempt.current.payload !== serialized) attempt.current = { payload: serialized, key: crypto.randomUUID() }
    setPending(true)
    setError('')
    try {
      if (starting && template !== 'designer') {
        await confirmApplyTemplate(template, { target: 'new_block', block_name: name.trim(), start_date: startDate, week_start_day: weekStart, backfilled_maxes: maxes, expected_revision: payload.expected_revision, idempotency_key: attempt.current.key })
      } else {
        await transitionBlock({ ...payload, idempotency_key: attempt.current.key })
      }
      await loadProgram('current')
      await loadVersions()
      setAction(null)
      if (starting) navigate(template === 'designer' ? '/designer/phases' : '/sessions')
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Block transition failed. Your existing Sessions are preserved.')
    } finally { setPending(false) }
  }

  return <Stack gap="xs">
    <Text fw={600}>{active?.name || (hasActive ? program.meta.program_name : 'Block completed')}</Text>
    {isDirty && <Alert color="yellow">Save your Session changes before changing Blocks.</Alert>}
    <Group>
      <Button mih={44} variant="subtle" disabled={isDirty || !sourceId} onClick={() => open('rename')}>Rename Block</Button>
      {hasActive && <Button mih={44} variant="default" disabled={isDirty} onClick={() => open('complete')}>Complete Block</Button>}
      <Button mih={44} disabled={isDirty || !sourceId} onClick={() => open(hasActive ? 'complete_and_start' : 'start_next')}>
        {hasActive ? 'Complete and start next Block' : 'Start next Block'}
      </Button>
    </Group>
    <Modal opened={Boolean(action)} onClose={() => !pending && setAction(null)} title={action === 'rename' ? 'Rename Block' : action === 'complete' ? 'Complete Block' : 'Start next Block'} closeOnClickOutside={!pending} closeOnEscape={!pending}>
      <Stack>
        {action === 'rename' && <>
          <Select label="Block" value={renameId} data={blocks.length ? blocks.map(block => ({ value: block.id, label: block.name })) : [{ value: 'current', label: program.meta.program_name || 'Current Block' }]} onChange={value => { setRenameId(value || ''); setCurrentName(blocks.find(block => block.id === value)?.name || program.meta.program_name || '') }} />
          <TextInput label="Block name" required maxLength={80} value={currentName} onChange={event => setCurrentName(event.currentTarget.value)} />
        </>}
        {hasActive && action !== 'rename' && <Alert color={unfinished ? 'yellow' : 'blue'}>{unfinished ? `${unfinished} unfinished Sessions will stay in the archived Block with their current statuses.` : 'The Block and its Session history will be archived.'}</Alert>}
        {action && !['complete', 'rename'].includes(action) && <>
          <Select label="Start from" value={template} onChange={value => setTemplate(value || 'designer')} data={[{ value: 'designer', label: 'Program designer' }, ...(permissions.includes('templates:write') ? templates.map(item => ({ value: item.sk, label: item.name })) : [])]} searchable />
          <TextInput label="Next Block name" required maxLength={80} value={name} onChange={event => setName(event.currentTarget.value)} />
          <TextInput label="Start date" type="date" required value={startDate} onChange={event => setStartDate(event.currentTarget.value)} />
          <Select label="Week starts" data={weekdays} value={weekStart} onChange={value => value && setWeekStart(value as WeekStartDay)} />
          <Text size="sm">Confirm best-known current maxes in kg. Week numbering restarts at 1.</Text>
          {lifts.map(lift => <NumberInput key={lift} label={`${lift[0].toUpperCase()}${lift.slice(1)} 1RM (kg${maxes[lift] ? ` / ${(maxes[lift] * 2.20462).toFixed(1)} lb` : ''})`} min={0.5} step={2.5} value={maxes[lift] || ''} onChange={value => setMaxes(previous => ({ ...previous, [lift]: Number(value) }))} required />)}
        </>}
        {error && <Alert color="red">{error}<Button variant="subtle" onClick={() => loadProgram('current')}>Reload current revision</Button></Alert>}
        <Group justify="flex-end">
          <Button variant="default" mih={44} disabled={pending} onClick={() => setAction(null)}>Cancel</Button>
          <Button mih={44} loading={pending} disabled={action === 'rename' ? !currentName.trim() : action !== 'complete' && (!name.trim() || !startDate || lifts.some(lift => !(maxes[lift] > 0)))} onClick={submit}>
            {action === 'rename' ? 'Save name' : action === 'complete' ? 'Complete Block' : 'Start Block'}
          </Button>
        </Group>
      </Stack>
    </Modal>
  </Stack>
}
