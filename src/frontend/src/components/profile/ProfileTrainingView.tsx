import { useEffect, useMemo, useState } from 'react'
import { Alert, Badge, Box, Button, Collapse, Group, Loader, Paper, Stack, Table, Text, UnstyledButton } from '@mantine/core'
import { AlertCircle, ChevronDown, ChevronRight } from 'lucide-react'
import type { Exercise, Program, Session } from '@powerlifting/types'
import { fetchViewedProgram } from '@/api/profiles'
import { fetchBlockAnalysis, fetchProgramBlocks, type BlockAnalysisBundle } from '@/api/analytics'
import { BlockWeeklySurface } from '@/components/analysis/BlockWeeklySurface'
import { useSettingsStore } from '@/store/settingsStore'
import { toDisplayUnit } from '@/utils/units'

export type ProfileTrainingTab = 'sessions' | 'analysis'

const PAGE_SIZE = 20

function isoToday(): string {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
}

function sessionStatus(session: Session): { label: string; color: string } {
  if (session.status === 'skipped') return { label: 'Skipped', color: 'gray' }
  if (session.completed || session.status === 'completed') return { label: 'Completed', color: 'green' }
  if (session.status === 'logged') return { label: 'Logged', color: 'blue' }
  return { label: 'Planned', color: 'yellow' }
}

function weightText(kg: number | null | undefined, unit: 'kg' | 'lb'): string {
  if (kg === null || kg === undefined || !Number.isFinite(kg) || kg <= 0) return '--'
  const value = toDisplayUnit(kg, unit)
  return `${Number.isInteger(value) ? value : value.toFixed(1)} ${unit}`
}

function exercisePrescription(exercise: Exercise, unit: 'kg' | 'lb'): string {
  const load = weightText(exercise.kg, unit)
  return `${exercise.sets} × ${exercise.reps}${load === '--' ? '' : ` @ ${load}`}`
}

function setSummary(exercise: Exercise, unit: 'kg' | 'lb'): string | null {
  if (!exercise.sets_data?.length) return null
  return exercise.sets_data
    .map((set, index) => {
      const status = exercise.set_statuses?.[index]
      const load = weightText(set.kg ?? exercise.kg, unit)
      const parts = [`${set.reps ?? exercise.reps}`, load === '--' ? '' : `@ ${load}`, set.rpe ? `RPE ${set.rpe}` : '', status === 'failed' ? '(failed)' : status === 'skipped' ? '(skipped)' : '']
      return parts.filter(Boolean).join(' ')
    })
    .join(' · ')
}

function ReadOnlySession({ session, unit }: { session: Session; unit: 'kg' | 'lb' }) {
  const [open, setOpen] = useState(false)
  const status = sessionStatus(session)
  const exercises = session.exercises?.length ? session.exercises : (session.planned_exercises ?? []).map((planned) => ({ ...planned, notes: '' }) as Exercise)
  return (
    <Paper withBorder radius="md" className="if-card" data-testid="profile-session-row">
      <UnstyledButton onClick={() => setOpen((value) => !value)} w="100%" p="md" aria-expanded={open}>
        <Group justify="space-between" wrap="nowrap" gap="sm">
          <Group gap="sm" wrap="nowrap" style={{ minWidth: 0 }}>
            {open ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
            <Stack gap={0} style={{ minWidth: 0 }}>
              <Text fw={600} truncate>{session.date} · {session.day}</Text>
              <Text size="xs" c="var(--text-secondary)" truncate>
                Week {session.week_number}{session.phase?.name ? ` · ${session.phase.name}` : ''} · {exercises.length} exercises
              </Text>
            </Stack>
          </Group>
          <Group gap="xs" wrap="nowrap">
            {session.session_rpe ? <Badge variant="light" color="gray">RPE {session.session_rpe}</Badge> : null}
            <Badge variant="light" color={status.color}>{status.label}</Badge>
          </Group>
        </Group>
      </UnstyledButton>
      <Collapse expanded={open}>
        <Stack gap="sm" px="md" pb="md">
          {exercises.length > 0 ? (
            <Box style={{ overflowX: 'auto' }}>
              <Table fz="sm" verticalSpacing="xs">
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>Exercise</Table.Th>
                    <Table.Th>Prescription</Table.Th>
                    <Table.Th>RPE</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {exercises.map((exercise, index) => {
                    const sets = setSummary(exercise, unit)
                    return (
                      <Table.Tr key={exercise.id ?? `${exercise.name}-${index}`}>
                        <Table.Td>
                          <Text size="sm" fw={500}>{exercise.name}</Text>
                          {sets && <Text size="xs" c="var(--text-secondary)">{sets}</Text>}
                          {exercise.notes && <Text size="xs" c="var(--text-secondary)">{exercise.notes}</Text>}
                        </Table.Td>
                        <Table.Td>{exercisePrescription(exercise, unit)}</Table.Td>
                        <Table.Td>{exercise.rpe ?? exercise.rpe_target ?? '--'}</Table.Td>
                      </Table.Tr>
                    )
                  })}
                </Table.Tbody>
              </Table>
            </Box>
          ) : (
            <Text size="sm" c="var(--text-secondary)">No exercises recorded.</Text>
          )}
          <Group gap="lg" wrap="wrap">
            {session.body_weight_kg ? <Text size="xs" c="var(--text-secondary)">Bodyweight {weightText(session.body_weight_kg, unit)}</Text> : null}
          </Group>
          {session.session_notes && <Text size="sm" style={{ whiteSpace: 'pre-wrap' }}>{session.session_notes}</Text>}
        </Stack>
      </Collapse>
    </Paper>
  )
}

function ReadOnlySessions({ program, unit }: { program: Program; unit: 'kg' | 'lb' }) {
  const [scope, setScope] = useState<'past' | 'upcoming'>('past')
  const [visible, setVisible] = useState(PAGE_SIZE)
  const today = isoToday()
  const sessions = useMemo(() => {
    const all = program.sessions ?? []
    return scope === 'past'
      ? all.filter((session) => session.date <= today).sort((a, b) => b.date.localeCompare(a.date))
      : all.filter((session) => session.date > today).sort((a, b) => a.date.localeCompare(b.date))
  }, [program.sessions, scope, today])

  return (
    <Stack gap="sm" data-testid="profile-sessions">
      <div className="if-tab-group" role="group" aria-label="Session range">
        {(['past', 'upcoming'] as const).map((value) => (
          <button key={value} type="button" className="if-tab-button" data-active={scope === value} onClick={() => { setScope(value); setVisible(PAGE_SIZE) }}>
            {value === 'past' ? 'Past' : 'Upcoming'}
          </button>
        ))}
      </div>
      {sessions.length === 0 && <Text size="sm" c="var(--text-secondary)">No sessions to show.</Text>}
      {sessions.slice(0, visible).map((session, index) => (
        <ReadOnlySession key={session.id ?? `${session.date}-${index}`} session={session} unit={unit} />
      ))}
      {visible < sessions.length && (
        <Button variant="default" onClick={() => setVisible((value) => value + PAGE_SIZE)}>
          Show more
        </Button>
      )}
    </Stack>
  )
}

function ReadOnlyAnalysis({ athlete, program, unit }: { athlete: string; program: Program; unit: 'kg' | 'lb' }) {
  const [bundle, setBundle] = useState<BlockAnalysisBundle | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    setBundle(null)
    fetchProgramBlocks(athlete)
      .then((blocks) => {
        const current = blocks.find((block) => block.isCurrent)
        if (!current) throw new Error('No current block')
        return fetchBlockAnalysis(current.blockKey, false, athlete)
      })
      .then((result) => { if (!cancelled) setBundle(result) })
      .catch(() => { if (!cancelled) setError('Block analysis is unavailable for this Athlete.') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [athlete])

  if (loading) return <Group justify="center" py="xl"><Loader size="sm" /></Group>
  if (error || !bundle) return <Alert color="yellow" icon={<AlertCircle size={16} />}>{error ?? 'Block analysis is unavailable.'}</Alert>

  return (
    <Stack gap="md" data-testid="profile-analysis">
      <BlockWeeklySurface
        program={program}
        bundle={bundle}
        unit={unit}
        sex={program.meta?.sex ?? null}
        version="current"
        viewAthlete={athlete}
      />
    </Stack>
  )
}

export default function ProfileTrainingView({ athlete, tab, analysisAvailable }: { athlete: string; tab: ProfileTrainingTab; analysisAvailable: boolean }) {
  const { unit } = useSettingsStore()
  const [program, setProgram] = useState<Program | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    setProgram(null)
    fetchViewedProgram(athlete)
      .then((result) => { if (!cancelled) setProgram(result) })
      .catch(() => { if (!cancelled) setError('This Athlete has not shared their Sessions.') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [athlete])

  if (loading) return <Group justify="center" py="xl"><Loader size="sm" /></Group>
  if (error || !program) return <Alert color="yellow" icon={<AlertCircle size={16} />}>{error ?? 'Sessions are unavailable.'}</Alert>
  if (tab === 'analysis') {
    return analysisAvailable
      ? <ReadOnlyAnalysis athlete={athlete} program={program} unit={unit} />
      : <Alert color="yellow" icon={<AlertCircle size={16} />}>This Athlete has not shared their Analysis.</Alert>
  }
  return <ReadOnlySessions program={program} unit={unit} />
}
