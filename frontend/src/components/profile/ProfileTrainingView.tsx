import { useEffect, useMemo, useState } from 'react'
import { Alert, Badge, Box, Button, Collapse, Group, Loader, Paper, SimpleGrid, Stack, Table, Text, UnstyledButton } from '@mantine/core'
import { AlertCircle, ChevronDown, ChevronRight } from 'lucide-react'
import type { Exercise, GlossaryExercise, Program, Session } from '@powerlifting/types'
import { fetchViewedProgram, fetchViewedWeeklyAnalysis } from '@/api/profiles'
import type { WeeklyAnalysis } from '@/api/analytics'
import { fetchGlossary } from '@/api/client'
import { AlertsStrip } from '@/components/analysis/AlertsStrip'
import { WeeklyData } from '@/components/analysis/WeeklyData'
import { useSettingsStore } from '@/store/settingsStore'
import { toDisplayUnit } from '@/utils/units'
import { glossaryCategoryLookup, glossaryMuscleLookup, muscleGroupAverages, perLiftBreakdown } from '@/utils/weeklyBreakdown'

export type ProfileTrainingTab = 'sessions' | 'analysis'

const PAGE_SIZE = 20
const ANALYSIS_WINDOWS = [1, 4, 8] as const

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

function SummaryCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <Paper withBorder p="md" radius="md" className="if-metric-card">
      <Text size="xs" c="var(--text-secondary)">{label}</Text>
      <Text fz="xl" fw={700}>{value}</Text>
      {sub && <Text size="xs" c="var(--text-secondary)">{sub}</Text>}
    </Paper>
  )
}

function ReadOnlyAnalysis({ athlete, program, unit }: { athlete: string; program: Program; unit: 'kg' | 'lb' }) {
  const [weeks, setWeeks] = useState<number>(4)
  const [data, setData] = useState<WeeklyAnalysis | null>(null)
  const [glossary, setGlossary] = useState<GlossaryExercise[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchGlossary().then(setGlossary).catch(() => setGlossary([]))
  }, [])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    fetchViewedWeeklyAnalysis(athlete, weeks)
      .then((result) => { if (!cancelled) setData(result) })
      .catch(() => { if (!cancelled) setError('Analysis is unavailable for this Athlete.') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [athlete, weeks])

  const windowSessions = useMemo(() => {
    if (!data?.window_start || !data?.window_end) return []
    return (program.sessions ?? []).filter((session) =>
      (session.completed || session.status === 'logged' || session.status === 'completed') &&
      session.status !== 'skipped' &&
      session.date >= data.window_start! &&
      session.date <= data.window_end!,
    )
  }, [data?.window_end, data?.window_start, program.sessions])

  const muscleGroupAvgWeekly = useMemo(() => muscleGroupAverages(windowSessions, glossaryMuscleLookup(glossary), weeks), [glossary, weeks, windowSessions])
  const perLiftDetails = useMemo(() => perLiftBreakdown(windowSessions, glossaryCategoryLookup(glossary)), [glossary, windowSessions])

  const maxes = data?.current_maxes
  const projection = data?.projections?.[0]

  return (
    <Stack gap="md" data-testid="profile-analysis">
      <div className="if-tab-group" role="group" aria-label="Analysis window">
        {ANALYSIS_WINDOWS.map((value) => (
          <button key={value} type="button" className="if-tab-button" data-active={weeks === value} onClick={() => setWeeks(value)}>
            {value === 1 ? '1 week' : `${value} weeks`}
          </button>
        ))}
      </div>
      {loading && <Group justify="center" py="xl"><Loader size="sm" /></Group>}
      {!loading && error && <Alert color="red" icon={<AlertCircle size={16} />}>{error}</Alert>}
      {!loading && data && (
        <>
          <AlertsStrip alerts={data.alerts || []} />
          <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} spacing="md">
            <SummaryCard
              label="Current maxes"
              value={weightText(maxes ? (maxes.squat ?? 0) + (maxes.bench ?? 0) + (maxes.deadlift ?? 0) : null, unit)}
              sub={maxes ? `S ${weightText(maxes.squat, unit)} · B ${weightText(maxes.bench, unit)} · D ${weightText(maxes.deadlift, unit)}` : undefined}
            />
            <SummaryCard label="Estimated DOTS" value={data.estimated_dots !== null ? data.estimated_dots.toFixed(1) : '--'} sub={data.estimated_dots_reason ?? undefined} />
            <SummaryCard
              label="Compliance"
              value={data.compliance ? `${data.compliance.pct.toFixed(0)}%` : '--'}
              sub={data.compliance ? `${data.compliance.completed}/${data.compliance.planned} sessions · ${data.compliance.phase}` : undefined}
            />
            <SummaryCard
              label="Projected total"
              value={projection ? weightText(projection.total, unit) : '--'}
              sub={projection ? `${projection.comp_name ?? 'Next competition'}${projection.weeks_to_comp !== undefined ? ` · ${projection.weeks_to_comp} wk` : ''}` : (data.projection_reason ?? undefined)}
            />
          </SimpleGrid>
          <SummaryCard
            label="Fatigue"
            value={data.fatigue_index !== null ? `${(data.fatigue_index * 100).toFixed(0)}%` : '--'}
            sub={`${data.sessions_analyzed} sessions analyzed`}
          />
          <WeeklyData data={data} viewMode="raw" perLiftDetails={perLiftDetails} muscleGroupAvgWeekly={muscleGroupAvgWeekly} analysisWeeks={weeks} unit={unit} />
        </>
      )}
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
