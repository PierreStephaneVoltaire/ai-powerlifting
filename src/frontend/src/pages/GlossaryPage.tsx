import { useState, useEffect, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { Search, Plus, Trash2, Edit2, RefreshCw, Info, Wand2, ExternalLink } from 'lucide-react'
import {
  Stack,
  Group,
  Text,
  TextInput,
  Textarea,
  Select,
  Button,
  Badge,
  Modal,
  Paper,
  Accordion,
  Slider,
  Loader,
  SimpleGrid,
  Box,
  Divider,
  Tooltip,
  SegmentedControl,
  NumberInput,
} from '@mantine/core'
import * as api from '@/api/client'
import { ExerciseMuscleMap } from '@/components/glossary/ExerciseMuscleMap'
import { useUiStore } from '@/store/uiStore'
import { useAuth } from '@/auth/AuthProvider'
import type { GlossaryExercise, MuscleGroup, ExerciseCategory, Equipment, FatigueProfile, FatigueProfileSource, GenericStatus, LiftTransfer } from '@powerlifting/types'
import DraftNumberInput from '../components/sessions/DraftNumberInput'

function formatFatigue(profile: FatigueProfile): string {
  return `axial ${Math.round(profile.axial * 100)}, neural ${Math.round(profile.neural * 100)}, peripheral ${Math.round(profile.peripheral * 100)}, systemic ${Math.round(profile.systemic * 100)}`
}

interface FatigueSliderProps {
  label: string
  value: number
  onChange: (v: number) => void
  help?: string
  disabled?: boolean
}

function FatigueSlider({ label, value, onChange, help, disabled }: FatigueSliderProps) {
  return (
    <Stack gap={4}>
      <Group justify="space-between">
        <Group gap={4}>
          <Text size="sm" c="dimmed">{label}</Text>
          {help && (
            <Tooltip label={help} multiline w={280} withArrow position="top-start">
              <Info size={12} color="var(--mantine-color-gray-6)" style={{ cursor: 'help' }} />
            </Tooltip>
          )}
        </Group>
        <Text size="xs" ff="monospace">{(value / 100).toFixed(2)}</Text>
      </Group>
      <Slider
        min={0}
        max={100}
        step={5}
        value={value}
        onChange={onChange}
        disabled={disabled}
      />
    </Stack>
  )
}

const MUSCLE_LABELS: Record<MuscleGroup, string> = {
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

const CATEGORY_LABELS: Record<ExerciseCategory, string> = {
  squat: 'Squat',
  bench: 'Bench',
  deadlift: 'Deadlift',
  back: 'Back',
  chest: 'Chest',
  arm: 'Arms',
  legs: 'Legs',
  core: 'Core',
  lower_back: 'Lower Back',
}

const EQUIPMENT_LABELS: Record<Equipment, string> = {
  barbell: 'Barbell',
  dumbbell: 'Dumbbell',
  cable: 'Cable',
  machine: 'Machine',
  bodyweight: 'Bodyweight',
  hex_bar: 'Hex Bar',
  bands: 'Bands',
  kettlebell: 'Kettlebell',
}

const YOUTUBE_HOSTS = new Set(['youtube.com', 'www.youtube.com', 'm.youtube.com', 'youtu.be'])

function validateYoutubeUrl(value: string | undefined): string | undefined {
  const raw = (value || '').trim()
  if (!raw) return undefined
  try {
    const parsed = new URL(raw)
    if (!YOUTUBE_HOSTS.has(parsed.hostname.toLowerCase())) return undefined
    return parsed.toString()
  } catch {
    return undefined
  }
}

function emptyExerciseForm(): Partial<GlossaryExercise> {
  return {
    name: '',
    category: 'squat',
    primary_muscles: [],
    secondary_muscles: [],
    tertiary_muscles: [],
    equipment: 'barbell',
    description: '',
    how_to_perform: '',
    why_do_it: '',
    video_url: '',
  }
}

const ALL_ASPECTS: api.EstimateAspect[] = ['fatigue', 'e1rm', 'muscles', 'lift_transfer', 'text']

const BULK_ESTIMATES: Record<'fatigue' | 'muscles' | 'e1rm', {
  label: string
  needsEstimate: (exercise: GlossaryExercise) => boolean
  overwrites: string
}> = {
  fatigue: {
    label: 'fatigue profiles',
    needsEstimate: (e) => !e.fatigue_profile || !e.fatigue_profile_personalized,
    overwrites: 'your personal fatigue profiles',
  },
  muscles: {
    label: 'muscle groups',
    needsEstimate: (e) => e.tertiary_muscles == null,
    overwrites: 'existing muscle groups',
  },
  e1rm: {
    label: 'e1RM',
    needsEstimate: (e) => !e.e1rm_estimate,
    overwrites: 'existing e1RM estimates',
  },
}

export default function GlossaryPage() {
  const { readOnly } = useAuth()
  const { pushToast } = useUiStore()
  const [exercises, setExercises] = useState<GlossaryExercise[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState('')
  const [isEditing, setIsEditing] = useState<GlossaryExercise | null>(null)
  const [showAddForm, setShowAddForm] = useState(false)

  // Form state for add/edit
  const [formData, setFormData] = useState<Partial<GlossaryExercise>>(emptyExerciseForm())
  const [fatigueProfile, setFatigueProfile] = useState<FatigueProfile | null>(null)
  const [fatigueSource, setFatigueSource] = useState<FatigueProfileSource | null>(null)
  const [fatigueReasoning, setFatigueReasoning] = useState<string | null>(null)
  const [genericFatigue, setGenericFatigue] = useState<FatigueProfile | null>(null)
  const [genericStatus, setGenericStatus] = useState<GenericStatus | null>(null)
  const [fatiguePersonalized, setFatiguePersonalized] = useState(false)
  const [liftTransfer, setLiftTransfer] = useState<LiftTransfer | null>(null)
  const [e1rmEstimate, setE1rmEstimate] = useState<GlossaryExercise['e1rm_estimate'] | null>(null)
  const [showArchived, setShowArchived] = useState(false)
  const [hasE1rmFilter, setHasE1rmFilter] = useState<'all' | 'with' | 'without'>('all')
  const [formEstimating, setFormEstimating] = useState<api.EstimateAspect[] | null>(null)
  const [bulkEstimating, setBulkEstimating] = useState<api.EstimateAspect | null>(null)

  useEffect(() => {
    loadExercises()
  }, [])

  async function loadExercises() {
    try {
      setIsLoading(true)
      const data = await api.fetchGlossary()
      setExercises(data || [])
    } catch (err) {
      console.error('Failed to load glossary:', err)
      pushToast({ message: 'Failed to load exercises', type: 'error' })
    } finally {
      setIsLoading(false)
    }
  }

  async function handleSearch(query: string) {
    setSearchQuery(query)
    if (!query.trim()) {
      loadExercises()
      return
    }
    try {
      const data = await api.searchExercises(query)
      setExercises(data || [])
    } catch (err) {
      console.error('Search failed:', err)
    }
  }

  async function handleSave() {
    if (!formData.name) {
      pushToast({ message: 'Exercise name is required', type: 'error' })
      return
    }

    const videoUrl = validateYoutubeUrl(formData.video_url)
    if ((formData.video_url || '').trim() && !videoUrl) {
      pushToast({ message: 'Use a valid YouTube URL', type: 'error' })
      return
    }

    try {
      const exercise: GlossaryExercise = {
        ...(isEditing || {}),
        id: (isEditing as GlossaryExercise | null)?.id ?? '',
        name: formData.name || '',
        category: formData.category || 'squat',
        fatigue_category: (isEditing as GlossaryExercise | null)?.fatigue_category || 'accessory',
        primary_muscles: formData.primary_muscles || [],
        secondary_muscles: formData.secondary_muscles || [],
        tertiary_muscles: formData.tertiary_muscles || [],
        equipment: formData.equipment || 'barbell',
        description: formData.description || '',
        how_to_perform: formData.how_to_perform || '',
        why_do_it: formData.why_do_it || '',
        video_url: videoUrl,
        fatigue_profile: fatiguePersonalized ? fatigueProfile || undefined : undefined,
        fatigue_profile_source: fatiguePersonalized ? fatigueSource || undefined : undefined,
        fatigue_profile_reasoning: fatiguePersonalized ? fatigueReasoning : null,
        lift_transfer: liftTransfer || undefined,
        e1rm_estimate: e1rmEstimate || undefined,
      }

      await api.upsertExercise(exercise)
      pushToast({
        message: isEditing ? 'Exercise updated' : 'Exercise added',
        type: 'success'
      })
      setShowAddForm(false)
      setIsEditing(null)
      setFormData(emptyExerciseForm())
      setFatigueProfile(null)
      setFatigueSource(null)
      setFatigueReasoning(null)
      setGenericFatigue(null)
      setGenericStatus(null)
      setFatiguePersonalized(false)
      setLiftTransfer(null)
      setE1rmEstimate(null)
      loadExercises()
    } catch (err) {
      pushToast({ message: 'Failed to save exercise', type: 'error' })
    }
  }

  async function handleDelete(id: string) {
    if (!confirm('Delete this exercise?')) return

    try {
      await api.deleteExercise(id)
      pushToast({ message: 'Exercise deleted', type: 'success' })
      setExercises((prev) => prev.filter((e) => e.id !== id))
    } catch (err) {
      pushToast({ message: 'Failed to delete exercise', type: 'error' })
    }
  }

  function startEdit(exercise: GlossaryExercise) {
    setIsEditing(exercise)
    setFormData({
      name: exercise.name,
      category: exercise.category,
      primary_muscles: exercise.primary_muscles,
      secondary_muscles: exercise.secondary_muscles,
      tertiary_muscles: exercise.tertiary_muscles ?? [],
      equipment: exercise.equipment,
      description: exercise.description ?? '',
      how_to_perform: exercise.how_to_perform ?? '',
      why_do_it: exercise.why_do_it ?? '',
      video_url: exercise.video_url ?? '',
    })
    setFatigueProfile(exercise.fatigue_profile || null)
    setFatigueSource(exercise.fatigue_profile_source || null)
    setFatigueReasoning(exercise.fatigue_profile_reasoning || null)
    setGenericFatigue(exercise.generic_fatigue_profile || null)
    setGenericStatus(exercise.generic_status || null)
    setFatiguePersonalized(!!exercise.fatigue_profile_personalized)
    setLiftTransfer(exercise.lift_transfer || null)
    setE1rmEstimate(exercise.e1rm_estimate || null)
    setShowAddForm(true)
  }

  function toggleMuscle(muscle: MuscleGroup, field: 'primary_muscles' | 'secondary_muscles' | 'tertiary_muscles') {
    setFormData((prev) => {
      const current = prev[field] || []
      const exists = current.includes(muscle)
      return {
        ...prev,
        [field]: exists
          ? current.filter((m) => m !== muscle)
          : [...current, muscle],
      }
    })
  }

  function handleFatigueSliderChange(dimension: keyof FatigueProfile, value: number) {
    setFatigueProfile((prev) => {
      const next = prev
        ? { ...prev, [dimension]: value / 100 }
        : { axial: 0, neural: 0, peripheral: 0, systemic: 0, [dimension]: value / 100 }
      return next as FatigueProfile
    })
    setFatigueSource('manual')
    setFatigueReasoning(null)
    setFatiguePersonalized(true)
  }

  function handleTransferChange(lift: 'squat' | 'bench' | 'deadlift', value: number | string) {
    const next = Math.max(0, Math.min(1, Number(value) || 0))
    setLiftTransfer((prev) => ({
      squat: prev?.squat ?? 0,
      bench: prev?.bench ?? 0,
      deadlift: prev?.deadlift ?? 0,
      reasoning: prev?.reasoning ?? '',
      [lift]: next,
      source: 'user',
    }))
  }

  function applyEstimated(fresh: GlossaryExercise, aspects: api.EstimateAspect[]) {
    setIsEditing(fresh)
    if (aspects.includes('fatigue')) {
      setFatigueProfile(fresh.fatigue_profile || null)
      setFatigueSource(fresh.fatigue_profile_source || null)
      setFatigueReasoning(fresh.fatigue_profile_reasoning || null)
      setGenericFatigue(fresh.generic_fatigue_profile || null)
      setGenericStatus(fresh.generic_status || null)
      setFatiguePersonalized(!!fresh.fatigue_profile_personalized)
    }
    if (aspects.includes('lift_transfer')) setLiftTransfer(fresh.lift_transfer || null)
    if (aspects.includes('e1rm')) setE1rmEstimate(fresh.e1rm_estimate || null)
    setFormData((prev) => ({
      ...prev,
      ...(aspects.includes('muscles')
        ? {
            primary_muscles: fresh.primary_muscles,
            secondary_muscles: fresh.secondary_muscles,
            tertiary_muscles: fresh.tertiary_muscles ?? [],
          }
        : {}),
      ...(aspects.includes('text')
        ? {
            description: fresh.description ?? '',
            how_to_perform: fresh.how_to_perform ?? '',
            why_do_it: fresh.why_do_it ?? '',
          }
        : {}),
    }))
  }

  async function handleFormEstimate(aspects: api.EstimateAspect[]) {
    const id = isEditing?.id
    if (!id) return
    const hasExistingText = Boolean(
      formData.description?.trim() ||
      formData.how_to_perform?.trim() ||
      formData.why_do_it?.trim()
    )
    if (aspects.includes('text') && hasExistingText && !window.confirm('Replace the existing exercise text with AI-generated text?')) {
      return
    }

    setFormEstimating(aspects)
    try {
      const result = await api.estimateExercises([id], aspects)
      if (result.saved.length === 0) {
        pushToast({ message: result.failed[0]?.reason || 'Estimation failed', type: 'error' })
        return
      }
      const data = await api.fetchGlossary()
      setExercises(data || [])
      const fresh = (data || []).find((exercise) => exercise.id === id)
      if (fresh) applyEstimated(fresh, aspects)
    } catch {
      pushToast({ message: 'Estimation failed', type: 'error' })
    } finally {
      setFormEstimating(null)
    }
  }

  async function handleBulkEstimate(aspect: 'fatigue' | 'muscles' | 'e1rm') {
    const { label, needsEstimate, overwrites } = BULK_ESTIMATES[aspect]
    const candidates = exercises.filter((e) => showArchived || !e.archived)
    const missing = candidates.filter(needsEstimate)
    const reEstimateAll = candidates.length > 0 && missing.length === 0
    const toEstimate = reEstimateAll ? candidates : missing
    if (toEstimate.length === 0) {
      pushToast({ message: `No exercises available for ${label} estimation`, type: 'warning' })
      return
    }

    const calls = Math.ceil(toEstimate.length / api.ESTIMATE_BATCH_SIZE)
    if (!window.confirm(`${reEstimateAll ? 'Re-estimate' : 'Estimate'} ${label} for ${toEstimate.length} exercises in ${calls} AI ${calls === 1 ? 'call' : 'calls'}${reEstimateAll ? ` and overwrite ${overwrites}` : ''}?`)) return

    setBulkEstimating(aspect)
    try {
      const result = await api.estimateExercises(toEstimate.map((e) => e.id), [aspect])
      pushToast({
        message: `Estimated ${label} for ${result.saved.length}/${toEstimate.length} exercises`,
        type: result.failed.length === 0 ? 'success' : 'warning',
      })
      loadExercises()
    } finally {
      setBulkEstimating(null)
    }
  }

  const filteredExercises = useMemo(() => {
    let result = exercises
    if (!showArchived) {
      result = result.filter(e => !e.archived)
    }
    if (hasE1rmFilter === 'with') {
      result = result.filter(e => !!e.e1rm_estimate?.value_kg)
    } else if (hasE1rmFilter === 'without') {
      result = result.filter(e => !e.e1rm_estimate?.value_kg)
    }
    if (!searchQuery.trim()) return result
    const query = searchQuery.toLowerCase()
    return result.filter(
      (e) =>
        e.name.toLowerCase().includes(query) ||
        e.category.toLowerCase().includes(query) ||
        e.description.toLowerCase().includes(query) ||
        e.how_to_perform.toLowerCase().includes(query) ||
        e.why_do_it.toLowerCase().includes(query) ||
        e.primary_muscles.some((m) => m.toLowerCase().includes(query)) ||
        e.secondary_muscles.some((m) => m.toLowerCase().includes(query)) ||
        (e.tertiary_muscles ?? []).some((m) => m.toLowerCase().includes(query))
    )
  }, [exercises, searchQuery, showArchived, hasE1rmFilter])

  const groupedExercises = useMemo(() => {
    const groups: Record<ExerciseCategory, GlossaryExercise[]> = {
      squat: [],
      bench: [],
      deadlift: [],
      back: [],
      chest: [],
      arm: [],
      legs: [],
      core: [],
      lower_back: [],
    }
    for (const exercise of filteredExercises) {
      groups[exercise.category].push(exercise)
    }
    return groups
  }, [filteredExercises])

  if (isLoading) {
    return (
      <Group justify="center" py={48}>
        <Loader />
      </Group>
    )
  }

  return (
    <Stack gap={16} className="if-mock-page">
      <div className="if-mock-header">
        <Stack gap={0}>
          <Group gap="xs">
            <Text component={Link} to="/designer" size="sm" c="dimmed" style={{ textDecoration: 'none' }}>
              Designer
            </Text>
            <Text c="dimmed">/</Text>
            <h1 className="if-mock-title">Glossary</h1>
          </Group>
          <div className="if-mock-subtitle">Browse and manage exercise definitions.</div>
        </Stack>
        <Group className="if-mock-toolbar">
          <Button
            variant="light"
            color="blue"
            leftSection={<RefreshCw size={16} />}
            onClick={() => handleBulkEstimate('fatigue')}
            loading={bulkEstimating === 'fatigue'}
            disabled={bulkEstimating !== null || readOnly}
          >
            Personalize Fatigue
          </Button>
          <Button
            variant="light"
            color="cyan"
            leftSection={<RefreshCw size={16} />}
            onClick={() => handleBulkEstimate('muscles')}
            loading={bulkEstimating === 'muscles'}
            disabled={bulkEstimating !== null || readOnly}
          >
            Estimate Muscles
          </Button>
          <Button
            variant="light"
            color="green"
            leftSection={<RefreshCw size={16} />}
            onClick={() => handleBulkEstimate('e1rm')}
            loading={bulkEstimating === 'e1rm'}
            disabled={bulkEstimating !== null || readOnly}
          >
            Estimate e1RM
          </Button>
          <Button
            leftSection={<Plus size={16} />}
            onClick={() => {
              setShowAddForm(true)
              setIsEditing(null)
              setFormData(emptyExerciseForm())
              setFatigueProfile(null)
              setFatigueSource(null)
              setFatigueReasoning(null)
              setGenericFatigue(null)
              setGenericStatus(null)
              setFatiguePersonalized(false)
              setLiftTransfer(null)
              setE1rmEstimate(null)
            }}
            disabled={readOnly}
          >
            Add Exercise
          </Button>
        </Group>
      </div>

      {/* Search and Filters */}
      <Paper withBorder p="md" radius="md" className="if-card">
        <Group align="flex-end">
          <TextInput
            leftSection={<Search size={16} />}
            placeholder="Search exercises..."
            value={searchQuery}
            onChange={(e) => handleSearch(e.currentTarget.value)}
            style={{ flex: 1, minWidth: 220 }}
          />
          <SegmentedControl
            visibleFrom="sm"
            size="sm"
            value={hasE1rmFilter}
            onChange={(v) => setHasE1rmFilter(v as 'all' | 'with' | 'without')}
            data={[
              { label: 'All e1RM', value: 'all' },
              { label: 'With e1RM', value: 'with' },
              { label: 'Missing e1RM', value: 'without' },
            ]}
            className="if-segmented"
          />
          <Select
            hiddenFrom="sm"
            aria-label="Estimated 1RM filter"
            value={hasE1rmFilter}
            onChange={(value) => value && setHasE1rmFilter(value as 'all' | 'with' | 'without')}
            data={[
              { label: 'All e1RM', value: 'all' },
              { label: 'With e1RM', value: 'with' },
              { label: 'Missing e1RM', value: 'without' },
            ]}
            style={{ flex: '1 1 100%', minWidth: 0 }}
          />
          <Button
            variant={showArchived ? 'filled' : 'light'}
            color="gray"
            size="sm"
            onClick={() => setShowArchived(!showArchived)}
          >
            {showArchived ? 'Hide Archived' : 'Show Archived'}
          </Button>
        </Group>
      </Paper>

      {/* Add/Edit Form Modal */}
      <Modal
        opened={showAddForm}
        onClose={() => { setShowAddForm(false); setIsEditing(null) }}
        title={isEditing ? 'Edit Exercise' : 'Add New Exercise'}
        size="xl"
        scrollAreaComponent={Stack}
      >
        <Stack gap="md" pb="md">
          <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md">
            <div>
              <Text size="sm" fw={500} mb={4}>Name</Text>
              <TextInput
                placeholder="Exercise Name"
                value={formData.name || ''}
                onChange={(e) => {
                  const val = e.currentTarget.value;
                  setFormData((p) => ({ ...p, name: val }));
                }}
                disabled={readOnly}
              />
            </div>
            <div>
              <Text size="sm" fw={500} mb={4}>Category</Text>
              <Select
                value={formData.category || 'squat'}
                onChange={(v) => setFormData((p) => ({ ...p, category: (v || 'squat') as ExerciseCategory }))}
                data={Object.entries(CATEGORY_LABELS).map(([value, label]) => ({ value, label }))}
                disabled={readOnly}
              />
            </div>
          </SimpleGrid>

          <div>
            <Text size="sm" fw={500} mb={4}>Equipment</Text>
            <Select
              value={formData.equipment || 'barbell'}
              onChange={(v) => setFormData((p) => ({ ...p, equipment: (v || 'barbell') as Equipment }))}
              data={Object.entries(EQUIPMENT_LABELS).map(([value, label]) => ({ value, label }))}
              disabled={readOnly}
            />
          </div>

          {/* Fatigue Profile Sliders */}
          <Paper withBorder p="md" radius="md" className="if-card">
            <Group justify="space-between" mb="sm">
              <Group gap="xs">
                <Text size="sm" fw={600}>Fatigue Profile</Text>
                {fatigueSource && (
                  <Badge
                    variant="light"
                    color={fatiguePersonalized ? 'blue' : 'gray'}
                    size="xs"
                  >
                    {fatiguePersonalized ? (fatigueSource === 'manual' ? 'Personal (manual)' : 'Personal (AI)') : 'Shared default'}
                  </Badge>
                )}
              </Group>
              <Button
                size="compact-xs"
                variant="light"
                onClick={() => handleFormEstimate(['fatigue'])}
                disabled={formEstimating !== null || !isEditing?.id || readOnly}
                leftSection={formEstimating?.includes('fatigue') ? <Loader size={12} /> : <RefreshCw size={12} />}
              >
                {formEstimating?.includes('fatigue') ? 'Estimating...' : 'Personalize with AI'}
              </Button>
            </Group>
            
            {fatiguePersonalized && genericFatigue && (
              <Text size="xs" c="dimmed" mb="xs">
                Shared default{genericStatus && genericStatus !== 'ready' ? ` (${genericStatus})` : ''}: {formatFatigue(genericFatigue)}
              </Text>
            )}
            {!fatiguePersonalized && genericStatus && genericStatus !== 'ready' && (
              <Text size="xs" c="dimmed" mb="xs">Shared default is {genericStatus}.</Text>
            )}

            <Stack gap="xs">
              <FatigueSlider
                label="Axial (Spinal Loading)"
                value={Math.round((fatigueProfile?.axial ?? 0) * 100)}
                onChange={(v) => handleFatigueSliderChange('axial', v)}
                help="Spinal compressive loading. High on squats and deadlifts where the bar sits on the spine or the erectors brace under load. Low on cable isolations and machines that take the spine out of the equation."
                disabled={readOnly}
              />
              <FatigueSlider
                label="Neural (CNS Demand)"
                value={Math.round((fatigueProfile?.neural ?? 0) * 100)}
                onChange={(v) => handleFatigueSliderChange('neural', v)}
                help="Central nervous system demand from high-intensity or technically dense work. High on heavy singles and near-max compounds (>=85% 1RM). Low on pump work, low-load hypertrophy, and machines."
                disabled={readOnly}
              />
              <FatigueSlider
                label="Peripheral (Muscle Damage)"
                value={Math.round((fatigueProfile?.peripheral ?? 0) * 100)}
                onChange={(v) => handleFatigueSliderChange('peripheral', v)}
                help="Local muscle damage, soreness, and eccentric stress in the target tissue. High on lengthened-partial hypertrophy work, slow eccentrics, and high-rep compounds. Low on short-range isometrics and explosive work."
                disabled={readOnly}
              />
              <FatigueSlider
                label="Systemic (Metabolic Load)"
                value={Math.round((fatigueProfile?.systemic ?? 0) * 100)}
                onChange={(v) => handleFatigueSliderChange('systemic', v)}
                help="Whole-body metabolic and cardiovascular cost. High on deadlifts, conditioning, and high-density circuits. Low on short-set isolations and skill work."
                disabled={readOnly}
              />
            </Stack>
            
            {fatiguePersonalized && fatigueSource !== 'manual' && fatigueReasoning && (
              <Box mt="sm" p="xs" style={{ background: 'var(--bg-elevated)', borderRadius: 8, border: '1px solid var(--border-subtle)' }}>
                <Text size="xs" fw={500} mb={2} c="dimmed">AI Reasoning:</Text>
                <Text size="xs" fs="italic" style={{ maxHeight: 100, overflowY: 'auto' }}>
                  {fatigueReasoning}
                </Text>
              </Box>
            )}
          </Paper>

          <Paper withBorder p="md" radius="md" className="if-card">
            <Group justify="space-between" mb="sm">
              <Group gap="xs">
                <Text size="sm" fw={600}>Lift Transfer</Text>
                {liftTransfer && (
                  <Tooltip
                    label={liftTransfer.reasoning || 'No reasoning recorded'}
                    multiline
                    w={280}
                    withArrow
                    position="top-start"
                  >
                    <Badge
                      variant="light"
                      color={liftTransfer.source === 'ai' ? 'blue' : liftTransfer.source === 'rule' ? 'gray' : 'green'}
                      size="xs"
                      style={{ cursor: 'help' }}
                    >
                      {liftTransfer.source === 'ai' ? 'AI Estimated' : liftTransfer.source === 'rule' ? 'Rule Default' : 'Manual Override'}
                    </Badge>
                  </Tooltip>
                )}
              </Group>
              <Button
                size="compact-xs"
                variant="light"
                onClick={() => handleFormEstimate(['lift_transfer'])}
                disabled={formEstimating !== null || !isEditing?.id || readOnly}
                leftSection={formEstimating?.includes('lift_transfer') ? <Loader size={12} /> : <RefreshCw size={12} />}
              >
                {formEstimating?.includes('lift_transfer') ? 'Estimating...' : 'Estimate transfer'}
              </Button>
            </Group>
            <SimpleGrid cols={3}>
              {(['squat', 'bench', 'deadlift'] as const).map((lift) => (
                <NumberInput
                  key={lift}
                  label={lift.charAt(0).toUpperCase() + lift.slice(1)}
                  min={0}
                  max={1}
                  step={0.05}
                  decimalScale={2}
                  value={liftTransfer?.[lift] ?? 0}
                  onChange={(v) => handleTransferChange(lift, v)}
                  disabled={readOnly}
                />
              ))}
            </SimpleGrid>
          </Paper>

          {/* e1RM Estimate Section */}
          <Paper withBorder p="md" radius="md" className="if-card">
            <Group justify="space-between" mb="sm">
              <Group gap="xs">
                <Text size="sm" fw={600}>e1RM Estimate</Text>
                {e1rmEstimate && (
                  <Badge
                    variant="light"
                    color={e1rmEstimate.confidence === 'high' ? 'green' : e1rmEstimate.confidence === 'medium' ? 'yellow' : 'red'}
                    size="xs"
                  >
                    {e1rmEstimate.confidence.toUpperCase()} CONFIDENCE
                  </Badge>
                )}
              </Group>
              <Button
                size="compact-xs"
                variant="light"
                color="green"
                onClick={() => handleFormEstimate(['e1rm'])}
                disabled={formEstimating !== null || !isEditing?.id || readOnly}
                leftSection={formEstimating?.includes('e1rm') ? <Loader size={12} /> : <RefreshCw size={12} />}
              >
                {formEstimating?.includes('e1rm') ? 'Estimating...' : 'AI Estimate'}
              </Button>
            </Group>

            <Group gap="md">
              <Stack gap={4} style={{ flex: 1 }}>
                <Text size="xs" c="dimmed">Value (kg)</Text>
                <DraftNumberInput
                  placeholder="e.g. 140"
                  inputMode="decimal"
                  value={e1rmEstimate?.value_kg ?? null}
                  isValid={(val) => val > 0}
                  onValueChange={(val) => {
                    setE1rmEstimate(prev => val === null ? null : ({
                      value_kg: val,
                      method: 'manual',
                      basis: prev?.basis || 'Manual override',
                      confidence: 'high',
                      set_at: new Date().toISOString(),
                      manually_overridden: true
                    }))
                  }}
                  disabled={readOnly}
                />
              </Stack>
              {e1rmEstimate && (
                <Stack gap={4} style={{ flex: 2 }}>
                  <Text size="xs" c="dimmed">Basis</Text>
                  <Text size="sm" fs="italic">{e1rmEstimate.basis}</Text>
                </Stack>
              )}
            </Group>
          </Paper>

          <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="md">
            <Stack gap={4}>
              <Group justify="space-between" gap="xs">
                <Text size="sm" fw={500}>Primary Muscles</Text>
                <Button
                  size="compact-xs"
                  variant="light"
                  color="blue"
                  onClick={() => handleFormEstimate(['muscles'])}
                  disabled={formEstimating !== null || !isEditing?.id || readOnly}
                  leftSection={formEstimating?.includes('muscles') ? <Loader size={12} /> : <RefreshCw size={12} />}
                >
                  {formEstimating?.includes('muscles') ? 'Estimating...' : 'AI Estimate'}
                </Button>
              </Group>
              <Paper withBorder p="xs" h={180} className="if-card" style={{ overflowY: 'auto' }}>
                <Group gap={4}>
                  {Object.entries(MUSCLE_LABELS).map(([value, label]) => (
                    <Button
                      key={value}
                      size="compact-xs"
                      variant={formData.primary_muscles?.includes(value as MuscleGroup) ? 'filled' : 'light'}
                      color={formData.primary_muscles?.includes(value as MuscleGroup) ? 'blue' : 'gray'}
                      onClick={() => toggleMuscle(value as MuscleGroup, 'primary_muscles')}
                      disabled={readOnly}
                    >
                      {label}
                    </Button>
                  ))}
                </Group>
              </Paper>
            </Stack>
            <Stack gap={4}>
              <Text size="sm" fw={500}>Secondary Muscles</Text>
              <Paper withBorder p="xs" h={180} className="if-card" style={{ overflowY: 'auto' }}>
                <Group gap={4}>
                  {Object.entries(MUSCLE_LABELS).map(([value, label]) => (
                    <Button
                      key={value}
                      size="compact-xs"
                      variant={formData.secondary_muscles?.includes(value as MuscleGroup) ? 'filled' : 'light'}
                      color={formData.secondary_muscles?.includes(value as MuscleGroup) ? 'blue' : 'gray'}
                      onClick={() => toggleMuscle(value as MuscleGroup, 'secondary_muscles')}
                      disabled={readOnly}
                    >
                      {label}
                    </Button>
                  ))}
                </Group>
              </Paper>
            </Stack>
          </SimpleGrid>

          <Stack gap={4}>
            <Text size="sm" fw={500}>Tertiary Muscles</Text>
            <Paper withBorder p="xs" h={140} className="if-card" style={{ overflowY: 'auto' }}>
              <Group gap={4}>
                {Object.entries(MUSCLE_LABELS).map(([value, label]) => (
                  <Button
                    key={value}
                    size="compact-xs"
                    variant={formData.tertiary_muscles?.includes(value as MuscleGroup) ? 'filled' : 'light'}
                    color={formData.tertiary_muscles?.includes(value as MuscleGroup) ? 'blue' : 'gray'}
                    onClick={() => toggleMuscle(value as MuscleGroup, 'tertiary_muscles')}
                    disabled={readOnly}
                  >
                    {label}
                  </Button>
                ))}
              </Group>
            </Paper>
          </Stack>

          <ExerciseMuscleMap
            primary={formData.primary_muscles ?? []}
            secondary={formData.secondary_muscles ?? []}
            tertiary={formData.tertiary_muscles ?? []}
          />

          <Paper withBorder p="md" className="if-card">
            <Stack gap="md">
              <Group justify="space-between" align="center">
                <Text size="sm" fw={600}>AI Generate</Text>
                <Button
                  size="compact-xs"
                  variant="light"
                  leftSection={formEstimating?.includes('text') ? <Loader size={12} /> : <Wand2 size={12} />}
                  onClick={() => handleFormEstimate(['text'])}
                  disabled={formEstimating !== null || !isEditing?.id || readOnly}
                >
                  {formEstimating?.includes('text') ? 'Generating...' : 'AI Generate'}
                </Button>
              </Group>

              <Textarea
                label="What it is"
                placeholder="Short description of the movement."
                autosize
                minRows={2}
                value={formData.description || ''}
                onChange={(e) => setFormData((p) => ({ ...p, description: e.currentTarget.value }))}
                disabled={readOnly}
              />
              <Textarea
                label="How to perform it"
                placeholder="Concise setup and execution steps."
                autosize
                minRows={3}
                value={formData.how_to_perform || ''}
                onChange={(e) => setFormData((p) => ({ ...p, how_to_perform: e.currentTarget.value }))}
                disabled={readOnly}
              />
              <Textarea
                label="Why we do it"
                placeholder="Training purpose and how it supports the program."
                autosize
                minRows={2}
                value={formData.why_do_it || ''}
                onChange={(e) => setFormData((p) => ({ ...p, why_do_it: e.currentTarget.value }))}
                disabled={readOnly}
              />
              <TextInput
                label="YouTube URL"
                placeholder="https://www.youtube.com/watch?v=..."
                value={formData.video_url || ''}
                error={(formData.video_url || '').trim() && !validateYoutubeUrl(formData.video_url) ? 'Use a valid YouTube URL' : undefined}
                onChange={(e) => setFormData((p) => ({ ...p, video_url: e.currentTarget.value }))}
                disabled={readOnly}
              />
            </Stack>
          </Paper>

          <Divider mt="md" />

          <Group justify="flex-end">
            <Button
              variant="light"
              leftSection={formEstimating?.length === ALL_ASPECTS.length ? <Loader size={12} /> : <Wand2 size={12} />}
              onClick={() => handleFormEstimate(ALL_ASPECTS)}
              disabled={formEstimating !== null || !isEditing?.id || readOnly}
            >
              Estimate all
            </Button>
            <Button
              variant="default"
              onClick={() => {
                setShowAddForm(false)
                setIsEditing(null)
              }}
            >
              Cancel
            </Button>
            <Button onClick={handleSave} disabled={readOnly}>
              {isEditing ? 'Update Exercise' : 'Create Exercise'}
            </Button>
          </Group>
        </Stack>
      </Modal>

      {/* Exercise List by Category */}
      {Object.entries(groupedExercises).map(([category, categoryExercises]) => {
        if (categoryExercises.length === 0) return null

        return (
          <Stack key={category} gap="xs">
            <Group gap="xs">
              <Text fz="h2" fw={600}>{CATEGORY_LABELS[category as ExerciseCategory]}</Text>
              <Text size="sm" c="dimmed">({categoryExercises.length})</Text>
            </Group>

            <Accordion
              variant="contained"
              chevronPosition="right"
              className="if-glossary-list if-mock-accordion"
            >
              {categoryExercises.map((exercise) => (
                <Accordion.Item key={exercise.id} value={exercise.id}>
                  <Accordion.Control>
                    <Group gap="xs" wrap="wrap" style={{ minWidth: 0, paddingRight: 8 }}>
                      <Text fw={500} style={{ flex: '1 1 180px', minWidth: 0, whiteSpace: 'normal' }}>{exercise.name}</Text>
                      <Badge style={{ flexShrink: 0 }} variant="light" color="gray" size="sm">
                        {EQUIPMENT_LABELS[exercise.equipment]}
                      </Badge>
                      {exercise.fatigue_profile && (
                        <Badge style={{ flexShrink: 0 }} variant="light" color={exercise.fatigue_profile_personalized ? 'blue' : 'gray'} size="sm">
                          {exercise.fatigue_profile_personalized ? 'Personal FP' : 'Shared FP'}
                        </Badge>
                      )}
                      {exercise.e1rm_estimate && (
                        <Badge style={{ flexShrink: 0 }} variant="filled" color="green" size="sm">
                          e1RM: {exercise.e1rm_estimate.value_kg}kg
                        </Badge>
                      )}
                      {exercise.archived && <Badge color="gray" size="sm">Archived</Badge>}
                    </Group>
                  </Accordion.Control>
                  <Accordion.Panel>
                    <Stack gap="md">
                      {/* Muscles */}
                      <SimpleGrid cols={2} spacing="md">
                        <div>
                          <Text size="xs" c="dimmed" mb={4}>Primary Muscles</Text>
                          <Group gap={4}>
                            {exercise.primary_muscles.map((m) => (
                              <Badge key={m} variant="light" size="sm">
                                {MUSCLE_LABELS[m]}
                              </Badge>
                            ))}
                          </Group>
                        </div>
                        {exercise.secondary_muscles.length > 0 && (
                          <div>
                            <Text size="xs" c="dimmed" mb={4}>Secondary Muscles</Text>
                            <Group gap={4}>
                              {exercise.secondary_muscles.map((m) => (
                                <Badge key={m} variant="outline" size="sm">
                                  {MUSCLE_LABELS[m]}
                                </Badge>
                              ))}
                            </Group>
                          </div>
                        )}
                        {(exercise.tertiary_muscles?.length ?? 0) > 0 && (
                          <div>
                            <Text size="xs" c="dimmed" mb={4}>Tertiary Muscles</Text>
                            <Group gap={4}>
                              {(exercise.tertiary_muscles ?? []).map((m) => (
                                <Badge key={m} variant="dot" size="sm">
                                  {MUSCLE_LABELS[m]}
                                </Badge>
                              ))}
                            </Group>
                          </div>
                        )}
                      </SimpleGrid>

                      {(exercise.description || exercise.how_to_perform || exercise.why_do_it || exercise.video_url) && (
                        <SimpleGrid cols={{ base: 1, md: 3 }} spacing="md">
                          {exercise.description && (
                            <div>
                              <Text size="xs" c="dimmed" mb={4}>What It Is</Text>
                              <Text size="sm">{exercise.description}</Text>
                            </div>
                          )}
                          {exercise.how_to_perform && (
                            <div>
                              <Text size="xs" c="dimmed" mb={4}>How To Perform</Text>
                              <Text size="sm">{exercise.how_to_perform}</Text>
                            </div>
                          )}
                          {exercise.why_do_it && (
                            <div>
                              <Text size="xs" c="dimmed" mb={4}>Why We Do It</Text>
                              <Text size="sm">{exercise.why_do_it}</Text>
                            </div>
                          )}
                          {exercise.video_url && (
                            <div>
                              <Text size="xs" c="dimmed" mb={4}>Example Video</Text>
                              <Button
                                component="a"
                                href={exercise.video_url}
                                target="_blank"
                                rel="noreferrer"
                                size="compact-sm"
                                variant="light"
                                leftSection={<ExternalLink size={12} />}
                              >
                                Open YouTube
                              </Button>
                            </div>
                          )}
                        </SimpleGrid>
                      )}

                      {/* Actions */}
                      <Group gap="xs">
                        <Button
                          size="compact-sm"
                          variant="default"
                          leftSection={readOnly ? <Search size={12} /> : <Edit2 size={12} />}
                          onClick={() => startEdit(exercise)}
                        >
                          {readOnly ? 'View' : 'Edit'}
                        </Button>
                        <Button
                          size="compact-sm"
                          variant="light"
                          color="red"
                          leftSection={<Trash2 size={12} />}
                          onClick={() => handleDelete(exercise.id)}
                          disabled={readOnly}
                        >
                          Delete
                        </Button>
                        <Button
                          size="compact-sm"
                          variant="light"
                          color="gray"
                          onClick={async () => {
                            try {
                              if (exercise.archived) {
                                await api.unarchiveExercise(exercise.id)
                                pushToast({ message: 'Exercise unarchived', type: 'success' })
                              } else {
                                await api.archiveExercise(exercise.id)
                                pushToast({ message: 'Exercise archived', type: 'success' })
                              }
                              loadExercises()
                            } catch {
                              pushToast({ message: 'Failed to update exercise', type: 'error' })
                            }
                          }}
                          disabled={readOnly}
                        >
                          {exercise.archived ? 'Unarchive' : 'Archive'}
                        </Button>
                      </Group>
                    </Stack>
                  </Accordion.Panel>
                </Accordion.Item>
              ))}
            </Accordion>
          </Stack>
        )
      })}

      {filteredExercises.length === 0 && (
        <Text ta="center" py={48} c="dimmed">
          {searchQuery ? 'No exercises found matching your search.' : 'No exercises in the glossary yet.'}
        </Text>
      )}
    </Stack>
  )
}
