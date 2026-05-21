import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useProgramStore } from '@/store/programStore'
import { useSettingsStore } from '@/store/settingsStore'
import { useUiStore } from '@/store/uiStore'
import { findClosestSessionToToday, groupSessionsByWeek, formatDateShort, getDayOfWeek } from '@/utils/dates'
import { displayWeight } from '@/utils/units'
import { phaseColor } from '@/utils/phases'
import { normalizeExerciseName } from '@/utils/volume'
import { Check, Dumbbell, Plus } from 'lucide-react'
import {
  Paper, Title, Text, Group, Stack, Button, ActionIcon,
  Select, Modal, Loader, Center, Box,
} from '@mantine/core'
import { DatePickerInput } from '@mantine/dates'
import type { Session } from '@powerlifting/types'
import Num from '@/components/shared/Num'

function countUniqueExerciseNames(session: Session): number {
  const entries = session.exercises.length > 0 ? session.exercises : session.planned_exercises ?? []
  return new Set(entries.map((exercise) => normalizeExerciseName(exercise.name))).size
}

interface SessionsCompactViewProps {
  backTo?: string
  readOnly?: boolean
}

export function SessionsCompactView({ backTo = '/sessions?view=Compact', readOnly = false }: SessionsCompactViewProps) {
  const { program, isLoading, createSession } = useProgramStore()
  const { unit } = useSettingsStore()
  const { pushToast } = useUiStore()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const [expandedWeeks, setExpandedWeeks] = useState<Set<number>>(new Set())
  const [showAddModal, setShowAddModal] = useState(false)
  const [newDate, setNewDate] = useState<string>('')
  const compactTargetRef = useRef<HTMLButtonElement | null>(null)
  const hasScrolledCompactRef = useRef(false)

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
      next.set('view', 'Compact')
      nextBlock === 'current' ? next.delete('block') : next.set('block', nextBlock)
      return next
    })
  }

  const blockSessions = useMemo(() => {
    if (!program) return []
    return program.sessions
      .filter((session) => (session.block ?? 'current') === block)
      .sort((a, b) => a.date.localeCompare(b.date))
  }, [block, program])

  const closestSession = useMemo(
    () => findClosestSessionToToday(blockSessions),
    [blockSessions],
  )
  const closestWeek = closestSession?.week_number ?? null

  const sessionsByWeek = useMemo(
    () => groupSessionsByWeek(program?.sessions ?? [], block),
    [block, program],
  )

  useEffect(() => {
    if (hasScrolledCompactRef.current || closestWeek == null) return

    setExpandedWeeks((prev) => {
      if (prev.has(closestWeek)) return prev
      const next = new Set(prev)
      next.add(closestWeek)
      return next
    })
  }, [closestWeek])

  useEffect(() => {
    if (
      hasScrolledCompactRef.current ||
      closestWeek == null ||
      !expandedWeeks.has(closestWeek) ||
      !closestSession
    ) {
      return
    }

    const timeoutId = window.setTimeout(() => {
      const target = compactTargetRef.current
      if (!target) return

      target.scrollIntoView({ block: 'center', inline: 'nearest' })
      hasScrolledCompactRef.current = true
    }, 0)

    return () => window.clearTimeout(timeoutId)
  }, [closestSession, closestWeek, expandedWeeks])

  const handleAddSession = async () => {
    if (!newDate || readOnly) {
      if (!newDate) pushToast({ message: 'Please select a date', type: 'error' })
      return
    }

    try {
      const dayOfWeek = getDayOfWeek(newDate)
      const createdSession = await createSession({
        date: newDate,
        day: dayOfWeek,
        exercises: [],
      })
      const currentSessions = useProgramStore.getState().program?.sessions ?? []
      const createdIndex = createdSession.id
        ? currentSessions.findIndex((session) => session.id === createdSession.id)
        : currentSessions.reduce(
            (found, session, idx) => (session.date === createdSession.date ? idx : found),
            -1
          )

      pushToast({ message: 'Session created', type: 'success' })
      setShowAddModal(false)
      setNewDate('')
      navigate(createdIndex >= 0 ? `/session/${createdSession.date}/${createdIndex}` : `/session/${createdSession.date}`, {
        state: { backTo },
      })
    } catch {
      pushToast({ message: 'Failed to create session', type: 'error' })
    }
  }

  const toggleWeek = (week: number) => {
    setExpandedWeeks((prev) => {
      const next = new Set(prev)
      if (next.has(week)) next.delete(week)
      else next.add(week)
      return next
    })
  }

  if (isLoading || !program) {
    return (
      <Center mih="50vh">
        <Loader />
      </Center>
    )
  }

  return (
    <Stack gap="md" style={{ position: 'relative' }}>
      <Box
        style={{
          position: 'sticky',
          top: 0,
          zIndex: 10,
          background: 'var(--bg-base)',
          borderBottom: '1px solid var(--border-subtle)',
          paddingBottom: 8,
          marginBottom: 0,
        }}
      >
        <Group justify="space-between" wrap="nowrap">
          <Title order={2} className="if-section-title">Sessions by Week</Title>
          <Group gap="xs" wrap="nowrap">
            {availableBlocks.length > 1 && (
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
            <Button
              size="sm"
              leftSection={<Plus size={16} />}
              onClick={() => setShowAddModal(true)}
              visibleFrom="sm"
              disabled={readOnly}
              data-testid="session-list-add-session"
            >
              Add Session
            </Button>
          </Group>
        </Group>
      </Box>

      <ActionIcon
        size="xl"
        radius="xl"
        variant="filled"
        hiddenFrom="sm"
        onClick={() => setShowAddModal(true)}
        aria-label="Add Session"
        disabled={readOnly}
        data-testid="session-list-add-session-mobile"
        style={{
          position: 'fixed',
          bottom: 'calc(76px + env(safe-area-inset-bottom, 0px) + var(--app-browser-bottom-overlap, 0px))',
          right: 16,
          zIndex: 120,
          width: 52,
          height: 52,
        }}
      >
        <Plus size={24} />
      </ActionIcon>

      <Modal
        opened={showAddModal}
        onClose={() => {
          setShowAddModal(false)
          setNewDate('')
        }}
        title="Add New Session"
        centered
      >
        <Stack gap="md">
          <Box>
            <Text size="sm" c="dimmed" mb={4}>Date</Text>
            <DatePickerInput
              value={newDate || null}
              valueFormat="YYYY-MM-DD"
              onChange={(d) => setNewDate(d || '')}
              disabled={readOnly}
              data-testid="session-create-date"
            />
          </Box>
          <Group justify="flex-end" gap="xs">
            <Button
              variant="default"
              onClick={() => {
                setShowAddModal(false)
                setNewDate('')
              }}
            >
              Cancel
            </Button>
            <Button onClick={handleAddSession} disabled={readOnly} data-testid="session-create-submit">
              Create Session
            </Button>
          </Group>
        </Stack>
      </Modal>

      {sessionsByWeek.size === 0 ? (
        <Paper withBorder p="xl" data-testid="session-list-empty">
          <Stack align="center" gap="xs">
            <Title order={3}>No sessions yet</Title>
            <Text c="dimmed" ta="center">
              Add a session to start planning and logging training.
            </Text>
            <Button
              leftSection={<Plus size={16} />}
              onClick={() => setShowAddModal(true)}
              disabled={readOnly}
              data-testid="session-list-empty-add-session"
            >
              Add Session
            </Button>
          </Stack>
        </Paper>
      ) : (
        <Stack gap="xs">
          {Array.from(sessionsByWeek.entries()).map(([week, sessions]) => {
          const firstSession = sessions[0]
          const phase = firstSession?.phase
          const isExpanded = expandedWeeks.has(week)
          const completedCount = sessions.filter((s) => s.completed).length
          const phaseColorValue = phase ? phaseColor(phase, program.phases) : undefined

          return (
            <Paper key={week} withBorder className="if-card" data-testid={`session-week-${week}`}>
              <Box
                component="button"
                onClick={() => toggleWeek(week)}
                style={{
                  width: '100%',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 12,
                  padding: 16,
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  textAlign: 'left',
                }}
              >
                <Text
                  fw={500}
                  style={{
                    transform: isExpanded ? 'rotate(0deg)' : 'rotate(-90deg)',
                    transition: 'transform 150ms ease',
                    lineHeight: 1,
                  }}
                >
                  &#9662;
                </Text>

                {phase && (
                  <Box
                    style={{
                      width: 12,
                      height: 12,
                      borderRadius: '50%',
                      backgroundColor: phaseColorValue,
                      flexShrink: 0,
                    }}
                  />
                )}

                <Num fw={500}>Week {week}</Num>
                <Text size="sm" c="var(--text-secondary)">
                  {phase?.name}
                </Text>

                <Box style={{ marginLeft: 'auto' }}>
                  <Num size="sm" c="var(--text-secondary)">
                    {completedCount}/{sessions.length} completed
                  </Num>
                </Box>
              </Box>

              {isExpanded && (
                <Box style={{ borderTop: '1px solid var(--border-subtle)' }}>
                  {sessions.map((session) => {
                    const previewExercises = session.exercises.length > 0 ? session.exercises : session.planned_exercises || []
                    const isPlanned = session.exercises.length === 0 && (session.planned_exercises?.length ?? 0) > 0
                    const uniqueExerciseCount = countUniqueExerciseNames(session)

                    return (
                      <Box
                        key={`${session.date}-${session.id ?? session.week_number}`}
                        ref={session === closestSession ? compactTargetRef : undefined}
                        component="button"
                        onClick={() => navigate(program.sessions.indexOf(session) >= 0 ? `/session/${session.date}/${program.sessions.indexOf(session)}` : `/session/${session.date}`, {
                          state: { backTo },
                        })}
                        data-testid={`session-list-row-${session.date}`}
                        style={{
                          width: '100%',
                          display: 'flex',
                          alignItems: 'center',
                          gap: 12,
                          padding: 12,
                          background: 'transparent',
                          border: 'none',
                          borderBottom: '1px solid var(--border-subtle)',
                          borderLeft: `3px solid ${phaseColorValue || 'var(--text-muted)'}`,
                          cursor: 'pointer',
                          textAlign: 'left',
                          minHeight: 52,
                        }}
                      >
                        <Box
                          style={{
                            width: 32,
                            height: 32,
                            borderRadius: '50%',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            backgroundColor: 'var(--bg-elevated)',
                            flexShrink: 0,
                          }}
                        >
                          {session.completed ? (
                            <Check size={16} style={{ color: 'var(--mantine-color-primary-filled)' }} />
                          ) : (
                            <Dumbbell size={16} style={{ opacity: 0.6 }} />
                          )}
                        </Box>

                        <Box style={{ flex: 1 }}>
                          <Text fw={500} c="var(--text-primary)">{session.day}</Text>
                          <Num size="sm" c="var(--text-secondary)">
                            {formatDateShort(session.date)}
                          </Num>
                        </Box>

                        <Box style={{ flex: 1, textAlign: 'right' }}>
                          <Text size="sm" c="var(--text-primary)">
                            {session.exercises.length > 0
                              ? `${uniqueExerciseCount} exercise${uniqueExerciseCount !== 1 ? 's' : ''}`
                              : isPlanned
                                ? `${uniqueExerciseCount} planned`
                                : 'No exercises'}
                          </Text>
                          {session.session_rpe !== null && (
                            <Num size="xs" c="var(--text-secondary)">
                              RPE {session.session_rpe}
                            </Num>
                          )}
                        </Box>

                        <Box style={{ flex: 1, textAlign: 'right' }} visibleFrom="lg">
                          {previewExercises.slice(0, 3).map((ex, idx) => (
                            <Text key={idx} size="sm" c="dimmed" component="span">
                              {ex.name}
                              {ex.kg !== null && ` @ ${displayWeight(ex.kg, unit)}`}
                              {idx < Math.min(previewExercises.length, 3) - 1 && ', '}
                            </Text>
                          ))}
                          {previewExercises.length > 3 && (
                            <Text size="sm" c="dimmed" component="span">
                              {' '}+{previewExercises.length - 3} more
                            </Text>
                          )}
                        </Box>
                      </Box>
                    )
                  })}
                </Box>
              )}
            </Paper>
          )
          })}
        </Stack>
      )}
    </Stack>
  )
}
