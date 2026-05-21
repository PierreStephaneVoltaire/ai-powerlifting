import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import {
  Group,
  Badge,
  Paper,
  Stack,
  Text,
  Box,
  ThemeIcon,
  UnstyledButton,
  Center,
  Select,
  ActionIcon,
} from '@mantine/core'
import { Calendar } from '@mantine/dates'
import { useProgramStore } from '@/store/programStore'
import { useSettingsStore } from '@/store/settingsStore'
import { phaseColor } from '@/utils/phases'
import { format } from 'date-fns'
import { findClosestSessionToToday, parseLocalDate } from '@/utils/dates'
import { trainingWeekStartForDate, weekStartForBlock } from '@/utils/weekStart'
import { normalizeExerciseName } from '@/utils/volume'
import { Check, ArrowUp } from 'lucide-react'
import dayjs from 'dayjs'
import type { Session } from '@powerlifting/types'
import MuscleVolumeChart from '@/components/charts/MuscleVolumeChart'
import { SessionsCompactView } from '@/components/sessions/SessionsCompactView'
import SetupOnboarding from '@/components/setup/SetupOnboarding'
import { useAuth } from '@/auth/AuthProvider'
import Num from '@/components/shared/Num'

type ViewType = 'Month' | 'Agenda' | 'Compact'
const SESSION_DATE_PARAM = /^\d{4}-\d{2}-\d{2}$/

function parseSessionView(raw: string | null): ViewType | null {
  return raw === 'Month' || raw === 'Compact' || raw === 'Agenda' ? raw : null
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
  const { readOnly } = useAuth()
  const { program, isLoading, needsSetup } = useProgramStore()
  const { defaultSessionsView } = useSettingsStore()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const agendaTargetRef = useRef<HTMLButtonElement | null>(null)
  const hasScrolledAgendaRef = useRef(false)
  const [showScrollTop, setShowScrollTop] = useState(false)
  const view = parseSessionView(searchParams.get('view')) || defaultSessionsView
  const calendarDate = parseDateParam(searchParams.get('date'))
  const sessionsBackTo = useMemo(() => {
    const query = searchParams.toString()
    return query ? `/sessions?${query}` : '/sessions'
  }, [searchParams])

  const availableBlocks = useMemo(() => {
    if (!program) return ['current']
    const blocks = new Set<string>()
    for (const s of program.sessions) blocks.add(s.block ?? 'current')
    return Array.from(blocks).sort()
  }, [program])

  const requestedBlock = searchParams.get('block') || 'current'
  const block = availableBlocks.includes(requestedBlock) ? requestedBlock : 'current'

  const updateBlockParam = (nextBlock: string) => {
    setSearchParams((current) => {
      const next = new URLSearchParams(current)
      nextBlock === 'current' ? next.delete('block') : next.set('block', nextBlock)
      return next
    })
  }

  useEffect(() => {
    const handleScroll = () => {
      setShowScrollTop(window.scrollY > 400)
    }
    window.addEventListener('scroll', handleScroll, { passive: true })
    return () => window.removeEventListener('scroll', handleScroll)
  }, [])

  const updateSessionParams = (updates: { date?: string | null }) => {
    setSearchParams((current) => {
      const next = new URLSearchParams(current)

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
      if ((session.block ?? 'current') === block) {
        map.set(session.date, session)
      }
    }
    return map
  }, [program, block])

  const currentSessions = useMemo(() => {
    if (!program) return []
    return program.sessions
      .filter((session) => (session.block ?? 'current') === block)
      .sort((a, b) => a.date.localeCompare(b.date))
  }, [program, block])

  const closestAgendaSession = useMemo(
    () => findClosestSessionToToday(currentSessions),
    [currentSessions],
  )

  const weeklyGroups = useMemo(() => {
    if (!program || !currentSessions.length) return []
    const groups = new Map<string, Session[]>()
    const weekStartDay = weekStartForBlock(program, block)

    for (const session of currentSessions) {
      const weekStart = trainingWeekStartForDate(session.date, program.meta.program_start, weekStartDay)
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
  }, [currentSessions, program, block])

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

  if (needsSetup) {
    return <SetupOnboarding compact />
  }

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
        style={{ width: '100%' }}
      >
        <Paper
          withBorder
          p={0}
          className="if-session-row"
          style={{
            borderLeft: `3px solid ${color}`,
            opacity: session.completed ? 1 : 0.8,
          }}
        >
          <Group justify="space-between" wrap="nowrap" align="flex-start" p={compact ? 12 : 16}>
            <Group gap="xs" wrap="nowrap" align="flex-start" style={{ minWidth: 0, flex: 1 }}>
              <Num size="sm" style={{ minWidth: compact ? 56 : 80 }}>
                {format(parseLocalDate(session.date), compact ? 'MMM d' : 'EEE, MMM d')}
              </Num>
              <Badge
                size="xs"
                variant="filled"
                h={20}
                radius={4}
                style={{ background: color, color: 'white', flexShrink: 0 }}
              >
                {session.phase?.name || 'Unknown'}
              </Badge>
              {!compact && (
                <Text size="sm" c="var(--text-secondary)" lineClamp={1} style={{ minWidth: 0 }}>
                  {previewNames}
                </Text>
              )}
            </Group>

            <Group gap="sm" wrap="nowrap" align="center">
              <Stack gap={0} align="flex-end">
                <Text size="sm" c="var(--text-primary)">
                  {uniqueExerciseCount} exercise{uniqueExerciseCount !== 1 ? 's' : ''}
                </Text>
                <Num size="xs" c="var(--text-secondary)">
                  {session.session_rpe !== null ? `RPE ${session.session_rpe}` : 'RPE --'}
                </Num>
              </Stack>
              {session.completed && (
                <ThemeIcon size="sm" variant="subtle" color="green" radius="xl">
                  <Check size={14} />
                </ThemeIcon>
              )}
            </Group>
          </Group>

          {compact && (
            <Text size="xs" c="var(--text-secondary)" px={12} pb={12} lineClamp={1}>
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
        <Text className="if-section-title" fz={24}>Sessions</Text>
        {view !== 'Compact' && availableBlocks.length > 1 && (
          <Select
            value={block}
            onChange={(v) => updateBlockParam(v || 'current')}
            data={availableBlocks.map((b) => ({
              value: b,
              label: b === 'current' ? 'Current Block' : b,
            }))}
            size="sm"
            style={{ width: 160 }}
            data-testid="session-block-select"
          />
        )}
      </Group>

      {view === 'Compact' ? (
        <SessionsCompactView backTo={sessionsBackTo} readOnly={readOnly} />
      ) : (
        <Paper p={{ base: 0, sm: 0 }} style={{ background: 'transparent', border: 'none' }}>
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
                  <Text className="if-week-header">
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

      {showScrollTop && (
        <ActionIcon
          size="lg"
          radius="xl"
          variant="filled"
          color="dark"
          onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
          style={{
            position: 'fixed',
            bottom: 'calc(76px + env(safe-area-inset-bottom, 0px) + var(--app-browser-bottom-overlap, 0px) + 56px)',
            right: 16,
            zIndex: 120,
            opacity: 0.7,
          }}
          aria-label="Scroll to top"
        >
          <ArrowUp size={20} />
        </ActionIcon>
      )}
    </Stack>
  )
}
