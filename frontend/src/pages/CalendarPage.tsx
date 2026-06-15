import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import {
  Group,
  Stack,
  Text,
  Box,
  UnstyledButton,
  Select,
  ActionIcon,
} from '@mantine/core'
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
import { SessionsCompactView } from '@/components/sessions/SessionsCompactView'
import SetupOnboarding from '@/components/setup/SetupOnboarding'
import { useAuth } from '@/auth/AuthProvider'

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

  const updateViewParam = (nextView: ViewType) => {
    setSearchParams((current) => {
      const next = new URLSearchParams(current)
      nextView === defaultSessionsView ? next.delete('view') : next.set('view', nextView)
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
    const dateLabel = format(parseLocalDate(session.date), compact ? 'EEE' : 'EEE')
    const dateSubLabel = format(parseLocalDate(session.date), 'MMM d')

    return (
      <UnstyledButton
        key={`${session.date}-${session.id ?? session.week_number}`}
        ref={session === closestAgendaSession ? agendaTargetRef : undefined}
        onClick={() => openSession(session)}
        style={{ width: '100%' }}
      >
        <div
          className="if-session-row"
          style={{
            borderLeft: `3px solid ${color}`,
            opacity: session.completed ? 1 : 0.8,
            padding: compact ? '7px 10px' : '10px 14px',
          }}
        >
          <div className="if-session-row-main" style={{ gap: compact ? 8 : 12 }}>
            <div className="if-session-date" style={{ width: compact ? 72 : 88 }}>
              <div className="if-mock-num" style={{ color: compact ? 'var(--color-text-secondary)' : 'var(--color-text-primary)', fontSize: compact ? 12 : 13, fontWeight: compact ? 400 : 500 }}>
                {dateLabel}
              </div>
              <div style={{ color: 'var(--color-text-secondary)', fontSize: compact ? 10 : 11 }}>{dateSubLabel}</div>
            </div>
            <span
              className="if-phase-pill"
              style={{
                background: `color-mix(in srgb, ${color} 22%, transparent)`,
                color,
                flexShrink: 0,
              }}
            >
              {session.phase?.name || 'Unknown'}
            </span>
            <div className="if-session-preview" style={{ fontSize: compact ? 12 : 13 }}>
              {previewNames}
            </div>
            <div className="if-session-meta" style={{ fontSize: compact ? 11 : 12, minWidth: compact ? 48 : 80 }}>
              {compact ? null : <>{uniqueExerciseCount} exercise{uniqueExerciseCount !== 1 ? 's' : ''}<br /></>}
              <span style={{ fontSize: 11 }}>{session.session_rpe !== null ? `RPE ${session.session_rpe}` : 'RPE --'}</span>
            </div>
            <span className="if-session-done" data-completed={session.completed ? 'true' : 'false'}>
              {session.completed && <Check size={12} />}
            </span>
          </div>
        </div>
      </UnstyledButton>
    )
  }

  const renderMonthGrid = () => (
    <Stack gap="xs">
      <div className="if-calendar-grid" style={{ marginBottom: 8 }}>
        {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map((day) => (
          <div key={day} style={{ color: 'var(--color-text-secondary)', fontSize: 11, letterSpacing: '0.07em', padding: '4px 0', textAlign: 'center', textTransform: 'uppercase' }}>
            {day}
          </div>
        ))}
      </div>
      {weeklyGroups.map(({ weekStart, weekLabel }) => {
        const start = dayjs(weekStart)
        const days = Array.from({ length: 7 }, (_, index) => start.add(index, 'day').format('YYYY-MM-DD'))
        return (
          <div key={weekStart}>
            <div style={{ color: 'var(--color-text-secondary)', fontSize: 10, letterSpacing: '0.07em', margin: '8px 0 4px', textTransform: 'uppercase' }}>
              Week of {weekLabel}
            </div>
            <div className="if-calendar-grid">
              {days.map((date) => {
                const session = sessionsByDate.get(date)
                const phase = session ? program.phases.find((p) => p.name === session.phase?.name) : undefined
                const color = phase ? phaseColor(phase, program.phases) : '#94a3b8'
                const previewExercises = session ? (session.exercises.length > 0 ? session.exercises : session.planned_exercises ?? []) : []
                return (
                  <button
                    key={date}
                    type="button"
                    className="if-calendar-day"
                    onClick={() => session && openSession(session)}
                    disabled={!session}
                    style={{
                      background: 'transparent',
                      borderLeft: session ? `3px solid ${color}` : undefined,
                      cursor: session ? 'pointer' : 'default',
                      opacity: session ? 1 : 0.35,
                      textAlign: 'left',
                    }}
                  >
                    <div className="if-mock-num" style={{ fontSize: 11, fontWeight: 500, marginBottom: 4 }}>{dayjs(date).date()}</div>
                    {session && (
                      <>
                        <span className="if-phase-pill" style={{ background: `color-mix(in srgb, ${color} 22%, transparent)`, color, fontSize: 9 }}>
                          {session.phase?.name || 'Unknown'}
                        </span>
                        <div style={{ color: 'var(--color-text-secondary)', fontSize: 10, marginTop: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {previewExercises[0]?.name || 'Rest Day'}{previewExercises.length > 1 ? ` +${previewExercises.length - 1}` : ''}
                        </div>
                        {session.completed && <Check size={11} style={{ color: 'var(--color-text-success)', display: 'block', marginTop: 4 }} />}
                      </>
                    )}
                  </button>
                )
              })}
            </div>
          </div>
        )
      })}
    </Stack>
  )

  return (
    <Stack gap="md" className="if-mock-page">
      <div className="if-mock-header">
        <h1 className="if-mock-title">Sessions</h1>
        <div className="if-mock-toolbar">
          <div className="if-tab-group">
            {(['Agenda', 'Compact', 'Month'] as ViewType[]).map((nextView) => (
              <button
                key={nextView}
                type="button"
                className="if-tab-button"
                data-active={view === nextView}
                onClick={() => updateViewParam(nextView)}
              >
                {nextView}
              </button>
            ))}
          </div>
          <Select
            value={block}
            onChange={(v) => updateBlockParam(v || 'current')}
            data={availableBlocks.map((b) => ({
              value: b,
              label: b === 'current' ? 'Current Block' : b,
            }))}
            size="xs"
            style={{ width: 160 }}
            data-testid="session-block-select"
          />
        </div>
      </div>

      {view === 'Compact' ? (
        <SessionsCompactView backTo={sessionsBackTo} readOnly={readOnly} />
      ) : view === 'Month' ? renderMonthGrid() : (
        <Stack gap="md">
          {weeklyGroups.map(({ weekStart, weekLabel, sessions }) => (
            <Stack key={weekStart} gap={4}>
              <Text className="if-week-header">Week of {weekLabel}</Text>
              {sessions.map((session) => renderSessionRow(session, false))}
            </Stack>
          ))}
        </Stack>
      )}

      {showScrollTop && (
        <ActionIcon
          size="lg"
          radius="xl"
          variant="filled"
          color="dark"
          onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
          style={{
            position: 'fixed',
            bottom: 'calc(84px + env(safe-area-inset-bottom, 0px) + var(--app-browser-bottom-overlap, 0px) + 56px)',
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
