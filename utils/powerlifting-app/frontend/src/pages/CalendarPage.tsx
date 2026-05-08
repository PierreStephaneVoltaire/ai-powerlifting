import { useEffect, useMemo, useRef } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import {
  Group,
  Badge,
  Paper,
  Stack,
  Text,
  SegmentedControl,
  Box,
  ThemeIcon,
  UnstyledButton,
  Center,
} from '@mantine/core'
import { Calendar } from '@mantine/dates'
import { useProgramStore } from '@/store/programStore'
import { phaseColor } from '@/utils/phases'
import { startOfWeek, format } from 'date-fns'
import { findClosestSessionToToday, parseLocalDate } from '@/utils/dates'
import { normalizeExerciseName } from '@/utils/volume'
import { Check } from 'lucide-react'
import dayjs from 'dayjs'
import type { Session } from '@powerlifting/types'
import MuscleVolumeChart from '@/components/charts/MuscleVolumeChart'
import { SessionsCompactView } from '@/components/sessions/SessionsCompactView'

type ViewType = 'Month' | 'Agenda' | 'Compact'
const SESSION_DATE_PARAM = /^\d{4}-\d{2}-\d{2}$/

function parseSessionView(raw: string | null): ViewType {
  return raw === 'Month' || raw === 'Compact' || raw === 'Agenda' ? raw : 'Agenda'
}

function parseDateParam(raw: string | null): string | null {
  return raw && SESSION_DATE_PARAM.test(raw) ? raw : null
}

function countUniqueExerciseNames(session: Session): number {
  const entries = session.exercises.length > 0 ? session.exercises : session.planned_exercises ?? []
  return new Set(entries.map((exercise) => normalizeExerciseName(exercise.name))).size
}

function sessionRoute(session: Session, index: number): string {
  return index >= 0 ? `/session/${session.date}/${index}` : `/session/${session.date}`
}

export default function CalendarPage() {
  const { program, isLoading } = useProgramStore()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const agendaTargetRef = useRef<HTMLButtonElement | null>(null)
  const hasScrolledAgendaRef = useRef(false)
  const view = parseSessionView(searchParams.get('view'))
  const calendarDate = parseDateParam(searchParams.get('date'))
  const sessionsBackTo = useMemo(() => {
    const query = searchParams.toString()
    return query ? `/sessions?${query}` : '/sessions'
  }, [searchParams])

  const updateSessionParams = (updates: { view?: ViewType; date?: string | null }) => {
    setSearchParams((current) => {
      const next = new URLSearchParams(current)

      if (updates.view !== undefined) {
        updates.view === 'Agenda' ? next.delete('view') : next.set('view', updates.view)
      }

      if (updates.date !== undefined) {
        updates.date ? next.set('date', updates.date) : next.delete('date')
      }

      return next
    })
  }

  const sessionsByDate = useMemo(() => {
    const map = new Map<string, Session>()
    if (!program) return map
    for (const session of program.sessions) {
      if ((session.block ?? 'current') === 'current') {
        map.set(session.date, session)
      }
    }
    return map
  }, [program])

  const currentSessions = useMemo(() => {
    if (!program) return []
    return program.sessions
      .filter((session) => (session.block ?? 'current') === 'current')
      .sort((a, b) => a.date.localeCompare(b.date))
  }, [program])

  const closestAgendaSession = useMemo(
    () => findClosestSessionToToday(currentSessions),
    [currentSessions],
  )

  const weeklyGroups = useMemo(() => {
    if (!currentSessions.length) return []
    const groups = new Map<string, Session[]>()

    for (const session of currentSessions) {
      const weekStart = format(startOfWeek(parseLocalDate(session.date), { weekStartsOn: 0 }), 'yyyy-MM-dd')
      const existing = groups.get(weekStart)
      if (existing) {
        existing.push(session)
      } else {
        groups.set(weekStart, [session])
      }
    }

    return Array.from(groups.entries()).map(([weekStart, sessions]) => ({
      weekStart,
      weekLabel: format(parseLocalDate(weekStart), 'MMM d'),
      sessions,
    }))
  }, [currentSessions])

  const dateColorMap = useMemo(() => {
    const map = new Map<string, string>()
    if (!program) return map
    for (const session of currentSessions) {
      const phase = program.phases.find((p) => p.name === session.phase?.name)
      const color = phase ? phaseColor(phase, program.phases) : '#94a3b8'
      map.set(session.date, color)
    }
    return map
  }, [currentSessions, program])

  useEffect(() => {
    if (view !== 'Agenda' || hasScrolledAgendaRef.current || !closestAgendaSession) return

    const timeoutId = window.setTimeout(() => {
      const target = agendaTargetRef.current
      if (!target) return

      target.scrollIntoView({ block: 'center', inline: 'nearest' })
      hasScrolledAgendaRef.current = true
    }, 0)

    return () => window.clearTimeout(timeoutId)
  }, [closestAgendaSession, view])

  if (isLoading || !program) {
    return (
      <Stack align="center" justify="center" style={{ minHeight: '50vh' }}>
        <Text c="dimmed" size="lg">Loading...</Text>
      </Stack>
    )
  }

  const openSession = (session: Session) => {
    navigate(sessionRoute(session, program.sessions.indexOf(session)), {
      state: { backTo: sessionsBackTo },
    })
  }

  const renderDay = (date: string) => {
    const color = dateColorMap.get(date)
    const session = sessionsByDate.get(date)

    return (
      <Stack gap={0} align="center" justify="center" style={{ minHeight: 40 }}>
        <Text size="sm">{dayjs(date).date()}</Text>
        {color && (
          <Box
            style={{
              width: 8,
              height: 8,
              borderRadius: '50%',
              backgroundColor: session?.completed ? color : `${color}80`,
              opacity: session?.completed ? 1 : 0.7,
            }}
          />
        )}
      </Stack>
    )
  }

  const getDayProps = (date: string) => {
    const session = sessionsByDate.get(date)
    return {
      onClick: () => session && openSession(session),
      disabled: !session,
    }
  }

  const renderSessionRow = (session: Session, compact = false) => {
    const phase = program.phases.find((p) => p.name === session.phase?.name)
    const color = phase ? phaseColor(phase, program.phases) : '#94a3b8'
    const previewExercises = session.exercises.length > 0 ? session.exercises : session.planned_exercises ?? []
    const uniqueExerciseCount = countUniqueExerciseNames(session)
    const previewNames = Array.from(new Set(previewExercises.map((exercise) => exercise.name))).slice(0, compact ? 2 : 3).join(', ') || 'Rest Day'

    return (
      <UnstyledButton
        key={`${session.date}-${session.id ?? session.week_number}`}
        ref={session === closestAgendaSession ? agendaTargetRef : undefined}
        onClick={() => openSession(session)}
      >
        <Paper
          withBorder
          p={compact ? 'xs' : 'sm'}
          style={{
            borderLeft: `4px solid ${color}`,
            opacity: session.completed ? 1 : 0.8,
          }}
        >
          <Group justify="space-between" wrap="nowrap" align="flex-start">
            <Group gap="xs" wrap="nowrap" align="flex-start" style={{ minWidth: 0, flex: 1 }}>
              <Text size="sm" fw={500} style={{ minWidth: compact ? 56 : 64 }}>
                {format(parseLocalDate(session.date), compact ? 'MMM d' : 'EEE, MMM d')}
              </Text>
              <Badge size="xs" variant="filled" color={color}>
                {session.phase?.name || 'Unknown'}
              </Badge>
              {!compact && (
                <Text size="sm" c="dimmed" lineClamp={1} style={{ minWidth: 0 }}>
                  {previewNames}
                </Text>
              )}
            </Group>

            <Group gap="sm" wrap="nowrap" align="center">
              <Stack gap={0} align="flex-end">
                <Text size="sm">
                  {uniqueExerciseCount} exercise{uniqueExerciseCount !== 1 ? 's' : ''}
                </Text>
                <Text size="xs" c="dimmed">
                  {session.session_rpe !== null ? `RPE ${session.session_rpe}` : 'RPE --'}
                </Text>
              </Stack>
              {session.completed && (
                <ThemeIcon size="sm" variant="subtle" color="green" radius="xl">
                  <Check size={14} />
                </ThemeIcon>
              )}
            </Group>
          </Group>

          {compact && (
            <Text size="xs" c="dimmed" mt={6} lineClamp={1}>
              {previewNames}
            </Text>
          )}
        </Paper>
      </UnstyledButton>
    )
  }

  return (
    <Stack gap="md">
      <Group justify="space-between" wrap="nowrap">
        <Text size="xl" fw={700}>Sessions</Text>
        <SegmentedControl
          size="xs"
          data={['Month', 'Agenda', 'Compact']}
          value={view}
          onChange={(value) => updateSessionParams({ view: value as ViewType })}
        />
      </Group>

      {view === 'Compact' ? (
        <SessionsCompactView backTo={sessionsBackTo} />
      ) : (
        <Paper withBorder p={{ base: 'xs', sm: 'md' }}>
          {view === 'Month' ? (
            <Center>
              <Calendar
                renderDay={renderDay}
                getDayProps={getDayProps}
                date={calendarDate ?? undefined}
                onDateChange={(date) => updateSessionParams({ date })}
                size="md"
              />
            </Center>
          ) : (
            <Stack gap="md">
              {weeklyGroups.map(({ weekStart, weekLabel, sessions }) => (
                <Stack key={weekStart} gap={4}>
                  <Text size="sm" fw={600} c="dimmed">
                    Week of {weekLabel}
                  </Text>
                  {sessions.map((session) => renderSessionRow(session))}
                </Stack>
              ))}
            </Stack>
          )}
        </Paper>
      )}

      <MuscleVolumeChart />
    </Stack>
  )
}
