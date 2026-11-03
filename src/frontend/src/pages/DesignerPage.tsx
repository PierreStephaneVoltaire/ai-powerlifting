import { useState, useEffect, useMemo } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Plus, Trash2, Save, BarChart3, Copy, ArrowLeft, ArrowRight, ArrowUp, ArrowDown, GripVertical } from 'lucide-react'
import {
  Stack, Group, Text, Button, Modal,
  Select, Autocomplete, Box, SegmentedControl
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
import { useAuth } from '@/auth/AuthProvider'
import { LoadTypeBadge } from '@/components/shared/LoadTypeBadge'
import DraftNumberInput from '@/components/sessions/DraftNumberInput'
import { formatPlannedExercise, hasRepRange, plannedSets } from '@/utils/plannedPrescription'
import type { Session, PlannedExercise, PlannedSet, GlossaryExercise } from '@powerlifting/types'

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

type DesignLayout = 'straight' | 'per-set'
type RepsMode = 'fixed' | 'range'

function isPositiveInteger(value: number): boolean {
  return value > 0 && Number.isInteger(value)
}

function isNonNegative(value: number): boolean {
  return value >= 0
}

function isValidRpe(value: number): boolean {
  return value >= 1 && value <= 10 && (value * 2) % 1 === 0
}

function withTopLevelFromPlan(plan: PlannedSet[]): Partial<PlannedExercise> {
  const first = plan[0]
  return {
    set_plan: plan,
    sets: plan.length,
    reps: first?.reps ?? 0,
    reps_max: first?.reps_max ?? null,
    kg: first?.kg ?? null,
    rpe_target: first?.rpe_target ?? null,
  }
}

function SortableExercise({ ex, onRemove, onPatch, onMoveUp, onMoveDown, canMoveUp, canMoveDown, readOnly = false }: {
  ex: PlannedExerciseWithId;
  onRemove: (id: string) => void;
  onPatch: (id: string, patch: Partial<PlannedExercise>) => void;
  onMoveUp: (id: string) => void;
  onMoveDown: (id: string) => void;
  canMoveUp: boolean;
  canMoveDown: boolean;
  readOnly?: boolean;
}) {
  const { unit } = useSettingsStore()
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging
  } = useSortable({ id: ex.id, disabled: readOnly })
  const [layout, setLayout] = useState<DesignLayout>(() => ex.set_plan?.length ? 'per-set' : 'straight')
  const [repsMode, setRepsMode] = useState<RepsMode>(() => hasRepRange(ex) ? 'range' : 'fixed')

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    zIndex: isDragging ? 1000 : undefined,
    opacity: isDragging ? 0.5 : 1,
    display: 'flex',
    flexDirection: 'column' as const,
    alignItems: 'stretch',
  }

  const displayUnit = unit as 'kg' | 'lb'
  const toDisplay = (kg: number) => toDisplayUnit(kg, displayUnit)
  const fromDisplay = (value: number) => fromDisplayUnit(value, displayUnit)
  const plan = ex.set_plan ?? []
  const baseSet: PlannedSet = { reps: ex.reps, reps_max: ex.reps_max ?? null, kg: ex.kg, rpe_target: ex.rpe_target ?? null }

  const changeLayout = (next: DesignLayout) => {
    setLayout(next)
    if (next === 'per-set') {
      const seed = plannedSets(ex)
      onPatch(ex.id, withTopLevelFromPlan(seed.length ? seed : [baseSet]))
    } else {
      onPatch(ex.id, { ...(plan[0] ?? baseSet), set_plan: undefined })
    }
  }

  const changeRepsMode = (next: RepsMode) => {
    setRepsMode(next)
    const repsMaxFor = (reps: number) => next === 'range' ? reps : null
    onPatch(ex.id, {
      reps_max: repsMaxFor(ex.reps),
      ...(plan.length ? { set_plan: plan.map((set) => ({ ...set, reps_max: repsMaxFor(set.reps) })) } : {}),
    })
  }

  const resizePlan = (count: number) => {
    const next = Array.from({ length: count }, (_, i) => plan[i] ?? plan[plan.length - 1] ?? baseSet)
    onPatch(ex.id, withTopLevelFromPlan(next))
  }

  const updateSet = (index: number, patch: Partial<PlannedSet>) => {
    onPatch(ex.id, withTopLevelFromPlan(plan.map((set, i) => i === index ? { ...set, ...patch } : set)))
  }

  const renderReps = (
    reps: number | null | undefined,
    repsMax: number | null | undefined,
    onChange: (patch: { reps?: number; reps_max?: number | null }) => void,
    label: string,
  ) => repsMode === 'range' ? (
    <Group gap={4} wrap="nowrap">
      <DraftNumberInput
        value={reps}
        onValueChange={(next) => next !== null && onChange({ reps: next })}
        isValid={isPositiveInteger}
        nullable={false}
        commitOnlyValid
        size="xs"
        w={48}
        placeholder="Min"
        disabled={readOnly}
        aria-label={`${label} minimum reps`}
      />
      <span className="if-designer-at">–</span>
      <DraftNumberInput
        value={repsMax}
        onValueChange={(next) => onChange({ reps_max: next })}
        isValid={(value) => isPositiveInteger(value) && value >= (reps ?? 0)}
        size="xs"
        w={48}
        placeholder="Max"
        disabled={readOnly}
        aria-label={`${label} maximum reps`}
      />
    </Group>
  ) : (
    <DraftNumberInput
      value={reps}
      onValueChange={(next) => next !== null && onChange({ reps: next })}
      isValid={isPositiveInteger}
      nullable={false}
      commitOnlyValid
      size="xs"
      w={48}
      placeholder="Reps"
      disabled={readOnly}
      aria-label={`${label} reps`}
    />
  )

  const renderLoad = (
    kg: number | null,
    rpeTarget: number | null | undefined,
    onChange: (patch: { kg?: number | null; rpe_target?: number | null }) => void,
    label: string,
  ) => {
    if (ex.load_source === 'unresolvable') return <span className="if-designer-at">—</span>
    if (ex.load_source === 'rpe') {
      return (
        <DraftNumberInput
          value={rpeTarget}
          onValueChange={(next) => onChange({ rpe_target: next })}
          isValid={isValidRpe}
          size="xs"
          w={60}
          placeholder="RPE"
          disabled={readOnly}
          aria-label={`${label} RPE`}
        />
      )
    }
    return (
      <Group gap={4} wrap="nowrap">
        {ex.load_source === 'percentage' && <span className="if-designer-at">~</span>}
        <DraftNumberInput
          value={kg}
          onValueChange={(next) => onChange({ kg: next })}
          isValid={isNonNegative}
          toDisplay={toDisplay}
          fromDisplay={fromDisplay}
          size="xs"
          w={64}
          placeholder={unit}
          disabled={readOnly}
          aria-label={`${label} weight`}
        />
      </Group>
    )
  }

  const setsInput = (
    <DraftNumberInput
      value={layout === 'per-set' ? plan.length : ex.sets}
      onValueChange={(next) => next !== null && (layout === 'per-set' ? resizePlan(next) : onPatch(ex.id, { sets: next }))}
      isValid={isPositiveInteger}
      nullable={false}
      commitOnlyValid
      size="xs"
      w={48}
      placeholder="Sets"
      disabled={readOnly}
      aria-label={`${ex.name} sets`}
    />
  )

  return (
    <div ref={setNodeRef} style={style} className="if-designer-ex-block">
      <Group gap={8} wrap="nowrap">
        <span {...(readOnly ? {} : { ...attributes, ...listeners })} className="if-designer-drag-handle">
          <GripVertical size={16} />
        </span>
        <span className="if-designer-ex-block-name">{ex.name}</span>
        {ex.load_source && <LoadTypeBadge source={ex.load_source} />}
        <button
          className="if-designer-icon-btn"
          type="button"
          onClick={() => onMoveUp(ex.id)}
          disabled={!canMoveUp || readOnly}
          title="Move exercise up"
          aria-label="Move exercise up"
        >
          <ArrowUp size={13} />
        </button>
        <button
          className="if-designer-icon-btn"
          type="button"
          onClick={() => onMoveDown(ex.id)}
          disabled={!canMoveDown || readOnly}
          title="Move exercise down"
          aria-label="Move exercise down"
        >
          <ArrowDown size={13} />
        </button>
        <button
          className="if-designer-icon-btn if-designer-icon-btn-danger"
          type="button"
          onClick={() => onRemove(ex.id)}
          title="Remove exercise"
          aria-label="Remove exercise"
          disabled={readOnly}
        >
          <Trash2 size={13} />
        </button>
      </Group>

      <Group gap="xs" wrap="wrap">
        <SegmentedControl
          size="xs"
          value={layout}
          onChange={(next) => changeLayout(next as DesignLayout)}
          data={[
            { label: 'Straight sets', value: 'straight' },
            { label: 'Per set', value: 'per-set' },
          ]}
          disabled={readOnly}
        />
        <SegmentedControl
          size="xs"
          value={repsMode}
          onChange={(next) => changeRepsMode(next as RepsMode)}
          data={[
            { label: 'Fixed reps', value: 'fixed' },
            { label: 'Rep range', value: 'range' },
          ]}
          disabled={readOnly}
        />
      </Group>

      {layout === 'straight' ? (
        <Group gap={6} wrap="wrap" align="center">
          {setsInput}
          <span className="if-designer-at">x</span>
          {renderReps(ex.reps, ex.reps_max, (patch) => onPatch(ex.id, patch), ex.name)}
          <span className="if-designer-at">@</span>
          {renderLoad(ex.kg, ex.rpe_target, (patch) => onPatch(ex.id, patch), ex.name)}
        </Group>
      ) : (
        <Stack gap={6}>
          <Group gap={6} align="center">
            <span className="if-designer-at">Sets</span>
            {setsInput}
          </Group>
          {plan.map((set, setIndex) => (
            <Group key={setIndex} gap={6} wrap="nowrap" align="center">
              <span className="if-designer-at" style={{ width: 40 }}>Set {setIndex + 1}</span>
              {renderReps(set.reps, set.reps_max, (patch) => updateSet(setIndex, patch), `Set ${setIndex + 1}`)}
              <span className="if-designer-at">@</span>
              {renderLoad(set.kg, set.rpe_target, (patch) => updateSet(setIndex, patch), `Set ${setIndex + 1}`)}
            </Group>
          ))}
        </Stack>
      )}
    </div>
  )
}

export default function DesignerPage() {
  const { readOnly } = useAuth()
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
      const sets = Number(ex.sets) || 0
      if (name.includes('squat') && !name.includes('split') && !name.includes('hack')) counts.squat += sets
      else if (name === 'bench' || name === 'bench press') counts.bench += sets
      else if ((name === 'deadlift' || name.includes('deadlift')) && !name.includes('romanian') && !name.includes('rdl')) counts.deadlift += sets
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
          }, api.mutationEnvelope(useProgramStore.getState().program?.meta.revision ?? 0))
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
                }, api.mutationEnvelope(useProgramStore.getState().program?.meta.revision ?? 0, undefined, existing.id))
              } else {
                const combined = [...(existing.planned_exercises || []), ...(src.planned_exercises || [])]
                await api.updateSession(version, targetDate, existingIndex, {
                  ...existing,
                  week: `W${selectedWeek}`,
                  week_number: selectedWeek,
                  phase: selectedPhase || existing.phase,
                  planned_exercises: combined,
                }, api.mutationEnvelope(useProgramStore.getState().program?.meta.revision ?? 0, undefined, existing.id))
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
        await api.updatePlannedExercises(version, editingSessionDate, editingSessionGlobalIndex, exercisesToSave, api.mutationEnvelope(useProgramStore.getState().program?.meta.revision ?? 0, undefined, editingSession.id))
        if (dateStr !== editingSessionDate) {
          await useProgramStore.getState().loadProgram(version)
          await api.rescheduleSession(version, editingSessionDate, editingSessionGlobalIndex, dateStr, day, api.mutationEnvelope(useProgramStore.getState().program?.meta.revision ?? 0, undefined, editingSession.id))
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

  function patchPlannedExercise(id: string, patch: Partial<PlannedExercise>) {
    setPlannedExercises(prev => prev.map((pe) => {
      if (pe.id !== id) return pe
      const next = { ...pe, ...patch }
      if ('set_plan' in patch && patch.set_plan === undefined) delete next.set_plan
      if (next.reps_max == null) delete next.reps_max
      return next
    }))
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
    <div className="if-designer-session-page">
      <div className="if-designer-breadcrumb">
        <Link to="/designer">Designer</Link> / <span>Session Design</span>
      </div>

      <div className="if-designer-top-bar">
        <div className="if-designer-page-title">Session Design</div>
        <div className="if-designer-top-right">
          <button
            type="button"
            className="if-designer-btn"
            disabled={selectedWeek <= 1 || readOnly}
            onClick={() => handleCopySessions(selectedWeek - 1)}
          >
            <Copy size={14} /> Copy Previous
          </button>
          <button
            type="button"
            className="if-designer-btn"
            disabled={selectedWeek >= totalWeeks || readOnly}
            onClick={() => handleCopySessions(selectedWeek + 1)}
          >
            <Copy size={14} /> Copy Next
          </button>
          <button
            type="button"
            className="if-designer-btn if-designer-btn-primary"
            onClick={() => openSessionEditor()}
            disabled={readOnly}
          >
            <Plus size={14} /> Add Session
          </button>
        </div>
      </div>

      <div className="if-designer-week-bar">
        <div className="if-designer-week-nav">
          <button
            type="button"
            className="if-designer-btn"
            disabled={selectedWeek <= 1}
            onClick={() => setSelectedWeek(prev => prev - 1)}
          >
            <ArrowLeft size={14} /> Prev Week
          </button>
          <button
            type="button"
            className="if-designer-btn"
            disabled={selectedWeek >= totalWeeks}
            onClick={() => setSelectedWeek(prev => prev + 1)}
          >
            Next Week <ArrowRight size={14} />
          </button>
        </div>
        <select
          className="if-designer-week-selector"
          value={selectedWeek}
          onChange={(event) => setSelectedWeek(Number(event.currentTarget.value))}
        >
          {weekOptions.map(w => <option key={w} value={w}>Week {w}</option>)}
        </select>
      </div>

      <div className="if-designer-vol-card">
        <div className="if-designer-vol-title"><BarChart3 size={16} /> Planned Weekly Volume</div>
        {(() => {
          const allItems = [
            ...plannedMuscleVolume,
            { label: 'Squat', sets: plannedSbdSets.squat },
            { label: 'Bench', sets: plannedSbdSets.bench },
            { label: 'Deadlift', sets: plannedSbdSets.deadlift },
          ].filter(item => item.sets > 0)
          const maxSets = Math.max(...allItems.map(v => v.sets), 1)
          const sbdLabels = new Set(['Squat', 'Bench', 'Deadlift'])
          if (allItems.length === 0) {
            return <div className="if-designer-add-help">No planned volume for this week.</div>
          }
          return allItems.map((item, i) => (
            <div className="if-designer-vol-row" key={`${item.label}-${i}`}>
              <span className="if-designer-vol-label">{item.label}</span>
              <span className="if-designer-vol-bar-wrap">
                <span
                  className="if-designer-vol-bar"
                  style={{
                    display: 'block',
                    width: `${(item.sets / maxSets) * 100}%`,
                    background: sbdLabels.has(item.label) ? 'hsl(142,60%,45%)' : 'hsl(214,70%,55%)',
                  }}
                />
              </span>
              <span className="if-designer-vol-count">{Number(item.sets).toFixed(1).replace(/\.0$/, '')} sets</span>
            </div>
          ))
        })()}
      </div>

      {weekSessions.length > 0 ? (
        <div className="if-designer-sess-grid">
          {weekSessions.map((session, i) => {
            const status = session.completed ? 'completed' : (session.status || 'planned')
            const groups: Record<string, PlannedExercise[]> = {}
            for (const ex of session.planned_exercises || []) {
              if (!groups[ex.name]) groups[ex.name] = []
              groups[ex.name].push(ex)
            }
            return (
              <button
                key={`${session.date}-${i}`}
                type="button"
                className="if-designer-sess-card"
                disabled={readOnly}
                onClick={() => openSessionEditor(session, session.date, i)}
              >
                <div className="if-designer-sess-head">
                  <span className="if-designer-sess-day">{session.day}</span>
                  <span className="if-designer-status-pill" data-status={status}>{status}</span>
                </div>
                <div className="if-designer-sess-date">{session.date}</div>

                {Object.entries(groups).length > 0 ? (
                  <div>
                    {Object.entries(groups).map(([name, items], j) => (
                      <div className="if-designer-ex-line" key={`${name}-${j}`}>
                        <span className="if-designer-ex-line-name">{name}</span>
                        <span className="if-designer-ex-line-sets">
                          {items.map((item) => formatPlannedExercise(item, (kg) => displayWeight(kg, unit))).join('\n')}
                        </span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="if-designer-add-help">No exercises planned</div>
                )}

                {session.exercises?.length > 0 && (
                  <div className="if-designer-logged">{session.exercises.length} exercises logged</div>
                )}
              </button>
            )
          })}
        </div>
      ) : (
        <div className="if-designer-empty">No sessions for Week {selectedWeek}. Click "Add Session" to plan one.</div>
      )}

      {/* Session Editor Modal */}
      <Modal
        opened={isSessionEditorOpen}
        onClose={closeSessionEditor}
        title={editingSession ? 'Edit Session' : 'Plan Session'}
        size="lg"
        classNames={{
          content: 'if-designer-modal-content',
          header: 'if-designer-modal-header',
          title: 'if-designer-modal-title',
          body: 'if-designer-modal-body',
        }}
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
        <div className="if-designer-modal-form">
          <div>
            <DatePickerInput
              label="Date"
              value={sessionDate}
              onChange={setSessionDate}
              valueFormat="ddd MMM D, YYYY"
              defaultDate={selectedWeekStartDate}
              disabled={readOnly}
              minDate={selectableWeekDates[0] ?? selectedWeekStartDate}
              maxDate={selectedWeekEndDate}
              clearable={false}
            />
            <div className="if-designer-pill-row" style={{ marginTop: 8 }}>
              <span className="if-designer-pill-tag">Week {selectedWeek}</span>
              {inferredSessionDay && <span className="if-designer-pill-tag">{inferredSessionDay}</span>}
              <span className="if-designer-pill-tag if-designer-pill-tag-info">{selectedPhase?.name ?? 'Unscheduled'}</span>
            </div>
          </div>

          {/* Planned exercises */}
          <div>
            <div className="if-designer-section-title">Planned Exercises</div>

            <DndContext
              sensors={sensors}
              collisionDetection={closestCenter}
              onDragEnd={handleDragEnd}
            >
              <SortableContext
                items={plannedExercises.map((ex) => ex.id)}
                strategy={verticalListSortingStrategy}
              >
                <div className="if-designer-ex-list">
                  {plannedExercises.map((ex, index) => (
                    <SortableExercise
                      key={ex.id}
                      ex={ex}
                      onRemove={removePlannedExercise}
                      onPatch={patchPlannedExercise}
                      onMoveUp={(id) => movePlannedExercise(id, -1)}
                      onMoveDown={(id) => movePlannedExercise(id, 1)}
                      canMoveUp={index > 0}
                      canMoveDown={index < plannedExercises.length - 1}
                      readOnly={readOnly}
                    />
                  ))}
                  {plannedExercises.length === 0 && (
                    <div className="if-designer-add-help">No exercises. Add below.</div>
                  )}
                </div>
              </SortableContext>
            </DndContext>

            {/* Add exercise */}
            <Autocomplete
              value={exerciseSearch}
              onChange={setExerciseSearch}
              data={autocompleteData}
              placeholder="Search exercises to add..."
              mt="sm"
              disabled={readOnly}
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
            <div className="if-designer-add-help">Select an exercise from the dropdown to add it.</div>
          </div>

          <div className="if-designer-modal-foot">
            {editingSession ? (
              <button
                type="button"
                className="if-designer-btn if-designer-btn-danger"
                disabled={readOnly}
                onClick={async () => {
                  if (confirm('Are you sure you want to delete this session? This cannot be undone.')) {
                    try {
                      await api.deleteSession(version, editingSessionDate, editingSessionGlobalIndex, api.mutationEnvelope(useProgramStore.getState().program?.meta.revision ?? 0, undefined, editingSession.id))
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
                <Trash2 size={14} /> Delete Session
              </button>
            ) : <Box />}
            
            <div className="if-designer-modal-actions">
              <button type="button" className="if-designer-btn" onClick={closeSessionEditor}>
                Cancel
              </button>
              <button
                type="button"
                className="if-designer-btn if-designer-btn-primary"
                onClick={saveSession}
                disabled={readOnly}
              >
                <Save size={14} />
                {editingSession ? 'Update' : 'Create'} Session
              </button>
            </div>
          </div>
        </div>
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
    </div>
  )
}
