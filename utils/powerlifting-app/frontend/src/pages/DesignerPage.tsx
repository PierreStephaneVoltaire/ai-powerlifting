import { useState, useEffect, useMemo } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Plus, Trash2, X, Save, BarChart3, Copy, ArrowLeft, ArrowRight, ArrowUp, ArrowDown, GripVertical } from 'lucide-react'
import {
  Stack, Group, Text, Button, Paper, Badge, Modal, SimpleGrid,
  Select, ActionIcon, Autocomplete, Progress, Box, Divider, TextInput
} from '@mantine/core'
import { DatePickerInput } from '@mantine/dates'
import { addDays, differenceInCalendarDays, format } from 'date-fns'
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  DragEndEvent,
} from '@dnd-kit/core'
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
  useSortable,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { useProgramStore } from '@/store/programStore'
import { useUiStore } from '@/store/uiStore'
import { useSettingsStore } from '@/store/settingsStore'
import { sessionMuscleSets } from '@/utils/sessionWorkload'
import { getDayOfWeek, parseLocalDate } from '@/utils/dates'
import { programWeekStartDate, trainingWeekForDate, weekStartForBlock } from '@/utils/weekStart'
import { toDisplayUnit, fromDisplayUnit, displayWeight } from '@/utils/units'
import * as api from '@/api/client'
import type { Session, PlannedExercise, GlossaryExercise } from '@powerlifting/types'

const MUSCLE_LABELS: Record<string, string> = {
  quads: 'Quads',
  hamstrings: 'Hamstrings',
  glutes: 'Glutes',
  calves: 'Calves',
  tibialis_anterior: 'Tibialis Anterior',
  hip_flexors: 'Hip Flexors',
  adductors: 'Adductors',
  chest: 'Chest',
  triceps: 'Triceps',
  front_delts: 'Front Delts',
  side_delts: 'Side Delts',
  rear_delts: 'Rear Delts',
  lats: 'Lats',
  traps: 'Traps',
  rhomboids: 'Rhomboids',
  teres_major: 'Teres Major',
  biceps: 'Biceps',
  forearms: 'Forearms',
  erectors: 'Erectors',
  lower_back: 'Lower Back',
  core: 'Core',
  obliques: 'Obliques',
  serratus: 'Serratus',
}

const STATUS_COLORS: Record<string, string> = {
  planned: 'blue',
  completed: 'green',
  logged: 'yellow',
  skipped: 'gray',
}

function toIsoDate(date: Date): string {
  return format(date, 'yyyy-MM-dd')
}

function addDaysIso(date: string, days: number): string {
  return toIsoDate(addDays(parseLocalDate(date), days))
}

// Helper to add IDs to planned exercises for stable DND
interface PlannedExerciseWithId extends PlannedExercise {
  id: string
}

import { LoadTypeBadge } from '@/components/shared/LoadTypeBadge'

function SortableExercise({ ex, onRemove, onUpdate, onMoveUp, onMoveDown, canMoveUp, canMoveDown }: { 
  ex: PlannedExerciseWithId; 
  onRemove: (id: string) => void;
  onUpdate: (id: string, f: keyof PlannedExercise, v: any) => void;
  onMoveUp: (id: string) => void;
  onMoveDown: (id: string) => void;
  canMoveUp: boolean;
  canMoveDown: boolean;
}) {
  const { unit } = useSettingsStore()
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging
  } = useSortable({ id: ex.id })

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    zIndex: isDragging ? 1000 : undefined,
    opacity: isDragging ? 0.5 : 1,
  }

  const renderLoadInput = () => {
    switch (ex.load_source) {
      case 'rpe':
        return (
          <TextInput
            type="number"
            value={ex.rpe_target || ''}
            onChange={(e) => onUpdate(ex.id, 'rpe_target', Number(e.currentTarget.value) || null)}
            step={0.5}
            w={70}
            placeholder="RPE"
          />
        )
      case 'percentage':
        return (
          <Group gap={4} wrap="nowrap">
            <Text size="xs" c="dimmed">~</Text>
            <TextInput
              type="number"
              value={ex.kg !== null ? toDisplayUnit(ex.kg, unit) : ''}
              onChange={(e) => onUpdate(ex.id, 'kg', e.currentTarget.value !== '' ? fromDisplayUnit(Number(e.currentTarget.value), unit) : null)}
              w={70}
              placeholder={unit}
              step={0.5}
            />
          </Group>
        )
      case 'unresolvable':
        return <Text size="sm" c="dimmed">—</Text>
      case 'absolute':
      default:
        return (
          <TextInput
            type="number"
            value={ex.kg !== null ? toDisplayUnit(ex.kg, unit) : ''}
            onChange={(e) => onUpdate(ex.id, 'kg', e.currentTarget.value !== '' ? fromDisplayUnit(Number(e.currentTarget.value), unit) : null)}
            w={70}
            placeholder={unit}
            step={0.5}
          />
        )
    }
  }

  return (
    <Paper ref={setNodeRef} style={style} withBorder p="xs" radius="sm">
      <Group justify="space-between" gap="xs" mb={4}>
        <Group gap="xs" style={{ flex: 1 }}>
          <Box {...attributes} {...listeners} style={{ cursor: 'grab', padding: '4px 0' }}>
            <GripVertical size={16} color="var(--mantine-color-gray-6)" />
          </Box>
          <Text size="sm" fw={500} truncate>{ex.name}</Text>
          {ex.load_source && <LoadTypeBadge source={ex.load_source} />}
        </Group>
        <Group gap={2} wrap="nowrap">
          <ActionIcon
            variant="subtle"
            size="sm"
            onClick={() => onMoveUp(ex.id)}
            disabled={!canMoveUp}
            title="Move exercise up"
            aria-label="Move exercise up"
          >
            <ArrowUp size={12} />
          </ActionIcon>
          <ActionIcon
            variant="subtle"
            size="sm"
            onClick={() => onMoveDown(ex.id)}
            disabled={!canMoveDown}
            title="Move exercise down"
            aria-label="Move exercise down"
          >
            <ArrowDown size={12} />
          </ActionIcon>
          <ActionIcon
            variant="subtle"
            color="red"
            size="sm"
            onClick={() => onRemove(ex.id)}
            title="Remove exercise"
            aria-label="Remove exercise"
          >
            <Trash2 size={12} />
          </ActionIcon>
        </Group>
      </Group>
      <Group gap={6}>
        <TextInput
          type="number"
          value={ex.sets || ''}
          onChange={(e) => onUpdate(ex.id, 'sets', Number(e.currentTarget.value) || 0)}
          w={60}
          placeholder="Sets"
        />
        <Text size="xs" c="dimmed">x</Text>
        <TextInput
          type="number"
          value={ex.reps || ''}
          onChange={(e) => onUpdate(ex.id, 'reps', Number(e.currentTarget.value) || 0)}
          w={60}
          placeholder="Reps"
        />
        <Text size="xs" c="dimmed">@</Text>
        {renderLoadInput()}
      </Group>
    </Paper>
  )
}

export default function DesignerPage() {
  const { program, version, createSession } = useProgramStore()
  const { pushToast } = useUiStore()
  const { unit } = useSettingsStore()
  const [searchParams, setSearchParams] = useSearchParams()

  const block = 'current'
  const weekStartDay = useMemo(() => weekStartForBlock(program, block), [program])
  const todayStr = useMemo(() => format(new Date(), 'yyyy-MM-dd'), [])
  const defaultWeek = useMemo(() => {
    const weekParam = searchParams.get('week')
    if (weekParam) {
      const week = parseInt(weekParam, 10)
      if (!isNaN(week) && week > 0) return week
    }
    const calculated = trainingWeekForDate(todayStr, program?.meta?.program_start, weekStartDay)
    const totalWeeks = program?.phases?.length
      ? Math.max(...program.phases.map(p => p.end_week))
      : 12
    return Math.min(calculated, totalWeeks)
  }, [searchParams, todayStr, program?.meta?.program_start, weekStartDay, program?.phases])

  const [selectedWeek, setSelectedWeek] = useState(defaultWeek)
  const [editingSession, setEditingSession] = useState<Session | null>(null)
  const [editingSessionGlobalIndex, setEditingSessionGlobalIndex] = useState<number>(-1)
  const [editingSessionDate, setEditingSessionDate] = useState<string>('')
  const [isSessionEditorOpen, setIsSessionEditorOpen] = useState(false)
  const [glossary, setGlossary] = useState<GlossaryExercise[]>([])
  const [exerciseSearch, setExerciseSearch] = useState('')

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: {
        distance: 5,
      },
    }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  )

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event
    if (over && active.id !== over.id) {
      setPlannedExercises((items) => {
        const oldIndex = items.findIndex(i => i.id === active.id)
        const newIndex = items.findIndex(i => i.id === over.id)
        return arrayMove(items, oldIndex, newIndex)
      })
    }
  }

  // Session form state
  const [sessionDate, setSessionDate] = useState<string | null>(null)
  const [plannedExercises, setPlannedExercises] = useState<PlannedExerciseWithId[]>([])

  const phases = program?.phases || []

  useEffect(() => {
    api.fetchGlossary().then(setGlossary).catch(console.error)
  }, [])

  useEffect(() => {
    const current = searchParams.get('week')
    if (current !== String(selectedWeek)) {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev)
        next.set('week', String(selectedWeek))
        return next
      }, { replace: true })
    }
  }, [selectedWeek])

  const totalWeeks = useMemo(() => {
    if (!phases.length) return 12
    return Math.max(...phases.map(p => p.end_week))
  }, [phases])

  const weekOptions = useMemo(() => {
    return Array.from({ length: totalWeeks }, (_, i) => i + 1)
  }, [totalWeeks])

  const selectedPhase = useMemo(() => {
    return phases.find(
      (phase) =>
        (phase.block ?? 'current') === block &&
        selectedWeek >= phase.start_week &&
        selectedWeek <= phase.end_week
    )
  }, [phases, block, selectedWeek])

  const weekSessions = useMemo(() => {
    return (program?.sessions || [])
      .filter(s => s.week_number === selectedWeek)
      .filter(s => (s.block ?? 'current') === block)
  }, [program?.sessions, selectedWeek, block])

  const selectedWeekStartDay = useMemo(() => weekStartForBlock(program, block), [program, block])

  const selectedWeekStartDate = useMemo(() => {
    return programWeekStartDate(program?.meta?.program_start, selectedWeek, selectedWeekStartDay)
  }, [program?.meta?.program_start, selectedWeek, selectedWeekStartDay])

  const selectedWeekDates = useMemo(() => {
    return Array.from({ length: 7 }, (_, i) => addDaysIso(selectedWeekStartDate, i))
  }, [selectedWeekStartDate])

  const selectableWeekDates = useMemo(() => {
    const programStart = program?.meta?.program_start
    return programStart ? selectedWeekDates.filter((date) => date >= programStart) : selectedWeekDates
  }, [program?.meta?.program_start, selectedWeekDates])

  const selectedWeekEndDate = selectedWeekDates[6] ?? selectedWeekStartDate
  const inferredSessionDay = sessionDate ? getDayOfWeek(sessionDate) : null

  const plannedMuscleVolume = useMemo(() => {
    const plannedEntries = weekSessions.flatMap((s) => s.planned_exercises ?? [])
    const mgSets = sessionMuscleSets(plannedEntries, glossary)

    const sorted = Object.entries(mgSets)
      .sort(([, a], [, b]) => (b ?? 0) - (a ?? 0))
      .map(([muscle, sets]) => ({ label: MUSCLE_LABELS[muscle] || muscle, sets: Number(sets) || 0 }))

    return sorted.slice(0, 5)
  }, [weekSessions, glossary])

  const plannedSbdSets = useMemo(() => {
    const plannedEntries = weekSessions.flatMap((s) => s.planned_exercises ?? [])
    const counts = { squat: 0, bench: 0, deadlift: 0 }
    for (const ex of plannedEntries) {
      const name = (ex.name || '').toLowerCase().trim()
      if (name.includes('squat') && !name.includes('split') && !name.includes('hack')) counts.squat += (ex.sets ?? 0)
      else if (name === 'bench' || name === 'bench press') counts.bench += (ex.sets ?? 0)
      else if ((name === 'deadlift' || name.includes('deadlift')) && !name.includes('romanian') && !name.includes('rdl')) counts.deadlift += (ex.sets ?? 0)
    }
    return counts
  }, [weekSessions])

  // Copy session state
  const [copySourceWeek, setCopySourceWeek] = useState<number | null>(null)
  const [isCopyModalOpen, setIsCopyModalOpen] = useState(false)
  const [copyCollisionMode, setCopyCollisionMode] = useState<'overwrite' | 'add'>('add')

  async function handleCopySessions(sourceWeek: number) {
    if (sourceWeek === selectedWeek) return
    const sourceSessions = (program?.sessions || [])
      .filter(s => s.week_number === sourceWeek)
      .filter(s => (s.block ?? 'current') === block)
    
    if (sourceSessions.length === 0) {
      pushToast({ message: `No sessions found in Week ${sourceWeek}`, type: 'error' })
      return
    }

    setCopySourceWeek(sourceWeek)
    setIsCopyModalOpen(true)
  }

  async function executeCopy() {
    if (!copySourceWeek) return
    try {
      const sourceSessions = (program?.sessions || [])
        .filter(s => s.week_number === copySourceWeek)
        .filter(s => (s.block ?? 'current') === block)
      
      const offset = selectedWeek > copySourceWeek ? 7 : -7

      for (const src of sourceSessions) {
        const targetDate = addDaysIso(src.date, offset)
        
        try {
          // Optimistically attempt to create
          await api.createSession(version, {
            date: targetDate,
            day: getDayOfWeek(targetDate),
            week: `W${selectedWeek}`,
            week_number: selectedWeek,
            phase: selectedPhase ?? undefined,
            block: block,
            status: 'planned',
            completed: false,
            planned_exercises: src.planned_exercises || [],
            exercises: [],
            session_notes: '',
            session_rpe: null,
            body_weight_kg: null,
          })
        } catch (err: any) {
          // If 400 "already exists", fallback to updating
          if (err.response?.status === 400 && err.response?.data?.error?.includes('already exists')) {
            const existing = program?.sessions.find(s => s.date === targetDate)
            if (existing && !existing.completed) {
              const existingIndex = program?.sessions.findIndex(s => s.date === targetDate) ?? -1

              if (copyCollisionMode === 'overwrite') {
                await api.updateSession(version, targetDate, existingIndex, {
                  ...existing,
                  week: `W${selectedWeek}`,
                  week_number: selectedWeek,
                  phase: selectedPhase || existing.phase,
                  planned_exercises: src.planned_exercises || [],
                })
              } else {
                const combined = [...(existing.planned_exercises || []), ...(src.planned_exercises || [])]
                await api.updateSession(version, targetDate, existingIndex, {
                  ...existing,
                  week: `W${selectedWeek}`,
                  week_number: selectedWeek,
                  phase: selectedPhase || existing.phase,
                  planned_exercises: combined,
                })
              }
            }
          } else {
            throw err
          }
        }
      }

      setIsCopyModalOpen(false)
      pushToast({ message: `Sessions copied to Week ${selectedWeek}`, type: 'success' })
      useProgramStore.getState().loadProgram(version)
    } catch (err) {
      console.error('Copy failed:', err)
      pushToast({ message: 'Failed to copy sessions: ' + err, type: 'error' })
    }
  }

  function openSessionEditor(session?: Session, date?: string, index?: number) {
    if (session) {
      setEditingSession(session)
      setEditingSessionDate(session.date)
      setEditingSessionGlobalIndex(
        index !== undefined && index >= 0
          ? program?.sessions.indexOf(session) ?? -1
          : program?.sessions.findIndex(s => s.date === session.date && s.week_number === session.week_number && s.day === session.day) ?? -1
      )
      setSessionDate(session.date)
      setPlannedExercises((session.planned_exercises || []).map((ex, i) => ({ ...ex, id: `ex-${Date.now()}-${i}` })))
    } else {
      setEditingSession(null)
      setEditingSessionDate('')
      setEditingSessionGlobalIndex(-1)
      const usedDates = new Set(weekSessions.map((s) => s.date))
      setSessionDate(selectableWeekDates.find((date) => !usedDates.has(date)) ?? selectableWeekDates[0] ?? selectedWeekStartDate)
      setPlannedExercises([])
    }
    setIsSessionEditorOpen(true)
  }

  function closeSessionEditor() {
    setEditingSession(null)
    setEditingSessionDate('')
    setEditingSessionGlobalIndex(-1)
    setIsSessionEditorOpen(false)
    setPlannedExercises([])
    setExerciseSearch('')
  }

  async function saveSession() {
    try {
      if (!sessionDate) {
        pushToast({ message: 'Choose a session date before saving', type: 'error' })
        return
      }

      const dateStr = sessionDate
      if (program?.meta?.program_start && dateStr < program.meta.program_start) {
        pushToast({ message: 'Session date is before program start', type: 'error' })
        return
      }
      const day = getDayOfWeek(dateStr)
      
      // Strip IDs before saving
      const exercisesToSave = plannedExercises.map(({ id, ...rest }) => rest)

      const sessionData: Partial<Session> & { date: string } = {
        date: dateStr,
        day,
        week: `W${selectedWeek}`,
        week_number: selectedWeek,
        block,
        status: 'planned',
        completed: false,
        planned_exercises: exercisesToSave,
        exercises: [],
        session_notes: '',
      }

      console.log('Sending sessionData:', sessionData)

      if (editingSession) {
        if (editingSessionGlobalIndex < 0) {
          throw new Error('Could not resolve the session index for update')
        }
        await api.updatePlannedExercises(version, editingSessionDate, editingSessionGlobalIndex, exercisesToSave)
        if (dateStr !== editingSessionDate) {
          await api.rescheduleSession(version, editingSessionDate, editingSessionGlobalIndex, dateStr, day)
        }
      } else {
        await createSession(sessionData)
      }

      closeSessionEditor()
      useProgramStore.getState().loadProgram(version)
    } catch (err) {
      console.error('Failed to save session:', err)
      pushToast({ message: 'Failed to save session', type: 'error' })
    }
  }

  function addPlannedExercise(exercise: GlossaryExercise) {
    setPlannedExercises(prev => [...prev, {
      id: `ex-${Date.now()}-${prev.length}`,
      name: exercise.name,
      sets: 3,
      reps: 5,
      kg: null,
    }])
    setExerciseSearch('')
  }

  function updatePlannedExercise(id: string, field: keyof PlannedExercise, value: unknown) {
    setPlannedExercises(prev => prev.map((pe) => pe.id === id ? { ...pe, [field]: value } : pe))
  }

  function movePlannedExercise(id: string, direction: -1 | 1) {
    setPlannedExercises(prev => {
      const index = prev.findIndex((ex) => ex.id === id)
      const nextIndex = index + direction
      if (index < 0 || nextIndex < 0 || nextIndex >= prev.length) return prev
      return arrayMove(prev, index, nextIndex)
    })
  }

  function removePlannedExercise(id: string) {
    setPlannedExercises(prev => prev.filter((ex) => ex.id !== id))
  }

  const filteredGlossary = useMemo(() => {
    if (!exerciseSearch.trim()) return glossary.slice(0, 10)
    const q = exerciseSearch.toLowerCase()
    return glossary.filter(e => e.name.toLowerCase().includes(q)).slice(0, 10)
  }, [glossary, exerciseSearch])

  const autocompleteData = useMemo(() => Array.from(new Set(filteredGlossary.map(e => e.name))), [filteredGlossary])

  return (
    <Stack gap="md">
      <Group justify="space-between">
        <Group gap="xs">
          <Text component={Link} to="/designer" size="sm" c="dimmed">Designer</Text>
          <Text c="dimmed">/</Text>
          <Text fw={700} size="xl">Session Design</Text>
        </Group>
        <Group gap="sm" wrap="wrap">
          <Select
            value={String(selectedWeek)}
            onChange={(v) => {
              const w = Number(v ?? 1)
              setSelectedWeek(w)
            }}
            data={weekOptions.map(w => ({ value: String(w), label: `Week ${w}` }))}
            size="sm"
            w={120}
          />
          <Button
            leftSection={<Plus size={16} />}
            size="sm"
            onClick={() => openSessionEditor()}
          >
            Add Session
          </Button>
        </Group>
      </Group>

      {/* Week Navigation & Copy Buttons */}
      <Group justify="space-between" wrap="nowrap">
        <Group gap="xs">
          <Button 
            variant="default" 
            size="compact-sm" 
            leftSection={<ArrowLeft size={14} />}
            disabled={selectedWeek <= 1}
            onClick={() => setSelectedWeek(prev => prev - 1)}
          >
            Prev Week
          </Button>
          <Button 
            variant="default" 
            size="compact-sm" 
            rightSection={<ArrowRight size={14} />}
            disabled={selectedWeek >= totalWeeks}
            onClick={() => setSelectedWeek(prev => prev + 1)}
          >
            Next Week
          </Button>
        </Group>
        <Group gap="xs">
          <Button 
            variant="light" 
            size="compact-sm" 
            leftSection={<Copy size={14} />}
            disabled={selectedWeek <= 1}
            onClick={() => handleCopySessions(selectedWeek - 1)}
          >
            Copy Previous
          </Button>
          <Button 
            variant="light" 
            size="compact-sm" 
            leftSection={<Copy size={14} />}
            disabled={selectedWeek >= totalWeeks}
            onClick={() => handleCopySessions(selectedWeek + 1)}
          >
            Copy Next
          </Button>
        </Group>
      </Group>

      {/* Planned Volume Graph */}
      {(plannedMuscleVolume.length > 0 || plannedSbdSets.squat + plannedSbdSets.bench + plannedSbdSets.deadlift > 0) && (
        <Paper withBorder p="md">
          <Group gap="xs" mb="md">
            <BarChart3 size={18} />
            <Text fw={500}>Planned Weekly Volume</Text>
          </Group>
          <Stack gap="xs">
            {(() => {
              const allItems = [
                ...plannedMuscleVolume,
                { label: 'Squat', sets: plannedSbdSets.squat },
                { label: 'Bench', sets: plannedSbdSets.bench },
                { label: 'Deadlift', sets: plannedSbdSets.deadlift },
              ].filter(item => item.sets > 0)
              const maxSets = Math.max(...allItems.map(v => v.sets), 1)
              const sbdLabels = new Set(['Squat', 'Bench', 'Deadlift'])
              return allItems.map((item, i) => (
                <Box key={i}>
                  <Group justify="space-between" mb={2}>
                    <Text size="xs" fw={500}>{item.label}</Text>
                    <Text size="xs" c="dimmed">{item.sets.toFixed(1)} sets</Text>
                  </Group>
                  <Progress
                    value={(item.sets / maxSets) * 100}
                    size="sm"
                    color={sbdLabels.has(item.label) ? 'teal' : 'blue'}
                    radius="xl"
                  />
                </Box>
              ))
            })()}
          </Stack>
        </Paper>
      )}

      {/* Session cards */}
      {weekSessions.length > 0 ? (
        <SimpleGrid cols={{ base: 1, sm: 2, xl: 3 }} spacing="md">
          {weekSessions.map((session, i) => (
            <Paper
              key={`${session.date}-${i}`}
              withBorder
              p="md"
              style={{ cursor: 'pointer' }}
              onClick={() => openSessionEditor(session, session.date, i)}
            >
              <Group justify="space-between" mb="xs">
                <Text fw={500}>{session.day}</Text>
                <Badge variant="light" color={STATUS_COLORS[session.status ?? 'planned'] || 'blue'} size="sm">
                  {session.status || 'planned'}
                </Badge>
              </Group>
              <Text size="sm" c="dimmed" mb="sm">{session.date}</Text>

              {(session.planned_exercises || []).length > 0 ? (
                <Stack gap={4}>
                  {(() => {
                    const groups: Record<string, { sets: number; reps: number; kg: number | null }[]> = {}
                    for (const ex of session.planned_exercises!) {
                      if (!groups[ex.name]) groups[ex.name] = []
                      groups[ex.name].push(ex)
                    }
                    return Object.entries(groups).map(([name, items], j) => (
                      <Group key={j} justify="space-between" wrap="nowrap">
                        <Text size="sm" truncate style={{ flex: 1 }}>{name}</Text>
                        <Stack gap={0} align="flex-end">
                          {items.map((item, k) => (
                            <Text key={k} size="sm" c="dimmed">
                              {item.sets}x{item.reps}{item.kg !== null ? ` @${displayWeight(item.kg, unit)}` : ''}
                            </Text>
                          ))}
                        </Stack>
                      </Group>
                    ))
                  })()}
                </Stack>
              ) : (
                <Text size="sm" c="dimmed">No exercises planned</Text>
              )}

              {session.exercises?.length > 0 && (
                <Text size="xs" c="dimmed" mt="sm" style={{ borderTop: '1px solid var(--mantine-color-default-border)' }} pt="sm">
                  {session.exercises.length} exercises logged
                </Text>
              )}
            </Paper>
          ))}
        </SimpleGrid>
      ) : (
        <Group justify="center" py={48}>
          <Text c="dimmed">No sessions for Week {selectedWeek}. Click "Add Session" to plan one.</Text>
        </Group>
      )}

      {/* Session Editor Modal */}
      <Modal
        opened={isSessionEditorOpen}
        onClose={closeSessionEditor}
        title={editingSession ? 'Edit Session' : 'Plan Session'}
        size="lg"
        styles={{
          content: {
            maxHeight: 'calc(var(--app-viewport-height, 100dvh) - 32px)',
            display: 'flex',
            flexDirection: 'column',
          },
          body: {
            flex: 1,
            minHeight: 0,
            overflowY: 'auto',
            overscrollBehavior: 'contain',
            paddingBottom: 'calc(var(--mantine-spacing-md) + env(safe-area-inset-bottom, 0px))',
          },
        }}
      >
        <Stack gap="md">
          <Stack gap="xs">
            <DatePickerInput
              label="Date"
              value={sessionDate}
              onChange={setSessionDate}
              valueFormat="ddd MMM D, YYYY"
              defaultDate={selectedWeekStartDate}
              minDate={selectableWeekDates[0] ?? selectedWeekStartDate}
              maxDate={selectedWeekEndDate}
              clearable={false}
            />
            <Group gap="xs" wrap="wrap">
              <Badge variant="light">Week {selectedWeek}</Badge>
              {inferredSessionDay && <Badge variant="light">{inferredSessionDay}</Badge>}
              <Badge variant="light">{selectedPhase?.name ?? 'Unscheduled'}</Badge>
            </Group>
          </Stack>

          {/* Planned exercises */}
          <Stack gap="xs">
            <Text size="sm" c="dimmed">Planned Exercises</Text>

            <DndContext
              sensors={sensors}
              collisionDetection={closestCenter}
              onDragEnd={handleDragEnd}
            >
              <SortableContext
                items={plannedExercises.map((ex) => ex.id)}
                strategy={verticalListSortingStrategy}
              >
                <Stack gap="xs">
                  {plannedExercises.map((ex, index) => (
                    <SortableExercise
                      key={ex.id}
                      ex={ex}
                      onRemove={removePlannedExercise}
                      onUpdate={updatePlannedExercise}
                      onMoveUp={(id) => movePlannedExercise(id, -1)}
                      onMoveDown={(id) => movePlannedExercise(id, 1)}
                      canMoveUp={index > 0}
                      canMoveDown={index < plannedExercises.length - 1}
                    />
                  ))}
                </Stack>
              </SortableContext>
            </DndContext>

            {/* Add exercise */}
            <Autocomplete
              value={exerciseSearch}
              onChange={setExerciseSearch}
              data={autocompleteData}
              placeholder="Search exercises to add..."
              mt="sm"
              onOptionSubmit={(value) => {
                const match = glossary.find(e => e.name.toLowerCase() === value.toLowerCase())
                if (match) {
                  addPlannedExercise(match)
                } else {
                  // If no exact match in glossary, still add it as a custom exercise
                  setPlannedExercises(prev => [...prev, {
                    id: `ex-${Date.now()}-${prev.length}`,
                    name: value,
                    sets: 3,
                    reps: 5,
                    kg: null,
                  }])
                  setExerciseSearch('')
                }
              }}
            />
            <Text size="xs" c="dimmed">Select an exercise from the dropdown to add it.</Text>
          </Stack>

          <Divider mt="md" />

          <Group justify="space-between" mt="md">
            {editingSession ? (
              <Button
                color="red"
                variant="subtle"
                leftSection={<Trash2 size={16} />}
                onClick={async () => {
                  if (confirm('Are you sure you want to delete this session? This cannot be undone.')) {
                    try {
                      await api.deleteSession(version, editingSessionDate, editingSessionGlobalIndex)
                      pushToast({ message: 'Session deleted successfully', type: 'success' })
                      closeSessionEditor()
                      useProgramStore.getState().loadProgram(version)
                    } catch (err) {
                      console.error('Failed to delete session:', err)
                      pushToast({ message: 'Failed to delete session', type: 'error' })
                    }
                  }
                }}
              >
                Delete Session
              </Button>
            ) : <Box />}
            
            <Group gap="sm">
              <Button variant="default" onClick={closeSessionEditor}>
                Cancel
              </Button>
              <Button
                leftSection={<Save size={16} />}
                onClick={saveSession}
              >
                {editingSession ? 'Update' : 'Create'} Session
              </Button>
            </Group>
          </Group>
        </Stack>
      </Modal>

      {/* Copy Confirmation Modal */}
      <Modal
        opened={isCopyModalOpen}
        onClose={() => setIsCopyModalOpen(false)}
        title={`Copy Sessions from Week ${copySourceWeek}`}
      >
        <Stack gap="md">
          <Text size="sm">
            You are about to copy all planned sessions from Week {copySourceWeek} to Week {selectedWeek}.
            Existing sessions in Week {selectedWeek} that fall on the same day will be handled based on your choice below.
            <Text fw={700} c="orange" mt="sm">Completed sessions will never be overwritten.</Text>
          </Text>

          <Select
            label="Collision Handling"
            value={copyCollisionMode}
            onChange={(v) => setCopyCollisionMode(v as 'overwrite' | 'add')}
            data={[
              { value: 'overwrite', label: 'Overwrite - Replace target day sets' },
              { value: 'add', label: 'Add - Keep existing and add new sets' },
            ]}
          />

          <Group justify="flex-end" mt="md">
            <Button variant="default" onClick={() => setIsCopyModalOpen(false)}>Cancel</Button>
            <Button color="blue" onClick={executeCopy}>Copy Sessions</Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  )
}
