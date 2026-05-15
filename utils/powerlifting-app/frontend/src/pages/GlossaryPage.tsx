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
  Progress,
} from '@mantine/core'
import * as api from '@/api/client'
import { ExerciseMuscleMap } from '@/components/glossary/ExerciseMuscleMap'
import { useProgramStore } from '@/store/programStore'
import { useUiStore } from '@/store/uiStore'
import type { GlossaryExercise, MuscleGroup, ExerciseCategory, Equipment, FatigueProfile, FatigueProfileSource } from '@powerlifting/types'

interface FatigueSliderProps {
  label: string
  value: number
  onChange: (v: number) => void
  help?: string
}

function FatigueSlider({ label, value, onChange, help }: FatigueSliderProps) {
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

export default function GlossaryPage() {
  const { pushToast } = useUiStore()
  const liftProfiles = useProgramStore((state) => state.program?.lift_profiles ?? [])
  const [exercises, setExercises] = useState<GlossaryExercise[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState('')
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [isEditing, setIsEditing] = useState<GlossaryExercise | null>(null)
  const [showAddForm, setShowAddForm] = useState(false)

  // Form state for add/edit
  const [formData, setFormData] = useState<Partial<GlossaryExercise>>(emptyExerciseForm())
  const [fatigueProfile, setFatigueProfile] = useState<FatigueProfile | null>(null)
  const [fatigueSource, setFatigueSource] = useState<FatigueProfileSource | null>(null)
  const [fatigueReasoning, setFatigueReasoning] = useState<string | null>(null)
  const [e1rmEstimate, setE1rmEstimate] = useState<GlossaryExercise['e1rm_estimate'] | null>(null)
  const [showArchived, setShowArchived] = useState(false)
  const [hasE1rmFilter, setHasE1rmFilter] = useState<'all' | 'with' | 'without'>('all')
  const [isEstimating, setIsEstimating] = useState(false)
  const [isEstimatingMuscles, setIsEstimatingMuscles] = useState(false)
  const [isEstimatingE1rm, setIsEstimatingE1rm] = useState(false)
  const [isGeneratingText, setIsGeneratingText] = useState(false)
  const [isBulkEstimatingFatigue, setIsBulkEstimatingFatigue] = useState(false)
  const [isBulkEstimatingE1rm, setIsBulkEstimatingE1rm] = useState(false)
  const [isBulkEstimatingMuscles, setIsBulkEstimatingMuscles] = useState(false)
  const [bulkProgress, setBulkProgress] = useState<{ current: number; total: number; label: string } | null>(null)

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
        fatigue_profile: fatigueProfile || undefined,
        fatigue_profile_source: fatigueSource || undefined,
        fatigue_profile_reasoning: fatigueReasoning,
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
  }

  async function handleReEstimate() {
    setIsEstimating(true)
    try {
      const result = await api.estimateFatigueProfile({
        name: formData.name || '',
        category: formData.category,
        equipment: formData.equipment,
        primary_muscles: formData.primary_muscles,
        secondary_muscles: formData.secondary_muscles,
        tertiary_muscles: formData.tertiary_muscles,
        description: formData.description,
        how_to_perform: formData.how_to_perform,
        why_do_it: formData.why_do_it,
      })
      setFatigueProfile({
        axial: result.axial,
        neural: result.neural,
        peripheral: result.peripheral,
        systemic: result.systemic,
      })
      setFatigueSource('ai_estimated')
      setFatigueReasoning(result.reasoning)
    } catch {
      pushToast({ message: 'Fatigue estimation failed', type: 'error' })
    } finally {
      setIsEstimating(false)
    }
  }

  async function handleEstimateMuscles() {
    setIsEstimatingMuscles(true)
    try {
      const result = await api.estimateMuscleGroups({
        name: formData.name || '',
        category: formData.category,
        equipment: formData.equipment,
        primary_muscles: formData.primary_muscles,
        secondary_muscles: formData.secondary_muscles,
        tertiary_muscles: formData.tertiary_muscles,
        description: formData.description,
        how_to_perform: formData.how_to_perform,
        why_do_it: formData.why_do_it,
        lift_profiles: liftProfiles,
      })
      setFormData((prev) => ({
        ...prev,
        primary_muscles: result.primary_muscles as MuscleGroup[],
        secondary_muscles: result.secondary_muscles as MuscleGroup[],
        tertiary_muscles: result.tertiary_muscles as MuscleGroup[],
      }))
    } catch {
      pushToast({ message: 'Muscle group estimation failed', type: 'error' })
    } finally {
      setIsEstimatingMuscles(false)
    }
  }

  async function handleGenerateText() {
    if (!formData.name) {
      pushToast({ message: 'Exercise name is required', type: 'error' })
      return
    }

    const hasExistingText = Boolean(
      formData.description?.trim() ||
      formData.how_to_perform?.trim() ||
      formData.why_do_it?.trim()
    )
    if (hasExistingText && !window.confirm('Replace the existing exercise text with AI-generated text?')) {
      return
    }

    setIsGeneratingText(true)
    try {
      const result = await api.generateGlossaryText({
        name: formData.name,
        category: formData.category,
        equipment: formData.equipment,
        primary_muscles: formData.primary_muscles,
        secondary_muscles: formData.secondary_muscles,
        tertiary_muscles: formData.tertiary_muscles,
        description: formData.description,
        how_to_perform: formData.how_to_perform,
        why_do_it: formData.why_do_it,
        lift_profiles: liftProfiles,
      })
      setFormData((prev) => ({
        ...prev,
        description: result.description || '',
        how_to_perform: result.how_to_perform || '',
        why_do_it: result.why_do_it || '',
      }))
    } catch {
      pushToast({ message: 'Glossary text generation failed', type: 'error' })
    } finally {
      setIsGeneratingText(false)
    }
  }

  async function handleBulkEstimateFatigue() {
    const candidates = exercises.filter((e) => showArchived || !e.archived)
    const missingEstimates = candidates.filter(e => !e.fatigue_profile || e.fatigue_profile_source !== 'ai_estimated')
    const shouldReEstimateAll = candidates.length > 0 && missingEstimates.length === 0
    const toEstimate = shouldReEstimateAll ? candidates : missingEstimates
    if (toEstimate.length === 0) {
      pushToast({ message: 'No exercises available for fatigue estimation', type: 'warning' })
      return
    }

    if (!confirm(`${shouldReEstimateAll ? 'Re-estimate' : 'Estimate'} fatigue profiles for ${toEstimate.length} exercises? This will call the AI backend multiple times${shouldReEstimateAll ? ' and overwrite existing AI fatigue profiles' : ''}.`)) return

    setIsBulkEstimatingFatigue(true)
    setBulkProgress({ current: 0, total: toEstimate.length, label: 'Estimating fatigue profiles' })

    try {
      let successCount = 0
      for (let i = 0; i < toEstimate.length; i++) {
        setBulkProgress({ current: i + 1, total: toEstimate.length, label: 'Estimating fatigue profiles' })
        try {
          const res = await api.estimateExerciseFatigue(toEstimate[i].id)
          if (res?.fatigue_profile || res?.profile) {
            successCount++
          }
        } catch (err) {
          console.error(`Failed to estimate fatigue for ${toEstimate[i].name}`, err)
        }
      }

      pushToast({ message: `Successfully estimated fatigue for ${successCount}/${toEstimate.length} exercises`, type: 'success' })
      loadExercises()
    } finally {
      setIsBulkEstimatingFatigue(false)
      setBulkProgress(null)
    }
  }

  async function handleBulkEstimateE1rm() {
    const candidates = exercises.filter((e) => showArchived || !e.archived)
    const missingEstimates = candidates.filter(e => !e.e1rm_estimate)
    const shouldReEstimateAll = candidates.length > 0 && missingEstimates.length === 0
    const toEstimate = shouldReEstimateAll ? candidates : missingEstimates
    if (toEstimate.length === 0) {
      pushToast({ message: 'No exercises available for e1RM estimation', type: 'warning' })
      return
    }

    if (!window.confirm(`${shouldReEstimateAll ? 'Re-estimate' : 'Estimate'} e1RM for ${toEstimate.length} exercises? This will call the AI backend multiple times${shouldReEstimateAll ? ' and overwrite existing e1RM estimates' : ''}.`)) return

    setIsBulkEstimatingE1rm(true)
    setBulkProgress({ current: 0, total: toEstimate.length, label: 'Estimating e1RM values' })

    try {
      let successCount = 0
      for (let i = 0; i < toEstimate.length; i++) {
        setBulkProgress({ current: i + 1, total: toEstimate.length, label: 'Estimating e1RM values' })
        try {
          const res = await api.estimateExerciseE1rm(toEstimate[i].id)
          if (res?.estimate) {
            successCount++
          }
        } catch (err) {
          console.error(`Failed to estimate e1RM for ${toEstimate[i].name}`, err)
        }
      }

      pushToast({ message: `Successfully estimated e1RM for ${successCount}/${toEstimate.length} exercises`, type: 'success' })
      loadExercises()
    } finally {
      setIsBulkEstimatingE1rm(false)
      setBulkProgress(null)
    }
  }

  async function handleBulkEstimateMuscles() {
    const candidates = exercises.filter((e) => showArchived || !e.archived)
    const missingEstimates = candidates.filter((e) => e.tertiary_muscles == null)
    const shouldReEstimateAll = candidates.length > 0 && missingEstimates.length === 0
    const toEstimate = shouldReEstimateAll ? candidates : missingEstimates
    if (toEstimate.length === 0) {
      pushToast({ message: 'No exercises available for muscle group estimation', type: 'warning' })
      return
    }

    if (!confirm(`${shouldReEstimateAll ? 'Re-estimate' : 'Estimate'} muscle groups for ${toEstimate.length} exercises? This will call the AI backend multiple times${shouldReEstimateAll ? ' and overwrite existing muscle groups' : ''}.`)) return

    setIsBulkEstimatingMuscles(true)
    setBulkProgress({ current: 0, total: toEstimate.length, label: 'Estimating muscle groups' })

    try {
      let successCount = 0
      for (let i = 0; i < toEstimate.length; i++) {
        setBulkProgress({ current: i + 1, total: toEstimate.length, label: 'Estimating muscle groups' })
        try {
          const res = await api.estimateExerciseMuscles(toEstimate[i].id)
          if (Array.isArray(res?.primary_muscles) && Array.isArray(res?.secondary_muscles) && Array.isArray(res?.tertiary_muscles)) {
            successCount++
          }
        } catch (err) {
          console.error(`Failed to estimate muscles for ${toEstimate[i].name}`, err)
        }
      }

      pushToast({ message: `Successfully estimated muscle groups for ${successCount}/${toEstimate.length} exercises`, type: 'success' })
      loadExercises()
    } finally {
      setIsBulkEstimatingMuscles(false)
      setBulkProgress(null)
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
    <Stack gap={24}>
      <Group justify="space-between">
        <Stack gap={0}>
          <Group gap="xs">
            <Text component={Link} to="/designer" size="sm" c="dimmed" style={{ textDecoration: 'none' }}>
              Designer
            </Text>
            <Text c="dimmed">/</Text>
            <Text fz="h1" fw={700}>Glossary</Text>
          </Group>
          <Text c="dimmed" size="sm" mt={4}>Browse and manage exercise definitions</Text>
        </Stack>
        <Group>
          <Button
            variant="light"
            color="blue"
            leftSection={<RefreshCw size={16} />}
            onClick={handleBulkEstimateFatigue}
            loading={isBulkEstimatingFatigue}
            disabled={isBulkEstimatingFatigue || isBulkEstimatingE1rm || isBulkEstimatingMuscles}
          >
            {isBulkEstimatingFatigue && bulkProgress ? `Fatigue (${bulkProgress.current}/${bulkProgress.total})` : 'Estimate Fatigue'}
          </Button>
          <Button
            variant="light"
            color="cyan"
            leftSection={<RefreshCw size={16} />}
            onClick={handleBulkEstimateMuscles}
            loading={isBulkEstimatingMuscles}
            disabled={isBulkEstimatingFatigue || isBulkEstimatingE1rm || isBulkEstimatingMuscles}
          >
            {isBulkEstimatingMuscles && bulkProgress ? `Muscles (${bulkProgress.current}/${bulkProgress.total})` : 'Estimate Muscles'}
          </Button>
          <Button
            variant="light"
            color="green"
            leftSection={<RefreshCw size={16} />}
            onClick={handleBulkEstimateE1rm}
            loading={isBulkEstimatingE1rm}
            disabled={isBulkEstimatingFatigue || isBulkEstimatingE1rm || isBulkEstimatingMuscles}
          >
            {isBulkEstimatingE1rm && bulkProgress ? `e1RM (${bulkProgress.current}/${bulkProgress.total})` : 'Estimate e1RM'}
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
              setE1rmEstimate(null)
            }}
          >
            Add Exercise
          </Button>
        </Group>
      </Group>

      {/* Search and Filters */}
      <Group align="flex-end">
        <TextInput
          leftSection={<Search size={16} />}
          placeholder="Search exercises..."
          value={searchQuery}
          onChange={(e) => handleSearch(e.currentTarget.value)}
          style={{ flex: 1 }}
        />
        <SegmentedControl
          size="sm"
          value={hasE1rmFilter}
          onChange={(v) => setHasE1rmFilter(v as 'all' | 'with' | 'without')}
          data={[
            { label: 'All e1RM', value: 'all' },
            { label: 'With e1RM', value: 'with' },
            { label: 'Missing e1RM', value: 'without' },
          ]}
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

      {bulkProgress && (
        <Paper withBorder p="sm">
          <Stack gap={6}>
            <Group justify="space-between" gap="sm">
              <Text size="sm" fw={500}>{bulkProgress.label}</Text>
              <Text size="sm" c="dimmed">{bulkProgress.current}/{bulkProgress.total}</Text>
            </Group>
            <Progress value={bulkProgress.total > 0 ? (bulkProgress.current / bulkProgress.total) * 100 : 0} />
          </Stack>
        </Paper>
      )}

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
              />
            </div>
            <div>
              <Text size="sm" fw={500} mb={4}>Category</Text>
              <Select
                value={formData.category || 'squat'}
                onChange={(v) => setFormData((p) => ({ ...p, category: (v || 'squat') as ExerciseCategory }))}
                data={Object.entries(CATEGORY_LABELS).map(([value, label]) => ({ value, label }))}
              />
            </div>
          </SimpleGrid>

          <div>
            <Text size="sm" fw={500} mb={4}>Equipment</Text>
            <Select
              value={formData.equipment || 'barbell'}
              onChange={(v) => setFormData((p) => ({ ...p, equipment: (v || 'barbell') as Equipment }))}
              data={Object.entries(EQUIPMENT_LABELS).map(([value, label]) => ({ value, label }))}
            />
          </div>

          {/* Fatigue Profile Sliders */}
          <Paper withBorder p="md" radius="md" bg="var(--mantine-color-gray-light)">
            <Group justify="space-between" mb="sm">
              <Group gap="xs">
                <Text size="sm" fw={600}>Fatigue Profile</Text>
                {fatigueSource && (
                  <Badge
                    variant="light"
                    color={fatigueSource === 'ai_estimated' ? 'blue' : 'green'}
                    size="xs"
                  >
                    {fatigueSource === 'ai_estimated' ? 'AI Estimated' : 'Manual Override'}
                  </Badge>
                )}
              </Group>
              <Button
                size="compact-xs"
                variant="light"
                onClick={handleReEstimate}
                disabled={isEstimating || !formData.name}
                leftSection={isEstimating ? <Loader size={12} /> : <RefreshCw size={12} />}
              >
                {isEstimating ? 'Estimating...' : 'AI Estimate'}
              </Button>
            </Group>
            
            <Stack gap="xs">
              <FatigueSlider
                label="Axial (Spinal Loading)"
                value={Math.round((fatigueProfile?.axial ?? 0) * 100)}
                onChange={(v) => handleFatigueSliderChange('axial', v)}
                help="Spinal compressive loading. High on squats and deadlifts where the bar sits on the spine or the erectors brace under load. Low on cable isolations and machines that take the spine out of the equation."
              />
              <FatigueSlider
                label="Neural (CNS Demand)"
                value={Math.round((fatigueProfile?.neural ?? 0) * 100)}
                onChange={(v) => handleFatigueSliderChange('neural', v)}
                help="Central nervous system demand from high-intensity or technically dense work. High on heavy singles and near-max compounds (>=85% 1RM). Low on pump work, low-load hypertrophy, and machines."
              />
              <FatigueSlider
                label="Peripheral (Muscle Damage)"
                value={Math.round((fatigueProfile?.peripheral ?? 0) * 100)}
                onChange={(v) => handleFatigueSliderChange('peripheral', v)}
                help="Local muscle damage, soreness, and eccentric stress in the target tissue. High on lengthened-partial hypertrophy work, slow eccentrics, and high-rep compounds. Low on short-range isometrics and explosive work."
              />
              <FatigueSlider
                label="Systemic (Metabolic Load)"
                value={Math.round((fatigueProfile?.systemic ?? 0) * 100)}
                onChange={(v) => handleFatigueSliderChange('systemic', v)}
                help="Whole-body metabolic and cardiovascular cost. High on deadlifts, conditioning, and high-density circuits. Low on short-set isolations and skill work."
              />
            </Stack>
            
            {fatigueSource === 'ai_estimated' && fatigueReasoning && (
              <Box mt="sm" p="xs" style={{ background: 'var(--mantine-color-body)', borderRadius: 4, border: '1px solid var(--mantine-color-gray-2)' }}>
                <Text size="xs" fw={500} mb={2} c="dimmed">AI Reasoning:</Text>
                <Text size="xs" fs="italic" style={{ maxHeight: 100, overflowY: 'auto' }}>
                  {fatigueReasoning}
                </Text>
              </Box>
            )}
          </Paper>

          {/* e1RM Estimate Section */}
          <Paper withBorder p="md" radius="md" bg="var(--mantine-color-green-light)">
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
                onClick={async () => {
                  if (!isEditing?.id) return
                  setIsEstimatingE1rm(true)
                  try {
                    const res = await api.estimateExerciseE1rm(isEditing.id)
                    if (res?.estimate) {
                      setE1rmEstimate({
                        value_kg: res.estimate.e1rm_kg,
                        method: 'ai_backfill',
                        basis: res.estimate.basis,
                        confidence: res.estimate.confidence,
                        set_at: new Date().toISOString(),
                        manually_overridden: false,
                      })
                    } else {
                      pushToast({ message: 'e1RM estimation returned no result', type: 'error' })
                    }
                  } catch {
                    pushToast({ message: 'e1RM estimation failed', type: 'error' })
                  } finally {
                    setIsEstimatingE1rm(false)
                  }
                }}
                disabled={isEstimatingE1rm || !isEditing?.id}
                leftSection={isEstimatingE1rm ? <Loader size={12} /> : <RefreshCw size={12} />}
              >
                {isEstimatingE1rm ? 'Estimating...' : 'AI Estimate'}
              </Button>
            </Group>

            <Group gap="md">
              <Stack gap={4} style={{ flex: 1 }}>
                <Text size="xs" c="dimmed">Value (kg)</Text>
                <TextInput
                  type="number"
                  placeholder="e.g. 140"
                  value={e1rmEstimate?.value_kg || ''}
                  onChange={(e) => {
                    const val = parseFloat(e.currentTarget.value)
                    setE1rmEstimate(prev => ({
                      value_kg: isNaN(val) ? 0 : val,
                      method: 'manual',
                      basis: prev?.basis || 'Manual override',
                      confidence: 'high',
                      set_at: new Date().toISOString(),
                      manually_overridden: true
                    }))
                  }}
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
                  onClick={handleEstimateMuscles}
                  disabled={isEstimatingMuscles || !formData.name}
                  leftSection={isEstimatingMuscles ? <Loader size={12} /> : <RefreshCw size={12} />}
                >
                  {isEstimatingMuscles ? 'Estimating...' : 'AI Estimate'}
                </Button>
              </Group>
              <Paper withBorder p="xs" h={180} style={{ overflowY: 'auto' }}>
                <Group gap={4}>
                  {Object.entries(MUSCLE_LABELS).map(([value, label]) => (
                    <Button
                      key={value}
                      size="compact-xs"
                      variant={formData.primary_muscles?.includes(value as MuscleGroup) ? 'filled' : 'light'}
                      color={formData.primary_muscles?.includes(value as MuscleGroup) ? 'blue' : 'gray'}
                      onClick={() => toggleMuscle(value as MuscleGroup, 'primary_muscles')}
                    >
                      {label}
                    </Button>
                  ))}
                </Group>
              </Paper>
            </Stack>
            <Stack gap={4}>
              <Text size="sm" fw={500}>Secondary Muscles</Text>
              <Paper withBorder p="xs" h={180} style={{ overflowY: 'auto' }}>
                <Group gap={4}>
                  {Object.entries(MUSCLE_LABELS).map(([value, label]) => (
                    <Button
                      key={value}
                      size="compact-xs"
                      variant={formData.secondary_muscles?.includes(value as MuscleGroup) ? 'filled' : 'light'}
                      color={formData.secondary_muscles?.includes(value as MuscleGroup) ? 'blue' : 'gray'}
                      onClick={() => toggleMuscle(value as MuscleGroup, 'secondary_muscles')}
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
            <Paper withBorder p="xs" h={140} style={{ overflowY: 'auto' }}>
              <Group gap={4}>
                {Object.entries(MUSCLE_LABELS).map(([value, label]) => (
                  <Button
                    key={value}
                    size="compact-xs"
                    variant={formData.tertiary_muscles?.includes(value as MuscleGroup) ? 'filled' : 'light'}
                    color={formData.tertiary_muscles?.includes(value as MuscleGroup) ? 'blue' : 'gray'}
                    onClick={() => toggleMuscle(value as MuscleGroup, 'tertiary_muscles')}
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

          <Paper withBorder p="md">
            <Stack gap="md">
              <Group justify="space-between" align="center">
                <Text size="sm" fw={600}>AI Generate</Text>
                <Button
                  size="compact-xs"
                  variant="light"
                  leftSection={isGeneratingText ? <Loader size={12} /> : <Wand2 size={12} />}
                  onClick={handleGenerateText}
                  disabled={isGeneratingText || !formData.name}
                >
                  {isGeneratingText ? 'Generating...' : 'AI Generate'}
                </Button>
              </Group>

              <Textarea
                label="What it is"
                placeholder="Short description of the movement."
                autosize
                minRows={2}
                value={formData.description || ''}
                onChange={(e) => setFormData((p) => ({ ...p, description: e.currentTarget.value }))}
              />
              <Textarea
                label="How to perform it"
                placeholder="Concise setup and execution steps."
                autosize
                minRows={3}
                value={formData.how_to_perform || ''}
                onChange={(e) => setFormData((p) => ({ ...p, how_to_perform: e.currentTarget.value }))}
              />
              <Textarea
                label="Why we do it"
                placeholder="Training purpose and how it supports the program."
                autosize
                minRows={2}
                value={formData.why_do_it || ''}
                onChange={(e) => setFormData((p) => ({ ...p, why_do_it: e.currentTarget.value }))}
              />
              <TextInput
                label="YouTube URL"
                placeholder="https://www.youtube.com/watch?v=..."
                value={formData.video_url || ''}
                error={(formData.video_url || '').trim() && !validateYoutubeUrl(formData.video_url) ? 'Use a valid YouTube URL' : undefined}
                onChange={(e) => setFormData((p) => ({ ...p, video_url: e.currentTarget.value }))}
              />
            </Stack>
          </Paper>

          <Divider mt="md" />

          <Group justify="flex-end">
            <Button
              variant="default"
              onClick={() => {
                setShowAddForm(false)
                setIsEditing(null)
              }}
            >
              Cancel
            </Button>
            <Button onClick={handleSave}>
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
            >
              {categoryExercises.map((exercise) => (
                <Accordion.Item key={exercise.id} value={exercise.id}>
                  <Accordion.Control>
                    <Group gap="sm" wrap="nowrap">
                      <Text fw={500}>{exercise.name}</Text>
                      <Badge variant="light" color="gray" size="sm">
                        {EQUIPMENT_LABELS[exercise.equipment]}
                      </Badge>
                      {exercise.fatigue_profile && (
                        <Badge variant="light" color="blue" size="sm">
                          {exercise.fatigue_profile_source === 'ai_estimated' ? 'AI FP' : 'Manual FP'}
                        </Badge>
                      )}
                      {exercise.e1rm_estimate && (
                        <Badge variant="filled" color="green" size="sm">
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
                          leftSection={<Edit2 size={12} />}
                          onClick={() => startEdit(exercise)}
                        >
                          Edit
                        </Button>
                        <Button
                          size="compact-sm"
                          variant="light"
                          color="red"
                          leftSection={<Trash2 size={12} />}
                          onClick={() => handleDelete(exercise.id)}
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
