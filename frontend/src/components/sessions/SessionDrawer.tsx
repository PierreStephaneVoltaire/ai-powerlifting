import { useState, useEffect, useMemo, Fragment, useRef } from 'react'
import { Drawer, Button, Group, Stack, Paper, SimpleGrid, TextInput, Textarea, Autocomplete, ActionIcon, Text, Box, Table, Divider, SegmentedControl, Slider, Modal, Badge, Menu, Tooltip, Checkbox } from '@mantine/core'
import { DatePickerInput } from '@mantine/dates'
import { useProgramStore } from '@/store/programStore'
import { useSettingsStore } from '@/store/settingsStore'
import { useUiStore } from '@/store/uiStore'
import { useRestTimerStore } from '@/store/restTimerStore'
import { getDayOfWeek } from '@/utils/dates'
import { displayWeight, toDisplayUnit, fromDisplayUnit } from '@/utils/units'
import { phaseColor } from '@/utils/phases'
import { fetchGlossary } from '@/api/client'
import { readDraft, removeDraftIfMatch, saveDraft, sessionDraftKey, legacySessionDraftKey, type Draft } from '@/api/drafts'
import { requestPartition } from '@/api/context'
import { X, Check, Save, RotateCcw, Plus, GripVertical, Trash2, Calendar, Film, HeartPulse, ArrowLeft, Calculator, Circle, CheckCircle2, XCircle, Minus, Bot, Wand2, MoreHorizontal, AlertTriangle, Timer } from 'lucide-react'
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
import type { Session, Exercise, ExerciseSetData, SessionVideo, SessionWellness, GlossaryExercise, SetStatus, FailedSetReason } from '@powerlifting/types'
import VideoGrid from './VideoGrid'
import VideoUploadModal from './VideoUploadModal'
import SessionToolkitModal from './SessionToolkitModal'
import SessionNotesHelperModal from './SessionNotesHelperModal'
import AutoRegulationModal from './AutoRegulationModal'
import RestTimerHeaderButton from './RestTimerHeaderButton'
import { normalizeExerciseName } from '@/utils/volume'
import { useAuth } from '@/auth/AuthProvider'
import Num from '@/components/shared/Num'

const WELLNESS_FIELDS: Array<{
  key: keyof Omit<SessionWellness, 'recorded_at'>
  label: string
}> = [
  { key: 'sleep', label: 'Sleep' },
  { key: 'soreness', label: 'Soreness' },
  { key: 'mood', label: 'Mood' },
  { key: 'stress', label: 'Stress' },
  { key: 'energy', label: 'Energy' },
]

function sanitizeRpe(raw: string): number | null {
  const trimmed = raw.trim()
  if (!trimmed) return null
  const parsed = Number(trimmed)
  if (!Number.isFinite(parsed)) return null
  if (parsed < 1 || parsed > 10) return null
  const decimal = Math.round((parsed % 1) * 10)
  if (decimal !== 0 && decimal !== 5) return null
  return parsed
}

function clampWellnessScore(value: number): 1 | 2 | 3 | 4 | 5 {
  return Math.max(1, Math.min(5, Math.round(value))) as 1 | 2 | 3 | 4 | 5
}

function createDefaultWellness(existing?: SessionWellness | null): SessionWellness {
  return {
    sleep: clampWellnessScore(existing?.sleep ?? 3),
    soreness: clampWellnessScore(existing?.soreness ?? 3),
    mood: clampWellnessScore(existing?.mood ?? 3),
    stress: clampWellnessScore(existing?.stress ?? 3),
    energy: clampWellnessScore(existing?.energy ?? 3),
    recorded_at: existing?.recorded_at ?? new Date().toISOString(),
  }
}

const SET_STATUS_META: Record<SetStatus, { label: string; color: string }> = {
  pending: { label: 'Pending', color: 'gray' },
  completed: { label: 'Completed', color: 'green' },
  failed: { label: 'Failed', color: 'red' },
  skipped: { label: 'Skipped', color: 'yellow' },
}

const FAILED_SET_REASON_OPTIONS: Array<{ value: FailedSetReason; label: string }> = [
  { value: 'strength_failure', label: 'Strength failure' },
  { value: 'technical_failure', label: 'Technical failure' },
  { value: 'command_failure', label: 'Command failure' },
  { value: 'grip', label: 'Grip' },
  { value: 'depth', label: 'Depth' },
  { value: 'pause', label: 'Pause' },
  { value: 'lockout', label: 'Lockout' },
  { value: 'balance', label: 'Balance' },
  { value: 'pain', label: 'Pain' },
  { value: 'fatigue', label: 'Fatigue' },
  { value: 'misload_bad_attempt_selection', label: 'Misload / bad attempt selection' },
]

const FAILED_SET_REASON_VALUES = new Set(FAILED_SET_REASON_OPTIONS.map((option) => option.value))
const FAILED_SET_REASON_LABELS = new Map(FAILED_SET_REASON_OPTIONS.map((option) => [option.value, option.label]))

function normalizeSetStatuses(exercise: Exercise, sessionCompleted = false): SetStatus[] {
  const setCount = Math.max(0, Math.round(Number(exercise.sets) || 0))
  const fallbackStatus: SetStatus = sessionCompleted ? 'completed' : 'pending'
  const source = Array.isArray(exercise.set_statuses)
    ? exercise.set_statuses
    : Array.from({ length: setCount }, (_, index) =>
        exercise.failed_sets?.[index] ? 'failed' : fallbackStatus
      )
  const normalized = source.slice(0, setCount).map((status) =>
    status === 'completed' || status === 'failed' || status === 'skipped' || status === 'pending'
      ? status
      : fallbackStatus
  )
  while (normalized.length < setCount) normalized.push(fallbackStatus)
  return normalized
}

function normalizeFailedSetReasons(exercise: Exercise, statuses = normalizeSetStatuses(exercise)): FailedSetReason[][] {
  const source = Array.isArray(exercise.failed_set_reasons) ? exercise.failed_set_reasons : []
  return statuses.map((status, setIndex) => {
    if (status !== 'failed') return []
    const rawReasons = Array.isArray(source[setIndex]) ? source[setIndex] : []
    const reasons: FailedSetReason[] = []
    for (const rawReason of rawReasons) {
      if (
        typeof rawReason === 'string' &&
        FAILED_SET_REASON_VALUES.has(rawReason as FailedSetReason) &&
        !reasons.includes(rawReason as FailedSetReason)
      ) {
        reasons.push(rawReason as FailedSetReason)
      }
    }
    return reasons
  })
}

function withSetStatusFields(exercise: Exercise, sessionCompleted = false): Exercise {
  const set_statuses = normalizeSetStatuses(exercise, sessionCompleted)
  const failed_sets = set_statuses.map((status) => status === 'failed')
  const failed_set_reasons = normalizeFailedSetReasons(exercise, set_statuses)
  return {
    ...exercise,
    set_statuses,
    failed_sets,
    failed_set_reasons,
    failed: failed_sets.some(Boolean),
  }
}

function normalizeSetData(exercise: Exercise): ExerciseSetData[] {
  const count = Math.max(0, Math.round(Number(exercise.sets) || 0))
  const source = Array.isArray(exercise.sets_data) ? exercise.sets_data : []
  return Array.from({ length: count }, (_, index) => ({
    reps: source[index]?.reps ?? exercise.reps ?? null,
    kg: source[index]?.kg ?? exercise.kg ?? null,
    rpe: source[index]?.rpe ?? exercise.rpe ?? null,
  }))
}

function cumulativeSetNumber(exercises: Exercise[], exerciseIndex: number, setIndex: number): number {
  const name = exercises[exerciseIndex].name
  const offset = exercises
    .slice(0, exerciseIndex)
    .filter((candidate) => candidate.name === name)
    .reduce((total, candidate) => total + Math.max(0, Math.round(Number(candidate.sets) || 0)), 0)
  return offset + setIndex + 1
}

function videosBySet(exercises: Exercise[], exerciseIndex: number, videos: SessionVideo[] = []): SessionVideo[][] {
  const exercise = exercises[exerciseIndex]
  const count = Math.max(0, Math.round(Number(exercise.sets) || 0))
  return Array.from({ length: count }, (_, setIndex) => {
    const setNumber = cumulativeSetNumber(exercises, exerciseIndex, setIndex)
    return videos.filter((video) => video.exercise_name === exercise.name && video.set_number === setNumber)
  })
}

function finalizeSessionForSave(session: Session): Session {
  return {
    ...session,
    status: session.completed ? 'completed' : (session.status || 'planned'),
    exercises: session.exercises.map((exercise) => {
      const set_statuses = normalizeSetStatuses(exercise, session.completed).map((status) =>
        session.completed && status === 'pending' ? 'completed' : status
      )
      return withSetStatusFields({ ...exercise, set_statuses }, session.completed)
    }),
  }
}

function statusCounts(exercise: Exercise): Record<SetStatus, number> {
  return normalizeSetStatuses(exercise).reduce<Record<SetStatus, number>>(
    (counts, status) => ({ ...counts, [status]: counts[status] + 1 }),
    { pending: 0, completed: 0, failed: 0, skipped: 0 }
  )
}

function failedReasonLabels(reasons: FailedSetReason[]): string {
  return reasons.map((reason) => FAILED_SET_REASON_LABELS.get(reason) || reason).join(', ')
}

function exerciseDragId(exercise: Exercise, index: number): string {
  return exercise.id || `ex-${index}`
}

interface SessionDrawerProps {
  isOpen: boolean
  onClose: () => void
  sessionIndex: number
  sessionArrayIndex: number
  mode?: 'drawer' | 'page'
  readOnly?: boolean
  onSaveSuccess?: () => void
  onDeleteSuccess?: () => void
}

function SortableExerciseItem({ 
  exercise, 
  index, 
  onRemove, 
  onUpdate, 
  onUpdateSets,
  onUpdateRpe,
  onUpdateSet,
  setVideos,
  onAddSetVideo,
  onShowVideos,
  glossaryNames,
  unit,
  renderMobileMenu,
  renderDesktopActions,
  renderSetStatusControls,
  renderStatusBadges,
  disabled = false,
}: { 
  exercise: Exercise;
  index: number;
  onRemove: (i: number) => void;
  onUpdate: (i: number, field: keyof Exercise, v: any) => void;
  onUpdateSets: (i: number, sets: number) => void;
  onUpdateRpe: (i: number, rpe: number | null) => void;
  onUpdateSet: (exerciseIndex: number, setIndex: number, patch: Partial<ExerciseSetData>) => void;
  setVideos: SessionVideo[][];
  onAddSetVideo: (exerciseIndex: number, setIndex: number) => void;
  onShowVideos: () => void;
  glossaryNames: string[];
  unit: string;
  renderMobileMenu: (ex: Exercise, i: number) => React.ReactNode;
  renderDesktopActions: (ex: Exercise, i: number) => React.ReactNode;
  renderSetStatusControls: (ex: Exercise, i: number) => React.ReactNode;
  renderStatusBadges: (ex: Exercise) => React.ReactNode;
  disabled?: boolean;
}) {
  const {
    attributes,
    listeners,
    setNodeRef,
    setActivatorNodeRef,
    transform,
    transition,
    isDragging
  } = useSortable({ id: exerciseDragId(exercise, index), disabled })

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    zIndex: isDragging ? 1000 : undefined,
    opacity: isDragging ? 0.5 : 1,
  }

  const setStatuses = normalizeSetStatuses(exercise)
  const setData = normalizeSetData(exercise)

  return (
    <Paper ref={setNodeRef} style={style} withBorder p={0} radius={10} className="if-exercise-card" data-testid={`session-exercise-${index}`}>
      <Group gap="xs" className="if-exercise-header">
        <Box
          ref={setActivatorNodeRef}
          {...(disabled ? {} : attributes)}
          {...(disabled ? {} : listeners)}
          className="if-exercise-drag"
          style={{ cursor: disabled ? 'default' : 'grab', touchAction: 'none' }}
          data-testid={`exercise-drag-handle-${index}`}
        >
          <GripVertical size={16} />
        </Box>
        <span
          className="if-mock-pill"
          style={{ background: 'var(--color-background-secondary)', borderColor: 'transparent', color: 'var(--color-text-secondary)', fontSize: 11, flexShrink: 0 }}
          data-testid={`exercise-index-${index}`}
        >
          #{index + 1}
        </span>
        <Autocomplete
          value={exercise.name}
          onChange={(newName) => onUpdate(index, 'name', newName)}
          data={glossaryNames}
          placeholder="Exercise name"
          size="sm"
          style={{ flex: 1 }}
          styles={{
            input: {
              background: 'transparent',
              borderColor: 'transparent',
              color: 'var(--text-primary)',
              fontSize: 15,
              fontWeight: 500,
            },
          }}
          disabled={disabled}
          data-testid={`exercise-name-${index}`}
        />
        <Group gap={4} wrap="nowrap">
          {renderMobileMenu(exercise, index)}
          {renderDesktopActions(exercise, index)}
          <ActionIcon
            visibleFrom="sm"
            variant="subtle"
            color="red"
            size="sm"
            onClick={() => onRemove(index)}
            disabled={disabled}
            data-testid={`exercise-delete-${index}`}
          >
            <Trash2 size={16} />
          </ActionIcon>
        </Group>
      </Group>

      <Box p={16}>
        <Group justify="space-between" align="flex-start" gap={4} mb="xs" wrap="nowrap">
          <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="xs" style={{ flex: 1, minWidth: 0 }}>
            <Box>
              <Text className="if-small-label">Sets</Text>
              <TextInput
                type="number"
                value={exercise.sets || ''}
                onChange={(e) => onUpdateSets(index, Number(e.currentTarget.value) || 0)}
                size="sm"
                classNames={{ input: 'if-control-input' }}
                disabled={disabled}
                data-testid={`exercise-sets-${index}`}
              />
            </Box>
            <Box>
              <Text className="if-small-label">Reps</Text>
              <TextInput
                type="number"
                value={exercise.reps || ''}
                onChange={(e) => onUpdate(index, 'reps', Number(e.currentTarget.value) || 0)}
                size="sm"
                classNames={{ input: 'if-control-input' }}
                disabled={disabled}
                data-testid={`exercise-reps-${index}`}
              />
            </Box>
            <Box>
              <Text className="if-small-label">{unit}</Text>
              <TextInput
                type="number"
                value={exercise.kg !== null && exercise.kg !== undefined ? toDisplayUnit(exercise.kg, unit as 'kg' | 'lb') : ''}
                onChange={(e) => onUpdate(index, 'kg', e.currentTarget.value !== '' ? fromDisplayUnit(Number(e.currentTarget.value), unit as 'kg' | 'lb') : null)}
                size="sm"
                step={0.5}
                classNames={{ input: 'if-control-input' }}
                disabled={disabled}
                data-testid={`exercise-weight-${index}`}
                rightSection={setStatuses.includes('failed') ? (
                  <Tooltip label="Contains failed sets">
                    <AlertTriangle size={14} color="var(--mantine-color-red-6)" />
                  </Tooltip>
                ) : null}
              />
            </Box>
            <Box>
              <Text className="if-small-label">RPE</Text>
              <TextInput
                type="number"
                inputMode="decimal"
                step={0.5}
                value={exercise.rpe != null ? String(exercise.rpe) : ''}
                onChange={(e) => {
                  const raw = e.currentTarget.value
                  if (raw.trim() === '') { onUpdateRpe(index, null); return }
                  const parsed = Number(raw)
                  if (Number.isFinite(parsed)) onUpdateRpe(index, parsed)
                }}
                onBlur={(e) => {
                  const sanitized = sanitizeRpe(e.currentTarget.value)
                  onUpdateRpe(index, sanitized)
                }}
                placeholder="1-10"
                size="sm"
                classNames={{ input: 'if-control-input' }}
                disabled={disabled}
                data-testid={`exercise-rpe-${index}`}
              />
            </Box>
          </SimpleGrid>
        </Group>

        <Stack gap={6} mt="xs">
          {setData.map((set, setIndex) => {
            const linkedVideos = setVideos[setIndex] ?? []
            return (
              <Box key={setIndex} data-testid={`exercise-${index}-set-${setIndex + 1}`}>
                <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="xs">
                  <Group h={36} gap={6} wrap="nowrap">
                    <Text size="sm" c="dimmed">Set {setIndex + 1}</Text>
                  </Group>
                  <TextInput type="number" size="sm" classNames={{ input: 'if-control-input' }} value={set.reps ?? ''} onChange={(event) => onUpdateSet(index, setIndex, { reps: event.currentTarget.value === '' ? null : Number(event.currentTarget.value) })} disabled={disabled} aria-label={`Set ${setIndex + 1} reps`} />
                  <TextInput type="number" size="sm" step={0.5} classNames={{ input: 'if-control-input' }} value={set.kg === null ? '' : toDisplayUnit(set.kg, unit as 'kg' | 'lb')} onChange={(event) => onUpdateSet(index, setIndex, { kg: event.currentTarget.value === '' ? null : fromDisplayUnit(Number(event.currentTarget.value), unit as 'kg' | 'lb') })} disabled={disabled} aria-label={`Set ${setIndex + 1} weight`} />
                  <TextInput type="number" size="sm" step={0.5} classNames={{ input: 'if-control-input' }} value={set.rpe ?? ''} onChange={(event) => onUpdateSet(index, setIndex, { rpe: event.currentTarget.value === '' ? null : Number(event.currentTarget.value) })} disabled={disabled} aria-label={`Set ${setIndex + 1} RPE`} />
                </SimpleGrid>
                <Group gap="xs" mt={2}>
                  {linkedVideos.length > 0 && (
                    <Button size="compact-xs" variant="subtle" leftSection={<Film size={12} />} onClick={onShowVideos}>
                      {linkedVideos.length} video{linkedVideos.length === 1 ? '' : 's'}
                    </Button>
                  )}
                  {!disabled && (
                    <Button size="compact-xs" variant="subtle" color="gray" leftSection={<Plus size={12} />} onClick={() => onAddSetVideo(index, setIndex)} data-testid={`exercise-${index}-set-${setIndex + 1}-add-video`}>
                      Video
                    </Button>
                  )}
                </Group>
              </Box>
            )
          })}
        </Stack>
        
        <Box mt="xs">
          <Text className="if-small-label">Notes</Text>
          <Textarea
            value={exercise.notes || ''}
            onChange={(e) => onUpdate(index, 'notes', e.currentTarget.value)}
            placeholder="Exercise notes..."
            size="sm"
            autosize
            minRows={1}
            maxRows={4}
            className="if-exercise-notes"
            disabled={disabled}
            data-testid={`exercise-notes-${index}`}
          />
        </Box>

        {setStatuses.length > 0 && (
          <Box mt={6}>
            <Group gap={4} align="center" wrap="nowrap">
              <Text className="if-small-label" style={{ flexShrink: 0 }}>Sets</Text>
              <Box style={{ flex: 1, minWidth: 0, overflow: 'hidden' }}>
                {renderSetStatusControls(exercise, index)}
              </Box>
            </Group>
            {renderStatusBadges(exercise)}
          </Box>
        )}
      </Box>
    </Paper>
  )
}

export default function SessionDrawer({
  isOpen,
  onClose,
  sessionArrayIndex,
  mode = 'drawer',
  readOnly: readOnlyProp,
  onSaveSuccess,
  onDeleteSuccess,
}: SessionDrawerProps) {
  const { readOnly: authReadOnly } = useAuth('sessions')
  const readOnly = readOnlyProp ?? authReadOnly
  const version = useProgramStore(s => s.version)
  const persistSession = useProgramStore(s => s.persistSession)
  const deleteSession = useProgramStore(s => s.deleteSession)
  const phases = useProgramStore(s => s.program?.phases)
  const unit = useSettingsStore(s => s.unit)
  const pushToast = useUiStore(s => s.pushToast)
  const [baseline, setBaseline] = useState<Session | null>(null)
  const [localSession, setLocalSession] = useState<Session | null>(null)
  const [originalDate, setOriginalDate] = useState<string>('')
  const [hasChanges, setHasChanges] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [lastSavedAt, setLastSavedAt] = useState<Date | null>(null)
  const [showVideoUpload, setShowVideoUpload] = useState(false)
  const [videoUploadPreset, setVideoUploadPreset] = useState<{ exerciseName: string; setNumber: number } | null>(null)
  const [discardIntent, setDiscardIntent] = useState<'reset' | 'close' | null>(null)
  const [glossary, setGlossary] = useState<GlossaryExercise[]>([])
  const [showNotesHelper, setShowNotesHelper] = useState(false)
  const [autoRegExerciseIndex, setAutoRegExerciseIndex] = useState<number | null>(null)
  const [failedReasonTarget, setFailedReasonTarget] = useState<{ exerciseIndex: number; setIndex: number } | null>(null)
  const [failedReasonDraft, setFailedReasonDraft] = useState<FailedSetReason[]>([])
  const [toolkitExercise, setToolkitExercise] = useState<{
    name: string
    targetKg: number | null
    reps: number | null
    isBarbell: boolean
  } | null>(null)
  const savedDateRef = useRef('')
  const draftKeyRef = useRef('')
  const draftPartitionRef = useRef('')
  const draftWriteRef = useRef<Promise<Draft<Session> | undefined>>(Promise.resolve(undefined))
  const changeVersionRef = useRef(0)
  const latestSaveRef = useRef<{ session: Session; version: number; notify: boolean; close: boolean; draftKey: string; partition: string; lookupDate: string } | null>(null)
  const saveInFlightRef = useRef(false)
  const flushRef = useRef<Promise<void>>(Promise.resolve())
  const revisionRef = useRef(0)
  const savedSessionRef = useRef<Session | null>(null)
  const savedAnythingRef = useRef(false)
  const pendingSaveRef = useRef(false)

  const markChanged = () => {
    changeVersionRef.current += 1
    setHasChanges(true)
  }

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
      setLocalSession((prev) => {
        if (!prev) return prev
        const items = prev.exercises
        const dragIds = items.map((exercise, index) => exerciseDragId(exercise, index))
        const oldIndex = dragIds.findIndex((id) => id === active.id)
        const newIndex = dragIds.findIndex((id) => id === over.id)
        if (oldIndex < 0 || newIndex < 0) return prev
        const nextExercises = arrayMove(items, oldIndex, newIndex)
        return { ...prev, exercises: nextExercises }
      })
      markChanged()
    }
  }

  useEffect(() => {
    fetchGlossary()
      .then((exercises) => setGlossary(exercises))
      .catch(() => {})
  }, [])

  const glossaryNames = useMemo(() => Array.from(new Set(glossary.map((e) => e.name))).sort(), [glossary])
  const glossaryLookup = useMemo(() => {
    const lookup = new Map<string, GlossaryExercise>()
    for (const exercise of glossary) {
      lookup.set(normalizeExerciseName(exercise.name), exercise)
    }
    return lookup
  }, [glossary])

  useEffect(() => {
    const program = useProgramStore.getState().program
    const session = program?.sessions[sessionArrayIndex]
    if (session) {
      revisionRef.current = program?.meta.revision ?? 0
      savedSessionRef.current = session
      let active = true
      const partition = requestPartition()
      const sessionId = session.id || ''
      setLocalSession(null)
      setBaseline(session)
      const clone = JSON.parse(JSON.stringify(session)) as Session
      // Pre-populate exercises from planned_exercises for incomplete sessions
      if (!clone.completed && clone.exercises.length === 0 && (clone.planned_exercises?.length ?? 0) > 0) {
        clone.exercises = clone.planned_exercises!.map(pe => ({
          name: pe.name,
          sets: pe.sets,
          reps: pe.reps,
          kg: pe.kg,
          notes: '',
          failed_sets: Array(pe.sets).fill(false),
          set_statuses: Array(pe.sets).fill('pending'),
          failed_set_reasons: Array.from({ length: pe.sets }, () => []),
        }))
      }
      clone.exercises = clone.exercises.map((ex) => ({
        ...withSetStatusFields(ex, clone.completed),
        id: ex.id || `ex-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      }))
      const draftKey = sessionId ? sessionDraftKey(version, sessionId) : ''
      const legacyKey = sessionId ? legacySessionDraftKey(version, session.date, sessionArrayIndex) : ''
      draftKeyRef.current = draftKey
      draftPartitionRef.current = partition
      void Promise.all([
        draftKey ? readDraft<Session>(draftKey, partition) : Promise.resolve(undefined),
        legacyKey ? readDraft<Session>(legacyKey, partition) : Promise.resolve(undefined),
      ]).then(([draft, legacyDraft]) => {
        if (!active || requestPartition() !== partition) return
        const legacy = legacyDraft?.value?.id === sessionId && legacyDraft.value.date === session.date ? legacyDraft : undefined
        const restored = draft?.value?.id === sessionId ? draft : legacy
        if (legacy && !draft && draftKey) {
          const migration = draftWriteRef.current.then(() => saveDraft(draftKey, legacy.value, partition))
          draftWriteRef.current = migration.catch(() => undefined)
          void migration.then(() => removeDraftIfMatch(legacyKey, legacy, partition)).catch(() => {})
        }
        setLocalSession(restored ? {
          ...restored.value,
          exercises: restored.value.exercises.map((ex) => ({
            ...withSetStatusFields(ex, restored.value.completed),
            id: ex.id || `ex-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
          })),
        } : clone)
        setOriginalDate(session.date)
        savedDateRef.current = session.date
        changeVersionRef.current = restored ? 1 : 0
        setHasChanges(Boolean(restored))
        setLastSavedAt(null)
      }).catch(() => {
        if (!active || requestPartition() !== partition) return
        setLocalSession(clone)
        setOriginalDate(session.date)
        savedDateRef.current = session.date
        changeVersionRef.current = 0
        setHasChanges(false)
        setLastSavedAt(null)
      })
      return () => { active = false }
    }
  }, [version, sessionArrayIndex])

  useEffect(() => {
    if (!localSession || !hasChanges || !draftKeyRef.current) return
    const key = draftKeyRef.current
    const partition = draftPartitionRef.current
    const write = draftWriteRef.current.then(() => saveDraft(key, localSession, partition))
    draftWriteRef.current = write.catch(() => undefined)
  }, [hasChanges, localSession])

  const autoSaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const handleSaveRef = useRef<((notify?: boolean, closeOnSuccess?: boolean) => Promise<void>) | null>(null)

  useEffect(() => {
    if (readOnly || !hasChanges || !localSession) return
    if (autoSaveTimerRef.current) {
      clearTimeout(autoSaveTimerRef.current)
    }
    pendingSaveRef.current = true
    autoSaveTimerRef.current = setTimeout(() => {
      pendingSaveRef.current = false
      void handleSaveRef.current?.(false, false)
    }, 1500)
    return () => {
      if (autoSaveTimerRef.current) {
        clearTimeout(autoSaveTimerRef.current)
        autoSaveTimerRef.current = null
      }
    }
  }, [hasChanges, localSession])

  useEffect(() => () => {
    const pending = pendingSaveRef.current ? handleSaveRef.current?.(false, false) : undefined
    void Promise.resolve(pending).then(() => flushRef.current).finally(() => {
      if (!savedAnythingRef.current) return
      const { loadProgram, version: currentVersion } = useProgramStore.getState()
      void loadProgram(currentVersion)
    })
  }, [])

  useEffect(() => {
    if (!hasChanges && !isSaving) return

    const handleBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault()
      event.returnValue = ''
    }

    window.addEventListener('beforeunload', handleBeforeUnload)
    return () => window.removeEventListener('beforeunload', handleBeforeUnload)
  }, [hasChanges, isSaving])

  const phaseColorValue = baseline && phases ? phaseColor(baseline.phase, phases) : 'var(--mantine-color-gray-6)'

  if (!baseline || !localSession) return null
  const wellness = localSession.wellness

  const enqueueDraft = (value: Session, key: string, partition: string) => {
    const write = draftWriteRef.current.then(() => saveDraft(key, value, partition))
    draftWriteRef.current = write.catch(() => undefined)
    return write
  }

  const flushLatestSave = async () => {
    if (saveInFlightRef.current) return flushRef.current
    const flush = runSaveQueue()
    flushRef.current = flush
    return flush
  }

  const runSaveQueue = async () => {
    saveInFlightRef.current = true
    setIsSaving(true)
    let shouldNotify = false
    let shouldClose = false

    try {
      while (latestSaveRef.current) {
        const job = latestSaveRef.current
        latestSaveRef.current = null
        shouldNotify = shouldNotify || job.notify
        shouldClose = shouldClose || job.close

        const lookupDate = job.lookupDate
        const draft = job.draftKey ? await enqueueDraft(job.session, job.draftKey, job.partition) : undefined
        const saved = await persistSession(lookupDate, sessionArrayIndex, job.session, revisionRef.current)
        revisionRef.current = saved.revision ?? revisionRef.current
        savedSessionRef.current = saved
        savedAnythingRef.current = true
        if (draft) await removeDraftIfMatch(job.draftKey, draft, job.partition)
        savedDateRef.current = job.session.date

        if (job.version === changeVersionRef.current && !latestSaveRef.current) {
          setOriginalDate(job.session.date)
          setHasChanges(false)
          setLastSavedAt(new Date())
        }
      }

      if (shouldNotify) {
        pushToast({ message: 'Session saved successfully', type: 'success' })
      }
      if (shouldClose) {
        if (onSaveSuccess) {
          onSaveSuccess()
        } else {
          onClose()
        }
      }
    } catch (err) {
      console.error(err)
      setHasChanges(true)
      setLastSavedAt(null)
      pushToast({
        message: shouldNotify ? 'Failed to save session' : 'Auto-save failed; session has unsaved changes',
        type: 'error',
      })
    } finally {
      saveInFlightRef.current = false
      setIsSaving(false)
    }
  }

  const handleSave = async (notify = true, closeOnSuccess = mode === 'drawer' && notify) => {
    const rpeError = validateRpeValues()
    if (rpeError) {
      pushToast({ message: rpeError, type: 'error' })
      return
    }

    if (autoSaveTimerRef.current) {
      clearTimeout(autoSaveTimerRef.current)
      autoSaveTimerRef.current = null
    }

    try {
      const sessionToSave = finalizeSessionForSave(localSession)
      latestSaveRef.current = {
        session: sessionToSave,
        version: changeVersionRef.current,
        notify,
        close: closeOnSuccess,
        draftKey: draftKeyRef.current,
        partition: draftPartitionRef.current,
        lookupDate: savedDateRef.current || originalDate || sessionToSave.date,
      }
      await flushLatestSave()
    } catch (err) {
      console.error(err)
      setHasChanges(true)
      setLastSavedAt(null)
      pushToast({
        message: notify ? 'Failed to save session' : 'Auto-save failed; session has unsaved changes',
        type: 'error',
      })
    }
  }

  handleSaveRef.current = handleSave

  const handleDiscard = () => {
    const clone = JSON.parse(JSON.stringify(savedSessionRef.current ?? baseline)) as Session
    clone.exercises = clone.exercises.map((ex) => withSetStatusFields(ex, clone.completed))
    pendingSaveRef.current = false
    setLocalSession(clone)
    changeVersionRef.current = 0
    setHasChanges(false)
  }

  const confirmDiscard = () => {
    if (discardIntent === 'reset') {
      handleDiscard()
    } else if (discardIntent === 'close') {
      handleDiscard()
      onClose()
    }
    setDiscardIntent(null)
  }

  const handleCloseWithCheck = () => {
    if (hasChanges) {
      setDiscardIntent('close')
    } else {
      onClose()
    }
  }

  const updateExercise = (index: number, field: keyof Exercise, value: unknown) => {
    setLocalSession((prev) => {
      if (!prev) return prev
      const exercises = [...prev.exercises]
      exercises[index] = { ...exercises[index], [field]: value }
      return { ...prev, exercises }
    })
    markChanged()
  }

  const addExercise = () => {
    setLocalSession((prev) => {
      if (!prev) return prev
      return {
        ...prev,
        exercises: [
          ...prev.exercises,
          {
            id: `ex-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
            name: '',
            sets: 3,
            reps: 5,
            kg: null,
            notes: '',
            failed_sets: [false, false, false],
            set_statuses: ['pending', 'pending', 'pending'],
            failed_set_reasons: [[], [], []],
          },
        ],
      }
    })
    markChanged()
  }

  const removeExercise = (index: number) => {
    setLocalSession((prev) => {
      if (!prev) return prev
      const exercises = prev.exercises.filter((_, i) => i !== index)
      return { ...prev, exercises }
    })
    markChanged()
  }

  const updateSetStatus = (exerciseIndex: number, setIndex: number, status: SetStatus) => {
    setLocalSession((prev) => {
      if (!prev) return prev
      const exercises = prev.exercises.map((ex, i) => {
        if (i !== exerciseIndex) return ex
        const statuses = normalizeSetStatuses(ex, prev.completed)
        statuses[setIndex] = status
        return withSetStatusFields({ ...ex, set_statuses: statuses }, prev.completed)
      })
      return { ...prev, exercises }
    })
    markChanged()
  }

  const openFailedSetReasons = (exerciseIndex: number, setIndex: number, exerciseOverride?: Exercise) => {
    const exercise = exerciseOverride || localSession.exercises[exerciseIndex]
    const statuses = normalizeSetStatuses(exercise, localSession.completed)
    setFailedReasonDraft(normalizeFailedSetReasons(exercise, statuses)[setIndex] || [])
    setFailedReasonTarget({ exerciseIndex, setIndex })
  }

  const handleSetStatusSelection = (exerciseIndex: number, setIndex: number, status: SetStatus) => {
    const exercise = localSession.exercises[exerciseIndex]
    updateSetStatus(exerciseIndex, setIndex, status)
    if (status === 'failed' && exercise) {
      const statuses = normalizeSetStatuses(exercise, localSession.completed)
      statuses[setIndex] = 'failed'
      openFailedSetReasons(exerciseIndex, setIndex, { ...exercise, set_statuses: statuses })
    }
  }

  const updateFailedSetReasons = (exerciseIndex: number, setIndex: number, reasons: FailedSetReason[]) => {
    const uniqueReasons = reasons.filter((reason, index) =>
      FAILED_SET_REASON_VALUES.has(reason) && reasons.indexOf(reason) === index
    )
    setLocalSession((prev) => {
      if (!prev) return prev
      const exercises = prev.exercises.map((ex, i) => {
        if (i !== exerciseIndex) return ex
        const statuses = normalizeSetStatuses(ex, prev.completed)
        statuses[setIndex] = 'failed'
        const failed_set_reasons = normalizeFailedSetReasons({ ...ex, set_statuses: statuses }, statuses)
        failed_set_reasons[setIndex] = uniqueReasons
        return withSetStatusFields({ ...ex, set_statuses: statuses, failed_set_reasons }, prev.completed)
      })
      return { ...prev, exercises }
    })
    markChanged()
  }

  const saveFailedSetReasons = () => {
    if (!failedReasonTarget) return
    updateFailedSetReasons(failedReasonTarget.exerciseIndex, failedReasonTarget.setIndex, failedReasonDraft)
    setFailedReasonTarget(null)
    setFailedReasonDraft([])
  }

  const updateSetsWithResize = (index: number, newSets: number) => {
    setLocalSession((prev) => {
      if (!prev) return prev
      const exercises = prev.exercises.map((ex, i) => {
        if (i !== index) return ex
        const prevStatuses = normalizeSetStatuses(ex, prev.completed)
        const prevReasons = normalizeFailedSetReasons(ex, prevStatuses)
        const previousData = normalizeSetData(ex)
        const fallbackStatus: SetStatus = prev.completed ? 'completed' : 'pending'
        const set_statuses: SetStatus[] = []
        const failed_set_reasons: FailedSetReason[][] = []
        const sets_data: ExerciseSetData[] = []
        for (let s = 0; s < newSets; s++) {
          if (s < prevStatuses.length) {
            set_statuses.push(prevStatuses[s])
            failed_set_reasons.push(prevReasons[s] ?? [])
            sets_data.push(previousData[s])
          } else {
            set_statuses.push(fallbackStatus)
            failed_set_reasons.push([])
            sets_data.push({ reps: ex.reps || null, kg: ex.kg, rpe: ex.rpe ?? null })
          }
        }
        const failed_sets = set_statuses.map((status) => status === 'failed')
        return withSetStatusFields(
          { ...ex, sets: newSets, set_statuses, failed_sets, failed_set_reasons, sets_data },
          prev.completed,
        )
      })
      return { ...prev, exercises }
    })
    markChanged()
  }

  const updateExerciseRpe = (index: number, rpe: number | null) => {
    setLocalSession((prev) => {
      if (!prev) return prev
      const exercises = [...prev.exercises]
      exercises[index] = { ...exercises[index], rpe }
      return { ...prev, exercises }
    })
    markChanged()
  }

  const updateExerciseSet = (exerciseIndex: number, setIndex: number, patch: Partial<ExerciseSetData>) => {
    setLocalSession((prev) => {
      if (!prev) return prev
      const exercises = prev.exercises.map((exercise, index) => {
        if (index !== exerciseIndex) return exercise
        const sets_data = normalizeSetData(exercise).map((set, currentIndex) => currentIndex === setIndex ? { ...set, ...patch } : set)
        const first = sets_data[0]
        return { ...exercise, sets_data, reps: first?.reps ?? exercise.reps, kg: first?.kg ?? exercise.kg, rpe: first?.rpe ?? exercise.rpe }
      })
      return { ...prev, exercises }
    })
    markChanged()
  }

  const openSetVideoUpload = (exerciseIndex: number, setIndex: number) => {
    if (!localSession) return
    setVideoUploadPreset({
      exerciseName: localSession.exercises[exerciseIndex].name,
      setNumber: cumulativeSetNumber(localSession.exercises, exerciseIndex, setIndex),
    })
    setShowVideoUpload(true)
  }

  const validateRpeValues = (): string | null => {
    for (let i = 0; i < localSession.exercises.length; i++) {
      const rpe = localSession.exercises[i].rpe
      if (rpe != null && (rpe < 1 || rpe > 10)) {
        return `Exercise "${localSession.exercises[i].name || 'unnamed'}" has RPE ${rpe}, must be 1-10.`
      }
      if (rpe != null && (rpe * 2) % 1 !== 0) {
        return `Exercise "${localSession.exercises[i].name || 'unnamed'}" has RPE ${rpe}, must be in 0.5 increments.`
      }
    }
    if (localSession.session_rpe != null && (localSession.session_rpe < 1 || localSession.session_rpe > 10)) {
      return `Session RPE ${localSession.session_rpe}, must be 1-10.`
    }
    if (localSession.session_rpe != null && (localSession.session_rpe * 2) % 1 !== 0) {
      return `Session RPE ${localSession.session_rpe}, must be in 0.5 increments.`
    }
    return null
  }

  const updateDate = (newDate: string) => {
    if (newDate && newDate !== localSession.date) {
      const newDay = getDayOfWeek(newDate)
      setLocalSession((prev) => prev ? { ...prev, date: newDate, day: newDay } : prev)
      markChanged()
    }
  }

  const toggleComplete = () => {
    setLocalSession((prev) => {
      if (!prev) return prev
      const completed = !prev.completed
      return { ...prev, completed, status: completed ? 'completed' : 'planned' }
    })
    markChanged()
  }

  const updateRpe = (rpe: number | null) => {
    setLocalSession((prev) => prev ? { ...prev, session_rpe: rpe } : prev)
    markChanged()
  }

  const updateBodyWeight = (kg: number | null) => {
    setLocalSession((prev) => prev ? { ...prev, body_weight_kg: kg } : prev)
    markChanged()
  }

  const updateNotes = (notes: string) => {
    setLocalSession((prev) => prev ? { ...prev, session_notes: notes } : prev)
    markChanged()
  }

  const setWellnessMode = (enabled: boolean) => {
    setLocalSession((prev) => {
      if (!prev) return prev
      if (!enabled) {
        const next = { ...prev }
        delete next.wellness
        return next
      }
      return { ...prev, wellness: createDefaultWellness(prev.wellness) }
    })
    markChanged()
  }

  const updateWellness = (field: keyof Omit<SessionWellness, 'recorded_at'>, value: number) => {
    setLocalSession((prev) => {
      if (!prev) return prev
      const current = prev.wellness ?? createDefaultWellness()
      return {
        ...prev,
        wellness: {
          ...current,
          [field]: clampWellnessScore(value),
          recorded_at: new Date().toISOString(),
        },
      }
    })
    markChanged()
  }

  const openToolkitForExercise = (exercise: Exercise) => {
    const match = glossaryLookup.get(normalizeExerciseName(exercise.name))
    setToolkitExercise({
      name: exercise.name,
      targetKg: exercise.kg,
      reps: exercise.reps,
      isBarbell: match ? ['barbell', 'hex_bar'].includes(match.equipment) : true,
    })
  }

  const renderMobileExerciseMenu = (exercise: Exercise, exerciseIndex: number) => (
    <Menu withinPortal position="bottom-end" shadow="md" width={220}>
      <Menu.Target>
        <ActionIcon
          hiddenFrom="sm"
          variant="subtle"
          color="gray"
          size="md"
          style={{ minHeight: 44, minWidth: 44 }}
          title="Exercise actions"
          aria-label={`Exercise actions for ${exercise.name || 'unnamed'}`}
          disabled={readOnly}
        >
          <MoreHorizontal size={18} />
        </ActionIcon>
      </Menu.Target>
      <Menu.Dropdown>
        {/* Safe actions grouped at top — BUG-1.1 */}
        <Menu.Item
          leftSection={<Bot size={16} />}
          onClick={() => setAutoRegExerciseIndex(exerciseIndex)}
          styles={{ item: { minHeight: 44, paddingInline: 12 } }}
        >
          Auto-regulation
        </Menu.Item>
        <Menu.Item
          leftSection={<Calculator size={16} />}
          onClick={() => openToolkitForExercise(exercise)}
          styles={{ item: { minHeight: 44, paddingInline: 12 } }}
        >
          Plate calculator
        </Menu.Item>
        <Menu.Divider />
        {/* Destructive action separated + ordered away + confirm — BUG-1.1 */}
        <Menu.Item
          color="red"
          leftSection={<Trash2 size={16} />}
          styles={{ item: { minHeight: 44, paddingInline: 12 } }}
          onClick={() => {
            const label = exercise.name || 'this exercise'
            if (window.confirm(`Delete "${label}"? This set's logged state will be removed. This cannot be undone.`)) {
              removeExercise(exerciseIndex)
            }
          }}
        >
          Delete exercise
        </Menu.Item>
      </Menu.Dropdown>
    </Menu>
  )

  const renderDesktopExerciseActions = (exercise: Exercise, exerciseIndex: number, iconSize = 16) => (
    <>
      <ActionIcon
        visibleFrom="sm"
        variant="subtle"
        color="grape"
        size="md"
        style={{ minHeight: 44, minWidth: 44 }}
        onClick={() => setAutoRegExerciseIndex(exerciseIndex)}
        title="Auto-regulation"
        disabled={readOnly}
        data-testid={`exercise-autoreg-${exerciseIndex}`}
      >
        <Bot size={iconSize} />
      </ActionIcon>
      <ActionIcon
        visibleFrom="sm"
        variant="subtle"
        color="blue"
        size="md"
        style={{ minHeight: 44, minWidth: 44 }}
        onClick={() => openToolkitForExercise(exercise)}
        title="Plate calculator"
        disabled={readOnly}
        data-testid={`exercise-toolkit-${exerciseIndex}`}
      >
        <Calculator size={iconSize} />
      </ActionIcon>
    </>
  )

  const statusIcon = (status: SetStatus, size = 14) => {
    if (status === 'completed') return <CheckCircle2 size={size} />
    if (status === 'failed') return <XCircle size={size} />
    if (status === 'skipped') return <Minus size={size} />
    return <Circle size={size} />
  }

  const statusDotClass = (status: SetStatus) => {
    if (status === 'completed') return 'if-set-dot if-set-dot-completed'
    if (status === 'failed') return 'if-set-dot if-set-dot-failed'
    if (status === 'skipped') return 'if-set-dot if-set-dot-skipped'
    return 'if-set-dot'
  }

  const renderSetStatusControls = (exercise: Exercise, exerciseIndex: number, size: 'xs' | 'sm' = 'xs') => {
    const statuses = normalizeSetStatuses(exercise, localSession.completed)
    const failedReasons = normalizeFailedSetReasons(exercise, statuses)
    return (
      <Group gap={2} wrap="wrap" style={{ flexShrink: 0 }}>
        {statuses.map((status, setIndex) => {
          const reasonLabel = failedReasonLabels(failedReasons[setIndex] || [])
          const tooltip = reasonLabel
            ? `Set ${setIndex + 1}: ${SET_STATUS_META[status].label} - ${reasonLabel}`
            : `Set ${setIndex + 1}: ${SET_STATUS_META[status].label}`
          return (
            <Menu key={setIndex} withinPortal position="bottom-start" shadow="md" width={200}>
              <Menu.Target>
                <Tooltip label={tooltip}>
                  <ActionIcon
                    size={40}
                    radius="xl"
                    variant="transparent"
                    className={statusDotClass(status)}
                    disabled={readOnly}
                    data-testid={`set-status-${exerciseIndex}-${setIndex}`}
                    aria-label={`Set ${setIndex + 1} status: ${SET_STATUS_META[status].label}`}
                  >
                    {statusIcon(status, size === 'xs' ? 15 : 17)}
                  </ActionIcon>
                </Tooltip>
              </Menu.Target>
              <Menu.Dropdown>
                {(Object.keys(SET_STATUS_META) as SetStatus[]).map((option) => (
                  <Menu.Item
                    key={option}
                    leftSection={statusIcon(option)}
                    color={SET_STATUS_META[option].color}
                    onClick={() => handleSetStatusSelection(exerciseIndex, setIndex, option)}
                    styles={{ item: { minHeight: 44, paddingInline: 12 } }}
                  >
                    {SET_STATUS_META[option].label}
                  </Menu.Item>
                ))}
                {status === 'failed' && (
                  <>
                    <Menu.Divider />
                    <Menu.Item
                      onClick={() => openFailedSetReasons(exerciseIndex, setIndex)}
                      styles={{ item: { minHeight: 44, paddingInline: 12 } }}
                    >
                      Edit reasons
                    </Menu.Item>
                  </>
                )}
              </Menu.Dropdown>
            </Menu>
          )
        })}
      </Group>
    )
  }

  const renderStatusBadges = (exercise: Exercise) => {
    const counts = statusCounts(exercise)
    return (
      <Group gap={4}>
        {(['completed', 'failed', 'skipped'] as SetStatus[]).map((status) =>
          counts[status] > 0 ? (
            <Badge key={status} size="xs" variant="light" color={SET_STATUS_META[status].color}>
              {counts[status]} {SET_STATUS_META[status].label}
            </Badge>
          ) : null
        )}
      </Group>
    )
  }

  const appendReasoningNote = (notes: string | undefined, reasoningNote: string) => {
    const note = reasoningNote.trim()
    if (!note) return notes || ''
    const prefix = `Auto-regulation ${new Date().toISOString().slice(0, 10)}: ${note}`
    return [notes || '', prefix].filter(Boolean).join('\n')
  }

  const exercisePrescriptionChanged = (before: Exercise, after: Exercise) => (
    before.name !== after.name ||
    before.kg !== after.kg ||
    before.reps !== after.reps
  )

  const buildAutoRegulatedSession = (
    baseSession: Session,
    proposedExercises: Exercise[],
    reasoningNote: string,
    exerciseIndex: number
  ): Session => {
    const currentExercise = baseSession.exercises[exerciseIndex]
    const proposedExercise = proposedExercises[exerciseIndex]
    if (!currentExercise || !proposedExercise) return baseSession

    const nextExercises = proposedExercises.map((exercise) =>
      withSetStatusFields({ ...exercise, notes: exercise.notes || '' }, baseSession.completed)
    )
    const currentStatuses = normalizeSetStatuses(currentExercise, baseSession.completed)
    const currentReasons = normalizeFailedSetReasons(currentExercise, currentStatuses)
    const lockedSets = currentStatuses
      .map((status, index) => ({ status, reasons: currentReasons[index] || [] }))
      .filter((entry) => entry.status === 'completed' || entry.status === 'failed')
    const lockedStatuses = lockedSets.map((entry) => entry.status)
    const lockedReasons = lockedSets.map((entry) => entry.status === 'failed' ? entry.reasons : [])
    const changedLockedWork = lockedStatuses.length > 0 && exercisePrescriptionChanged(currentExercise, proposedExercise)

    if (changedLockedWork) {
      const lockedExercise = withSetStatusFields({
        ...currentExercise,
        sets: lockedStatuses.length,
        set_statuses: lockedStatuses,
        failed_set_reasons: lockedReasons,
        notes: appendReasoningNote(currentExercise.notes, reasoningNote),
      }, baseSession.completed)
      const remainingSets = Math.max(0, Number(proposedExercise.sets || 0) - lockedStatuses.length)
      const proposedStatuses = normalizeSetStatuses(proposedExercise)
      const proposedReasons = normalizeFailedSetReasons(proposedExercise, proposedStatuses)
      const remainingStatuses = proposedStatuses.slice(lockedStatuses.length, lockedStatuses.length + remainingSets)
      const remainingReasons = proposedReasons.slice(lockedStatuses.length, lockedStatuses.length + remainingSets)
      while (remainingStatuses.length < remainingSets) remainingStatuses.push('pending')
      while (remainingReasons.length < remainingSets) remainingReasons.push([])
      const replacement = [lockedExercise]
      if (remainingSets > 0) {
        replacement.push(withSetStatusFields({
          ...proposedExercise,
          sets: remainingSets,
          set_statuses: remainingStatuses,
          failed_set_reasons: remainingReasons,
          notes: appendReasoningNote(proposedExercise.notes, reasoningNote),
        }, baseSession.completed))
      }
      nextExercises.splice(exerciseIndex, 1, ...replacement)
    } else {
      nextExercises[exerciseIndex] = withSetStatusFields({
        ...nextExercises[exerciseIndex],
        notes: appendReasoningNote(nextExercises[exerciseIndex].notes, reasoningNote),
      }, baseSession.completed)
    }

    return { ...baseSession, exercises: nextExercises }
  }

  const applyAutoRegulation = async (proposedExercises: Exercise[], reasoningNote: string) => {
    if (autoRegExerciseIndex === null) return
    const nextSession = finalizeSessionForSave(buildAutoRegulatedSession(
      localSession,
      proposedExercises,
      reasoningNote,
      autoRegExerciseIndex
    ))
    changeVersionRef.current += 1
    setHasChanges(true)
    setLocalSession(nextSession)
    latestSaveRef.current = {
      session: nextSession,
      version: changeVersionRef.current,
      notify: false,
      close: false,
      draftKey: draftKeyRef.current,
      partition: draftPartitionRef.current,
      lookupDate: savedDateRef.current || originalDate || nextSession.date,
    }
    await flushLatestSave()
    pushToast({ message: 'Auto-regulation applied', type: 'success' })
  }

  const editorContent = (
    <Stack
      gap={10}
      pb={mode === 'page' ? 'calc(120px + env(safe-area-inset-bottom, 0px))' : undefined}
      className="if-mock-page"
      style={{ maxWidth: mode === 'page' ? 680 : '100vw', margin: mode === 'page' ? '0 auto' : undefined, overflowX: 'hidden' }}
      data-testid="session-detail"
    >
      <Box
        className="if-mock-card if-mock-card-compact"
        style={{
          alignItems: 'center',
          display: 'flex',
          gap: 12,
          zIndex: 20,
          minHeight: 48,
          position: mode === 'page' ? 'sticky' : 'static',
          top: 0,
        }}
      >
        <button className="if-mock-button" onClick={handleCloseWithCheck} title={mode === 'page' ? 'Back' : 'Close'} style={{ minWidth: 34, padding: '4px 8px' }}>
          {mode === 'page' ? <ArrowLeft size={13} /> : <X size={13} />}
        </button>
        <span style={{ background: hasChanges ? 'var(--accent-blue)' : phaseColorValue, borderRadius: '50%', flexShrink: 0, height: 8, width: 8 }} title={hasChanges ? 'Unsaved changes' : localSession.phase?.name || 'Phase'} />
        <Box style={{ flex: 1, minWidth: 0 }}>
          <Group gap="xs" align="center" wrap="wrap">
            <DatePickerInput
              value={localSession.date}
              valueFormat="YYYY-MM-DD"
              onChange={(d) => {
                if (d) updateDate(d as string)
              }}
              size="xs"
              disabled={readOnly}
              data-testid="session-date"
              styles={{
                input: {
                  background: 'transparent',
                  border: '0',
                  color: 'var(--color-text-primary)',
                  fontFamily: 'var(--font-mono)',
                  fontSize: 14,
                  fontWeight: 500,
                  minHeight: 24,
                  padding: 0,
                  width: 104,
                },
              }}
            />
            <span className="if-mock-pill" style={{ background: 'var(--color-background-secondary)', borderColor: 'transparent', color: 'var(--color-text-secondary)', fontSize: 11 }}>
              {localSession.day}
            </span>
            {localSession.phase?.name && (
              <span className="if-mock-pill" style={{ background: `color-mix(in srgb, ${phaseColorValue} 22%, transparent)`, borderColor: 'transparent', color: phaseColorValue, fontSize: 11 }}>
                {localSession.phase.name}
              </span>
            )}
          </Group>
        </Box>
        <RestTimerHeaderButton />
      </Box>

      <Paper withBorder p={0} radius={10} className="if-card">
        <Box p="12px 16px">
          <Group justify="space-between" align="center" mb="sm">
            <Group gap="xs">
              <HeartPulse size={16} />
              <Text size="sm" fw={500}>Subjective wellness</Text>
            </Group>
            <SegmentedControl
              size="xs"
              value={localSession.wellness ? 'record' : 'skip'}
              onChange={(value) => setWellnessMode(value === 'record')}
              data={[
                { label: 'Skip', value: 'skip' },
                { label: 'Record', value: 'record' },
              ]}
              disabled={readOnly}
            />
          </Group>

          {wellness ? (
            <Stack gap="sm">
              {WELLNESS_FIELDS.map((field) => (
                <Box key={field.key}>
                  <Group justify="space-between" mb={4}>
                    <Text size="xs" c="dimmed">{field.label}</Text>
                    <Text size="xs" fw={500}>{wellness[field.key] ?? 3}/5</Text>
                  </Group>
                  <Slider
                    value={wellness[field.key]}
                    onChange={(value) => updateWellness(field.key, value)}
                    min={1}
                    max={5}
                    step={1}
                    marks={[
                      { value: 1, label: '1' },
                      { value: 2, label: '2' },
                      { value: 3, label: '3' },
                      { value: 4, label: '4' },
                      { value: 5, label: '5' },
                    ]}
                    color={field.key === 'soreness' || field.key === 'stress' ? 'orange' : 'blue'}
                    disabled={readOnly}
                  />
                </Box>
              ))}
              <Text size="xs" c="dimmed">
                Higher scores are better. Soreness and stress are inverted in readiness math.
              </Text>
            </Stack>
          ) : (
            <Text size="xs" c="dimmed">No wellness captured for this session.</Text>
          )}
        </Box>
        </Paper>

        <Paper withBorder p={0} radius={10} className="if-card">
          <Box p="12px 16px">
          <Group justify="space-between" align="center" mb="md">
            <Text size="sm" fw={500}>Workout</Text>
            <Button
              variant="light"
              onClick={addExercise}
              leftSection={<Plus size={16} />}
              disabled={readOnly}
              data-testid="session-add-exercise"
            >
              Add Exercise
            </Button>
          </Group>

          <Stack gap="sm">
          {/* Planned exercises reference */}
          {(localSession.planned_exercises?.length ?? 0) > 0 && (
            <Paper bg="var(--bg-elevated)" p="xs" radius="md" style={{ border: '1px solid var(--border-subtle)' }}>
              <Text size="xs" c="dimmed" fw={500} mb={4}>Planned</Text>
              <Group gap="md" wrap="wrap">
                {localSession.planned_exercises!.map((pe, i) => (
                  <Text key={i} size="xs" c="dimmed" span>
                    {pe.name} {pe.sets}x{pe.reps}{pe.kg !== null ? ` @${toDisplayUnit(pe.kg, unit as 'kg' | 'lb')}${unit}` : ''}
                  </Text>
                ))}
              </Group>
            </Paper>
          )}
          <Stack gap="xs">
            <DndContext
              sensors={sensors}
              collisionDetection={closestCenter}
              onDragEnd={handleDragEnd}
            >
              <SortableContext
                items={localSession.exercises.map(exerciseDragId)}
                strategy={verticalListSortingStrategy}
              >
                <Stack gap="sm">
                  {localSession.exercises.map((ex, i) => (
                    <SortableExerciseItem
                      key={exerciseDragId(ex, i)}
                      exercise={ex}
                      index={i}
                      onRemove={removeExercise}
                      onUpdate={updateExercise}
                      onUpdateSets={updateSetsWithResize}
                      onUpdateRpe={updateExerciseRpe}
                      onUpdateSet={updateExerciseSet}
                      setVideos={videosBySet(localSession.exercises, i, localSession.videos)}
                      onAddSetVideo={openSetVideoUpload}
                      onShowVideos={() => document.getElementById('session-videos')?.scrollIntoView({ behavior: 'smooth', block: 'start' })}
                      glossaryNames={glossaryNames}
                      unit={unit}
                      renderMobileMenu={renderMobileExerciseMenu}
                      renderDesktopActions={renderDesktopExerciseActions}
                      renderSetStatusControls={renderSetStatusControls}
                      renderStatusBadges={renderStatusBadges}
                      disabled={readOnly}
                    />
                  ))}
                </Stack>
              </SortableContext>
            </DndContext>
          </Stack>

          {/* Videos Section */}
          <Divider my="sm" />
          <Group justify="space-between" mb="sm" id="session-videos">
            <Group gap="xs">
              <Film size={16} />
              <Text size="sm" fw={500}>Videos</Text>
              {(localSession.videos?.length || 0) > 0 && (
                <Text size="xs" c="dimmed" span>({localSession.videos?.length})</Text>
              )}
            </Group>
              <Button
                size="xs"
                variant="default"
                onClick={() => { setVideoUploadPreset(null); setShowVideoUpload(true) }}
                leftSection={<Plus size={12} />}
                disabled={readOnly}
                data-testid="session-upload-video"
              >
              Upload
            </Button>
          </Group>

          {localSession.videos && localSession.videos.length > 0 ? (
            <VideoGrid
              session={localSession}
              onVideoUpdated={(video) => setLocalSession((prev) => prev ? {
                ...prev,
                videos: (prev.videos || []).map((item) => item.video_id === video.video_id ? video : item),
              } : prev)}
              onVideoRemoved={(videoId) => setLocalSession((prev) => prev ? {
                ...prev,
                videos: (prev.videos || []).filter((item) => item.video_id !== videoId),
              } : prev)}
            />
          ) : (
            <Text size="xs" c="dimmed" py="md">
              No videos uploaded for this session
            </Text>
          )}
          </Stack>
          </Box>
        </Paper>

        <Paper withBorder p={0} radius={10} className="if-card">
          <Box p="12px 16px">
          <Stack gap="sm">
            <Group justify="space-between">
              <Text size="sm" fw={500}>Session summary</Text>
              <Button
                size="xs"
                variant="light"
                leftSection={<Wand2 size={14} />}
                onClick={() => setShowNotesHelper(true)}
                disabled={readOnly}
                data-testid="session-notes-helper"
              >
                Help write notes
              </Button>
            </Group>
          <SimpleGrid cols={2} spacing="sm">
            <Box>
              <Text className="if-small-label">Session RPE</Text>
              <TextInput
                type="number"
                value={localSession.session_rpe || ''}
                onChange={(e) => {
                  const raw = e.currentTarget.value
                  const parsed = Number(raw)
                  if (raw.trim() === '' || !Number.isFinite(parsed)) { updateRpe(null); return }
                  updateRpe(parsed)
                }}
                onBlur={(e) => {
                  const sanitized = sanitizeRpe(e.currentTarget.value)
                  updateRpe(sanitized)
                }}
                placeholder="1-10"
                size="sm"
                classNames={{ input: 'if-control-input' }}
                step={0.5}
                disabled={readOnly}
                data-testid="session-rpe"
              />
            </Box>
            <Box>
              <Text className="if-small-label">Body Weight ({unit})</Text>
              <TextInput
                type="number"
                value={
                  localSession.body_weight_kg
                    ? toDisplayUnit(localSession.body_weight_kg, unit as 'kg' | 'lb')
                    : ''
                }
                onChange={(e) => updateBodyWeight(e.currentTarget.value !== '' ? fromDisplayUnit(Number(e.currentTarget.value), unit as 'kg' | 'lb') : null)}
                placeholder={unit}
                size="sm"
                classNames={{ input: 'if-control-input' }}
                step={0.1}
                disabled={readOnly}
                data-testid="session-body-weight"
              />
            </Box>
          </SimpleGrid>

          <Box>
            <Text className="if-small-label">Session Notes</Text>
            <Textarea
              value={localSession.session_notes || ''}
              onChange={(e) => updateNotes(e.currentTarget.value)}
              placeholder="How did the session feel?"
              autosize
              minRows={1}
              maxRows={mode === 'page' ? 4 : 6}
              size="sm"
              className="if-exercise-notes"
              disabled={readOnly}
              data-testid="session-notes"
            />
          </Box>
          </Stack>
          </Box>
        </Paper>

        <Stack gap="sm">
          <Button
            variant="default"
            color="red"
            onClick={async () => {
              if (confirm('Are you sure you want to delete this entire session? This cannot be undone.')) {
                await deleteSession(localSession.date, sessionArrayIndex, localSession.id)
                pushToast({ message: 'Session deleted successfully', type: 'success' })
                onClose()
                if (onDeleteSuccess) onDeleteSuccess()
              }
            }}
            leftSection={<Trash2 size={16} />}
            disabled={readOnly}
            data-testid="session-delete"
            fullWidth
            h={44}
            style={{
              background: 'var(--color-background-primary)',
              border: '0.5px solid var(--color-border-danger)',
              borderRadius: 'var(--border-radius-lg)',
              color: 'var(--color-text-danger)',
              fontWeight: 500,
            }}
          >
            Delete session
          </Button>
          <Group gap="sm" wrap="wrap" className="if-session-action-bar">
            <Text size="xs" c={hasChanges ? 'yellow' : 'dimmed'} style={{ alignSelf: 'center' }}>
              {isSaving ? 'Saving...' : hasChanges ? 'Unsaved changes' : lastSavedAt ? 'Saved' : 'No changes'}
            </Text>
            <Button
              variant="default"
              color="gray"
              h={44}
              onClick={() => setDiscardIntent('reset')}
              disabled={!hasChanges || isSaving || readOnly}
              leftSection={<RotateCcw size={16} />}
              data-testid="session-discard"
            >
              Discard
            </Button>
            <Button
              h={44}
              onClick={() => void handleSave()}
              disabled={!hasChanges || isSaving || readOnly}
              loading={isSaving}
              leftSection={<Save size={16} />}
              data-testid="session-save"
            >
              Save
            </Button>
            <Button
              h={44}
              variant={localSession.completed ? 'filled' : 'default'}
              onClick={toggleComplete}
              leftSection={<Check size={16} />}
              disabled={readOnly}
              data-testid="session-toggle-complete"
            >
              {localSession.completed ? 'Done' : 'Mark Done'}
            </Button>
          </Group>
        </Stack>
      </Stack>
  )

  return (
    <>
      {mode === 'drawer' ? (
        <Drawer
          opened={isOpen}
          onClose={handleCloseWithCheck}
          position="right"
          size="xl"
          withCloseButton={false}
          overlayProps={{ backgroundOpacity: 0.25 }}
          styles={{
            inner: {
              overflow: 'hidden',
            },
            content: {
              maxWidth: '100vw',
              overflowX: 'hidden',
            },
            body: {
              overflowX: 'hidden',
            },
          }}
        >
          {editorContent}
        </Drawer>
      ) : (
        <Box>
          {editorContent}
        </Box>
      )}

      <Modal
        opened={discardIntent !== null}
        onClose={() => setDiscardIntent(null)}
        title="Discard changes?"
        centered
      >
        <Stack gap="md">
          <Text size="sm">
            {discardIntent === 'close'
              ? 'You have unsaved changes. Discard them and leave this page?'
              : 'Discard all unsaved changes to this session?'}
          </Text>
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setDiscardIntent(null)}>Cancel</Button>
            <Button color="red" onClick={confirmDiscard}>Discard</Button>
          </Group>
        </Stack>
      </Modal>

      {/* Video Upload Modal */}
      <VideoUploadModal
        session={localSession || baseline}
        isOpen={showVideoUpload}
        initialExerciseName={videoUploadPreset?.exerciseName}
        initialSetNumber={videoUploadPreset?.setNumber}
        onClose={() => { setShowVideoUpload(false); setVideoUploadPreset(null) }}
        onUploaded={(video: SessionVideo) => {
          setLocalSession((prev) => {
            if (!prev) return prev
            const updated = {
              ...prev,
              videos: [...(prev.videos || []), video],
            }
            return updated
          })
          setShowVideoUpload(false)
        }}
      />

      <SessionNotesHelperModal
        opened={showNotesHelper}
        onClose={() => setShowNotesHelper(false)}
        version={version}
        session={localSession}
        sessionIndex={sessionArrayIndex}
        onInsert={(notes) => updateNotes(notes)}
      />

      <AutoRegulationModal
        opened={autoRegExerciseIndex !== null}
        onClose={() => setAutoRegExerciseIndex(null)}
        version={version}
        session={localSession}
        sessionIndex={sessionArrayIndex}
        exerciseIndex={autoRegExerciseIndex}
        onApply={applyAutoRegulation}
      />

      <Modal
        opened={failedReasonTarget !== null}
        onClose={() => {
          setFailedReasonTarget(null)
          setFailedReasonDraft([])
        }}
        title={failedReasonTarget ? `Set ${failedReasonTarget.setIndex + 1} failure reasons` : 'Failure reasons'}
        size="lg"
        centered
      >
        <Stack gap="md">
          <Checkbox.Group
            value={failedReasonDraft}
            onChange={(value) => setFailedReasonDraft(value as FailedSetReason[])}
            data-testid="failed-set-reasons"
          >
            <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="xs">
              {FAILED_SET_REASON_OPTIONS.map((option) => (
                <Checkbox
                  key={option.value}
                  value={option.value}
                  label={option.label}
                />
              ))}
            </SimpleGrid>
          </Checkbox.Group>
          <Group justify="flex-end">
            <Button
              variant="default"
              onClick={() => {
                setFailedReasonTarget(null)
                setFailedReasonDraft([])
              }}
            >
              Cancel
            </Button>
            <Button onClick={saveFailedSetReasons} disabled={failedReasonDraft.length === 0} data-testid="failed-set-reasons-save">
              Save
            </Button>
          </Group>
        </Stack>
      </Modal>

      <SessionToolkitModal
        opened={toolkitExercise !== null}
        onClose={() => setToolkitExercise(null)}
        exerciseName={toolkitExercise?.name || ''}
        targetKg={toolkitExercise?.targetKg ?? null}
        reps={toolkitExercise?.reps ?? null}
        isBarbell={toolkitExercise?.isBarbell ?? true}
      />
    </>
  )
}
