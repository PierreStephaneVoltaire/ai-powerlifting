import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { differenceInCalendarDays, parse } from 'date-fns'
import { useProgramStore } from '@/store/programStore'
import { useSettingsStore } from '@/store/settingsStore'
import { useUiStore } from '@/store/uiStore'
import { fetchWeightLog, updateMetaField, reviewLiftProfile, rewriteLiftProfile, estimateLiftProfileStimulus, type LiftProfileReview } from '@/api/client'
import { fetchBlockAnalysis, fetchProgramBlocks, type BlockAnalysisBundle, type WeeklyAnalysis } from '@/api/analytics'
import { daysUntil } from '@/utils/dates'
import { displayWeight, toDisplayUnit, fromDisplayUnit } from '@/utils/units'
import { phaseColor, phasesForBlock } from '@/utils/phases'
import { Activity, Target, Scale, Trophy, TrendingUp, Edit2, Save, X, Plus, Trash2, Download, Dumbbell, Ruler, Sparkles, HeartPulse } from 'lucide-react'
import {
  Stack,
  Group,
  Text,
  Paper,
  SimpleGrid,
  Button,
  ActionIcon,
  TextInput,
  Textarea,
  SegmentedControl,
  Progress,
  Badge,
  Loader,
  Box,
  Modal,
  Alert,
  Divider,
  Table,
} from '@mantine/core'
import type { Phase, WeightEntry, LiftProfile, Session, SessionWellness } from '@powerlifting/types'

const LIFT_ORDER = ['squat', 'bench', 'deadlift'] as const
const PROFILE_ESTIMATE_READY_SCORE = 55
const LIFT_ALIASES: Record<LiftProfile['lift'], string[]> = {
  squat: ['squat'],
  bench: ['bench'],
  deadlift: ['deadlift'],
}

const LIFT_LABELS: Record<LiftProfile['lift'], string> = {
  squat: 'Squat',
  bench: 'Bench',
  deadlift: 'Deadlift',
}

const LIFT_STYLE_PLACEHOLDERS: Record<LiftProfile['lift'], string> = {
  squat: 'e.g. High bar, hip width stance, knees track over toes, upright torso. Belt squat occasionally for back relief.',
  bench: 'e.g. Close grip for ROM, moderate arch, explosive leg drive, bar slightly below nipples, let bar sink slightly before explode.',
  deadlift: 'e.g. Conventional, double overhand / mixed grip at heavy, slight wedge off floor, lockout hip drive.',
}

const STICKING_PLACEHOLDERS: Record<LiftProfile['lift'], string> = {
  squat: 'e.g. Out of the hole just below parallel, hamstring activation drops',
  bench: 'e.g. Off the chest - initial drive phase, first 2-3 inches',
  deadlift: 'e.g. Below the knee transitioning off the floor, hip-hinge not engaged early enough',
}

const DEFAULT_PROFILE = (lift: LiftProfile['lift']): LiftProfile => ({
  lift,
  style_notes: '',
  sticking_points: '',
  primary_muscle: '',
  volume_tolerance: 'moderate',
  stimulus_coefficient: 1,
})

const normalizeLiftProfile = (profile: LiftProfile): LiftProfile => ({
  ...DEFAULT_PROFILE(profile.lift),
  ...profile,
  stimulus_coefficient: Math.max(1, Math.min(2, profile.stimulus_coefficient ?? 1)),
})

const mergeLiftProfiles = (profiles: LiftProfile[] = []): LiftProfile[] =>
  LIFT_ORDER.map(lift => normalizeLiftProfile(profiles.find(p => p.lift === lift) ?? DEFAULT_PROFILE(lift)))

const coefficientValue = (value: string | number): number =>
  typeof value === 'number' && Number.isFinite(value) ? Math.max(1, Math.min(2, value)) : 1

const WELLNESS_METRICS: Array<{ key: keyof Omit<SessionWellness, 'recorded_at'>; label: string }> = [
  { key: 'sleep', label: 'Sleep' },
  { key: 'soreness', label: 'Soreness' },
  { key: 'mood', label: 'Mood' },
  { key: 'stress', label: 'Stress' },
  { key: 'energy', label: 'Energy' },
]

function averageWellness(wellness?: SessionWellness | null): number | null {
  if (!wellness) return null
  const values = WELLNESS_METRICS.map(({ key }) => wellness[key]).filter((value) => typeof value === 'number') as number[]
  if (values.length === 0) return null
  return values.reduce((sum, value) => sum + value, 0) / values.length
}

function buildWellnessTrend(sessions: Session[]): {
  buckets: { label: string; average: number | null; count: number }[]
  overallAverage: number | null
  metricAverages: Record<keyof Omit<SessionWellness, 'recorded_at'>, number | null>
} {
  const today = new Date()
  const buckets = [
    { label: '4w ago', total: 0, count: 0 },
    { label: '3w ago', total: 0, count: 0 },
    { label: '2w ago', total: 0, count: 0 },
    { label: 'This week', total: 0, count: 0 },
  ]
  const metricTotals = WELLNESS_METRICS.reduce((acc, { key }) => {
    acc[key] = { total: 0, count: 0 }
    return acc
  }, {} as Record<keyof Omit<SessionWellness, 'recorded_at'>, { total: number; count: number }>)
  let overallTotal = 0
  let overallCount = 0

  for (const session of sessions) {
    const sessionAverage = averageWellness(session.wellness)
    if (sessionAverage === null) continue
    const sessionDate = parse(session.date, 'yyyy-MM-dd', new Date())
    const daysAgo = differenceInCalendarDays(today, sessionDate)
    if (daysAgo < 0 || daysAgo >= 28) continue
    const bucketIndex = 3 - Math.min(3, Math.floor(daysAgo / 7))
    buckets[bucketIndex].total += sessionAverage
    buckets[bucketIndex].count += 1
    overallTotal += sessionAverage
    overallCount += 1

    const wellness = session.wellness
    if (!wellness) continue
    for (const { key } of WELLNESS_METRICS) {
      const value = wellness[key]
      if (typeof value !== 'number') continue
      metricTotals[key].total += value
      metricTotals[key].count += 1
    }
  }

  return {
    buckets: buckets.map((bucket) => ({
      label: bucket.label,
      average: bucket.count > 0 ? bucket.total / bucket.count : null,
      count: bucket.count,
    })),
    overallAverage: overallCount > 0 ? overallTotal / overallCount : null,
    metricAverages: WELLNESS_METRICS.reduce((acc, { key }) => {
      const total = metricTotals[key].total
      const count = metricTotals[key].count
      acc[key] = count > 0 ? total / count : null
      return acc
    }, {} as Record<keyof Omit<SessionWellness, 'recorded_at'>, number | null>),
  }
}

function fatigueBadgeColor(score: number | null): string {
  if (score === null) return 'gray'
  if (score >= 0.65) return 'red'
  if (score >= 0.45) return 'orange'
  if (score >= 0.25) return 'yellow'
  return 'green'
}

function fatigueLabel(score: number | null): string {
  if (score === null) return 'N/A'
  if (score >= 0.65) return 'Very High'
  if (score >= 0.45) return 'High'
  if (score >= 0.25) return 'Moderate'
  return 'Low'
}

function formatSignedKg(deltaKg: number | null | undefined, unit: 'kg' | 'lb'): string {
  if (typeof deltaKg !== 'number' || !Number.isFinite(deltaKg)) return '--'
  const value = displayWeight(Math.abs(deltaKg), unit)
  return `${deltaKg >= 0 ? '+' : '-'}${value}`
}

function findLiftAnalysis(weekly: WeeklyAnalysis | null, lift: LiftProfile['lift']) {
  if (!weekly) return undefined
  const exact = weekly.lifts?.[lift]
  if (exact) return exact
  return Object.entries(weekly.lifts ?? {}).find(([name]) => {
    const lowerName = name.toLowerCase()
    return LIFT_ALIASES[lift].some((alias) => lowerName.includes(alias))
  })?.[1]
}

export default function Dashboard() {
  const { program, version, isLoading, updateMaxes, updateBodyWeight, updatePhases, updateLiftProfiles } = useProgramStore()
  const { unit } = useSettingsStore()
  const { pushToast } = useUiStore()

  const [editingMaxes, setEditingMaxes] = useState(false)
  const [editingWeight, setEditingWeight] = useState(false)
  const [editingPhases, setEditingPhases] = useState(false)
  const [editingLiftProfiles, setEditingLiftProfiles] = useState(false)
  const [localMaxes, setLocalMaxes] = useState({ squat: 0, bench: 0, deadlift: 0 })
  const [localWeight, setLocalWeight] = useState(0)
  const [localPhases, setLocalPhases] = useState<Phase[]>([])
  const [localLiftProfiles, setLocalLiftProfiles] = useState<LiftProfile[]>([])
  const [weightLog, setWeightLog] = useState<WeightEntry[]>([])
  const [editingMeasurements, setEditingMeasurements] = useState(false)
  const [localHeight, setLocalHeight] = useState<number | ''>('')
  const [localWingspan, setLocalWingspan] = useState<number | ''>('')
  const [localLegLength, setLocalLegLength] = useState<number | ''>('')
  const [profileGuideOpen, setProfileGuideOpen] = useState(false)
  const [profileGuideDraft, setProfileGuideDraft] = useState<LiftProfile | null>(null)
  const [profileGuideReview, setProfileGuideReview] = useState<LiftProfileReview | null>(null)
  const [profileGuideLoading, setProfileGuideLoading] = useState(false)
  const [profileGuideRewriting, setProfileGuideRewriting] = useState(false)
  const [profileGuideEstimating, setProfileGuideEstimating] = useState(false)
  const [currentBlockBundle, setCurrentBlockBundle] = useState<BlockAnalysisBundle | null>(null)
  const [currentBlockLoading, setCurrentBlockLoading] = useState(false)
  const [currentBlockCacheMissing, setCurrentBlockCacheMissing] = useState(false)

  useEffect(() => {
    if (version) {
      fetchWeightLog(version)
        .then(setWeightLog)
        .catch((e) => console.error('Failed to load weight log:', e))
    }
  }, [version])

  useEffect(() => {
    if (program?.lift_profiles) {
      setLocalLiftProfiles(mergeLiftProfiles(program.lift_profiles))
    } else {
      setLocalLiftProfiles(mergeLiftProfiles())
    }
  }, [program?.lift_profiles])

  useEffect(() => {
    let cancelled = false

    if (!version) {
      setCurrentBlockBundle(null)
      setCurrentBlockCacheMissing(false)
      return
    }

    setCurrentBlockLoading(true)
    setCurrentBlockCacheMissing(false)

    fetchProgramBlocks()
      .then((blocks) => {
        const currentBlock = blocks.find((block) => block.isCurrent)
        if (!currentBlock?.cacheStatus?.cached) {
          if (!cancelled) {
            setCurrentBlockBundle(null)
            setCurrentBlockCacheMissing(true)
          }
          return null
        }
        return fetchBlockAnalysis(currentBlock.blockKey, false, true)
      })
      .then((bundle) => {
        if (!cancelled && bundle) {
          setCurrentBlockBundle(bundle)
          setCurrentBlockCacheMissing(false)
        }
      })
      .catch((error) => {
        console.warn('Failed to load cached current block analysis:', error)
        if (!cancelled) {
          setCurrentBlockBundle(null)
          setCurrentBlockCacheMissing(true)
        }
      })
      .finally(() => {
        if (!cancelled) setCurrentBlockLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [version])

  if (isLoading || !program) {
    return (
      <Group justify="center" mih="50vh">
        <Loader />
      </Group>
    )
  }

  const { meta, sessions, phases, competitions } = program
  const currentBlockPhases = phasesForBlock(phases)

  const upcomingComps = competitions
    .filter((c) => c.status !== 'skipped' && new Date(c.date) >= new Date())
    .sort((a, b) => a.date.localeCompare(b.date))

  const latestWeightKg = weightLog.length > 0 ? weightLog[0].kg : meta.current_body_weight_kg

  const actualMaxes = { squat: 0, bench: 0, deadlift: 0 }
  for (const session of sessions) {
    if (!session.completed) continue
    if ((session.block || 'current') !== 'current') continue
    for (const exercise of session.exercises) {
      if (exercise.kg == null) continue
      const name = exercise.name.toLowerCase()
      if (name.includes('squat') && exercise.kg > actualMaxes.squat) actualMaxes.squat = exercise.kg
      if (name.includes('bench') && exercise.kg > actualMaxes.bench) actualMaxes.bench = exercise.kg
      if (name.includes('deadlift') && exercise.kg > actualMaxes.deadlift) actualMaxes.deadlift = exercise.kg
    }
  }

  const wellnessTrend = buildWellnessTrend(sessions)

  const startEditingMaxes = () => {
    setLocalMaxes({ squat: meta.target_squat_kg, bench: meta.target_bench_kg, deadlift: meta.target_dl_kg })
    setEditingMaxes(true)
  }

  const saveMaxes = async () => {
    try {
      await updateMaxes({ squat_kg: localMaxes.squat, bench_kg: localMaxes.bench, deadlift_kg: localMaxes.deadlift })
      pushToast({ message: 'Target maxes updated', type: 'success' })
      setEditingMaxes(false)
    } catch (err) {
      pushToast({ message: 'Failed to update maxes', type: 'error' })
    }
  }

  const startEditingWeight = () => {
    setLocalWeight(latestWeightKg)
    setEditingWeight(true)
  }

  const saveWeight = async () => {
    try {
      await updateBodyWeight(localWeight)
      pushToast({ message: 'Body weight updated', type: 'success' })
      setEditingWeight(false)
    } catch (err) {
      pushToast({ message: 'Failed to update weight', type: 'error' })
    }
  }

  const startEditingMeasurements = () => {
    setLocalHeight(meta.height_cm ?? '')
    setLocalWingspan(meta.arm_wingspan_cm ?? '')
    setLocalLegLength(meta.leg_length_cm ?? '')
    setEditingMeasurements(true)
  }

  const saveMeasurements = async () => {
    try {
      await Promise.all([
        updateMetaField(version, 'height_cm', localHeight === '' ? null : localHeight),
        updateMetaField(version, 'arm_wingspan_cm', localWingspan === '' ? null : localWingspan),
        updateMetaField(version, 'leg_length_cm', localLegLength === '' ? null : localLegLength),
      ])
      await useProgramStore.getState().loadProgram(version)
      pushToast({ message: 'Measurements updated', type: 'success' })
      setEditingMeasurements(false)
    } catch (err) {
      pushToast({ message: 'Failed to update measurements', type: 'error' })
    }
  }

  const startEditingPhases = () => {
    setLocalPhases([...currentBlockPhases])
    setEditingPhases(true)
  }

  const savePhases = async () => {
    try {
      await updatePhases(localPhases, 'current')
      pushToast({ message: 'Phases updated', type: 'success' })
      setEditingPhases(false)
    } catch (err) {
      pushToast({ message: 'Failed to update phases', type: 'error' })
    }
  }

  const updatePhase = (index: number, field: keyof Phase, value: string | number) => {
    setLocalPhases(prev => {
      const updated = [...prev]
      updated[index] = { ...updated[index], [field]: value }
      return updated
    })
  }

  const addPhase = () => {
    const lastPhase = localPhases[localPhases.length - 1]
    const newStart = lastPhase ? lastPhase.end_week + 1 : 1
    setLocalPhases(prev => [...prev, { name: 'New Phase', intent: '', start_week: newStart, end_week: newStart + 3, block: 'current' }])
  }

  const removePhase = (index: number) => setLocalPhases(prev => prev.filter((_, i) => i !== index))

  const startEditingLiftProfiles = () => {
    setLocalLiftProfiles(mergeLiftProfiles(program?.lift_profiles))
    setEditingLiftProfiles(true)
  }

  const saveLiftProfiles = async () => {
    try {
      await updateLiftProfiles(localLiftProfiles)
      pushToast({ message: 'Lift profiles saved', type: 'success' })
      setEditingLiftProfiles(false)
    } catch (err) {
      pushToast({ message: 'Failed to save lift profiles', type: 'error' })
    }
  }

  const updateLocalProfile = (lift: LiftProfile['lift'], updates: Partial<LiftProfile>) => {
    setLocalLiftProfiles(prev =>
      prev.map(p => p.lift === lift ? { ...p, ...updates } : p)
    )
  }

  const reviewProfileDraft = async (profile: LiftProfile) => {
    setProfileGuideLoading(true)
    try {
      const review = await reviewLiftProfile(profile)
      setProfileGuideReview(review)
    } catch (err) {
      pushToast({ message: 'AI profile review failed', type: 'error' })
    } finally {
      setProfileGuideLoading(false)
    }
  }

  const openProfileGuide = async (profile: LiftProfile) => {
    const merged = mergeLiftProfiles(localLiftProfiles.length ? localLiftProfiles : program?.lift_profiles)
    const draft = normalizeLiftProfile(merged.find(p => p.lift === profile.lift) ?? profile)
    const shouldAutoReview = Math.abs((draft.stimulus_coefficient ?? 1) - 1) < 0.001
    setLocalLiftProfiles(merged)
    setEditingLiftProfiles(true)
    setProfileGuideDraft(draft)
    setProfileGuideReview(null)
    setProfileGuideOpen(true)
    if (shouldAutoReview) {
      await reviewProfileDraft(draft)
    }
  }

  const updateProfileGuideDraft = (updates: Partial<LiftProfile>) => {
    setProfileGuideDraft(prev => prev ? { ...prev, ...updates } : prev)
  }

  const runProfileGuideReview = async () => {
    if (!profileGuideDraft) return
    await reviewProfileDraft(profileGuideDraft)
  }

  const runRewriteProfile = async () => {
    if (!profileGuideDraft) return
    setProfileGuideRewriting(true)
    try {
      const result = await rewriteLiftProfile(profileGuideDraft)
      const updated = normalizeLiftProfile({ ...profileGuideDraft, ...result })
      setProfileGuideDraft(updated)
      updateLocalProfile(updated.lift, updated)
      await reviewProfileDraft(updated)
      pushToast({ message: 'Lift profile rewritten', type: 'success' })
    } catch (err) {
      pushToast({ message: 'AI rewrite failed', type: 'error' })
    } finally {
      setProfileGuideRewriting(false)
    }
  }

  const runEstimateStimulus = async () => {
    if (!profileGuideDraft) return
    const score = profileGuideReview?.completeness_score ?? 0
    if (score < PROFILE_ESTIMATE_READY_SCORE) {
      pushToast({ message: `Profile score needs ${PROFILE_ESTIMATE_READY_SCORE}% before estimating stimulus`, type: 'error' })
      return
    }
    setProfileGuideEstimating(true)
    try {
      const result = await estimateLiftProfileStimulus(profileGuideDraft)
      const updated = normalizeLiftProfile({
        ...profileGuideDraft,
        stimulus_coefficient: result.stimulus_coefficient,
        stimulus_coefficient_confidence: result.stimulus_coefficient_confidence,
        stimulus_coefficient_reasoning: result.stimulus_coefficient_reasoning,
        stimulus_coefficient_updated_at: result.stimulus_coefficient_updated_at,
      })
      setProfileGuideDraft(updated)
      updateLocalProfile(updated.lift, updated)
      pushToast({ message: 'Stimulus coefficient applied', type: 'success' })
    } catch (err) {
      pushToast({ message: 'AI stimulus estimate failed', type: 'error' })
    } finally {
      setProfileGuideEstimating(false)
    }
  }

  const applyProfileGuide = () => {
    if (!profileGuideDraft) return
    updateLocalProfile(profileGuideDraft.lift, profileGuideDraft)
    setProfileGuideOpen(false)
    pushToast({ message: 'Profile staged. Save lift profiles to persist it.', type: 'success' })
  }

  const displayProfiles = (program?.lift_profiles?.length
    ? mergeLiftProfiles(program.lift_profiles)
    : mergeLiftProfiles()
  )
  const profileGuideScore = profileGuideReview?.completeness_score ?? 0
  const profileGuideCanEstimate = profileGuideScore >= PROFILE_ESTIMATE_READY_SCORE
  const currentBlockWeekly = currentBlockBundle?.weekly ?? null
  const currentBlockFatigue = currentBlockWeekly?.fatigue_index ?? null
  const liftBreakdownRows = LIFT_ORDER.map((lift) => {
    const liftAnalysis = findLiftAnalysis(currentBlockWeekly, lift)
    const endStrength = currentBlockBundle?.historical.endStrength[lift] ?? currentBlockWeekly?.current_maxes?.[lift] ?? null
    return {
      lift,
      endStrength,
      progressionRate: liftAnalysis?.progression_rate_kg_per_week ?? null,
    }
  })

  return (
    <Stack gap={24}>
      <Group justify="space-between">
        <Text fz="h1" fw={700}>Dashboard</Text>
        <Group gap="sm" wrap="wrap">
          <Button
            component="a"
            href="/api/export/xlsx"
            download="program_history.xlsx"
            leftSection={<Download size={16} />}
            size="sm"
          >
            Export Excel
          </Button>
          <Button
            component="a"
            href="/api/export/markdown"
            download="program_history.md"
            leftSection={<Download size={16} />}
            size="sm"
            variant="light"
          >
            Export Markdown
          </Button>
        </Group>
      </Group>

      {/* Stats Grid */}
      <SimpleGrid cols={{ base: 1, md: 2, lg: 3 }} spacing="md">
        {/* Upcoming Competitions */}
        {upcomingComps.length > 0 && (
          <Paper withBorder p="md">
            <Group gap="xs" mb="sm">
              <Trophy size={20} />
              <Text fw={500}>Upcoming Competitions</Text>
            </Group>
            <Stack gap="xs">
              {upcomingComps.map((comp) => (
                <Group key={comp.date} justify="space-between">
                  <Group gap="xs" style={{ minWidth: 0 }}>
                    <Badge
                      variant="light"
                      color={comp.status === 'confirmed' ? 'green' : 'yellow'}
                      size="sm"
                    >
                      {comp.status}
                    </Badge>
                    <Text size="sm" truncate>{comp.name}</Text>
                  </Group>
                  <Text size="sm" fw={500} ml="xs">{daysUntil(comp.date)}d</Text>
                </Group>
              ))}
            </Stack>
          </Paper>
        )}

        {/* Target Maxes */}
        <Paper withBorder p="md">
          <Group justify="space-between" mb="sm">
            <Group gap="xs">
              <Target size={20} />
              <Text fw={500}>Target Maxes</Text>
            </Group>
            {editingMaxes ? (
              <Group gap={4}>
                <ActionIcon variant="subtle" color="blue" onClick={saveMaxes}><Save size={16} /></ActionIcon>
                <ActionIcon variant="subtle" onClick={() => setEditingMaxes(false)}><X size={16} /></ActionIcon>
              </Group>
            ) : (
              <ActionIcon variant="subtle" onClick={startEditingMaxes}><Edit2 size={16} /></ActionIcon>
            )}
          </Group>
          {editingMaxes ? (
            <Stack gap="xs">
              {(['squat', 'bench', 'deadlift'] as const).map((lift) => (
                <Group key={lift} gap="xs">
                  <Text size="sm" w={64} tt="capitalize">{lift}</Text>
                  <TextInput
                    type="number"
                    style={{ flex: 1 }}
                    value={toDisplayUnit(localMaxes[lift], unit)}
                    onChange={(e) => setLocalMaxes(prev => ({ ...prev, [lift]: fromDisplayUnit(Number(e.currentTarget.value) || 0, unit) }))}
                    size="sm"
                  />
                  <Text size="xs" c="dimmed">{unit}</Text>
                </Group>
              ))}
              <Group justify="space-between" style={{ borderTop: '1px solid var(--mantine-color-default-border)' }} pt={4} mt={4}>
                <Text size="sm" fw={500}>Total</Text>
                <Text size="sm" fw={700}>{displayWeight(localMaxes.squat + localMaxes.bench + localMaxes.deadlift, unit)}</Text>
              </Group>
            </Stack>
          ) : (
            <Stack gap={4}>
              <Group justify="space-between"><Text size="sm">Squat</Text><Text size="sm" fw={500}>{displayWeight(meta.target_squat_kg, unit)}</Text></Group>
              <Group justify="space-between"><Text size="sm">Bench</Text><Text size="sm" fw={500}>{displayWeight(meta.target_bench_kg, unit)}</Text></Group>
              <Group justify="space-between"><Text size="sm">Deadlift</Text><Text size="sm" fw={500}>{displayWeight(meta.target_dl_kg, unit)}</Text></Group>
              <Group justify="space-between" style={{ borderTop: '1px solid var(--mantine-color-default-border)' }} pt={4} mt={4}>
                <Text size="sm" fw={500}>Total</Text>
                <Text size="sm" fw={700}>{displayWeight(meta.target_total_kg, unit)}</Text>
              </Group>
            </Stack>
          )}
        </Paper>

        {/* Actual Maxes */}
        {(actualMaxes.squat > 0 || actualMaxes.bench > 0 || actualMaxes.deadlift > 0) && (
          <Paper withBorder p="md">
            <Group gap="xs" mb="sm">
              <TrendingUp size={20} />
              <Text fw={500}>Actual Maxes</Text>
            </Group>
            <Stack gap="xs">
              {[
                { label: 'Squat', actual: actualMaxes.squat, target: meta.target_squat_kg },
                { label: 'Bench', actual: actualMaxes.bench, target: meta.target_bench_kg },
                { label: 'Deadlift', actual: actualMaxes.deadlift, target: meta.target_dl_kg },
              ].map(({ label, actual, target }) =>
                actual > 0 ? (
                  <Box key={label}>
                    <Group justify="space-between" mb={2}>
                      <Text size="sm">{label}: {displayWeight(actual, unit)}</Text>
                      <Text size="sm" c="dimmed">Target: {displayWeight(target, unit)}</Text>
                    </Group>
                    <Progress
                      value={Math.min(100, (actual / target) * 100)}
                      color={actual >= target ? 'green' : 'blue'}
                      size="sm"
                    />
                  </Box>
                ) : null
              )}
              {(actualMaxes.squat > 0 || actualMaxes.bench > 0 || actualMaxes.deadlift > 0) && (
                <Group justify="space-between" style={{ borderTop: '1px solid var(--mantine-color-default-border)' }} pt={4} mt={4}>
                  <Text size="sm" fw={500}>Total</Text>
                  <Text size="sm" fw={700}>{displayWeight(actualMaxes.squat + actualMaxes.bench + actualMaxes.deadlift, unit)}</Text>
                </Group>
              )}
            </Stack>
          </Paper>
        )}

        {/* Body Weight */}
        <Paper withBorder p="md">
          <Group justify="space-between" mb="sm">
            <Group gap="xs">
              <Scale size={20} />
              <Text fw={500}>Body Weight</Text>
            </Group>
            {editingWeight ? (
              <Group gap={4}>
                <ActionIcon variant="subtle" color="blue" onClick={saveWeight}><Save size={16} /></ActionIcon>
                <ActionIcon variant="subtle" onClick={() => setEditingWeight(false)}><X size={16} /></ActionIcon>
              </Group>
            ) : (
              <ActionIcon variant="subtle" onClick={startEditingWeight}><Edit2 size={16} /></ActionIcon>
            )}
          </Group>
          {editingWeight ? (
            <Group gap="xs">
              <TextInput
                type="number"
                style={{ flex: 1 }}
                value={toDisplayUnit(localWeight, unit)}
                onChange={(e) => setLocalWeight(fromDisplayUnit(Number(e.currentTarget.value) || 0, unit))}
                size="lg"
              />
              <Text size="sm" c="dimmed">{unit}</Text>
            </Group>
          ) : (
            <Text fz="h1" fw={700}>{displayWeight(latestWeightKg, unit)}</Text>
          )}
          <Text size="sm" c="dimmed">Target: {meta.weight_class_kg} kg class</Text>
          <Progress
            value={Math.min(100, (latestWeightKg / meta.weight_class_kg) * 100)}
            mt="sm"
            size="md"
          />
        </Paper>

        <Paper withBorder p="md">
          <Group justify="space-between" mb="sm" align="flex-start">
            <Group gap="xs">
              <HeartPulse size={20} />
              <Text fw={500}>Subjective Wellness</Text>
            </Group>
            {wellnessTrend.overallAverage !== null && (
              <Text size="xs" c="dimmed">
                {wellnessTrend.overallAverage.toFixed(1)} / 5 avg
              </Text>
            )}
          </Group>
          {wellnessTrend.overallAverage !== null ? (
            <Stack gap="xs">
              <SimpleGrid cols={4} spacing="xs">
                {wellnessTrend.buckets.map((bucket) => {
                  const average = bucket.average
                  const color = average === null ? 'gray' : average >= 4 ? 'green' : average >= 3 ? 'yellow' : 'red'
                  return (
                    <Stack key={bucket.label} gap={4}>
                      <Text size="xs" c="dimmed">{bucket.label}</Text>
                      <Progress value={average !== null ? (average / 5) * 100 : 0} color={color} size="sm" />
                      <Text size="xs" fw={500}>{average !== null ? average.toFixed(1) : '—'}</Text>
                    </Stack>
                  )
                })}
              </SimpleGrid>
              <Text size="xs" c="dimmed">Higher is better. Soreness is reversed in readiness math.</Text>
              <SimpleGrid cols={{ base: 2, sm: 5 }} spacing="xs" mt="xs">
                {WELLNESS_METRICS.map(({ key, label }) => {
                  const average = wellnessTrend.metricAverages[key]
                  const color = average === null ? 'gray' : average >= 4 ? 'green' : average >= 3 ? 'yellow' : 'red'
                  return (
                    <Stack key={key} gap={4}>
                      <Text size="xs" c="dimmed">{label} avg</Text>
                      <Progress value={average !== null ? (average / 5) * 100 : 0} color={color} size="sm" />
                      <Text size="xs" fw={500}>{average !== null ? average.toFixed(1) : '—'}</Text>
                    </Stack>
                  )
                })}
              </SimpleGrid>
            </Stack>
          ) : (
            <Text size="sm" c="dimmed">No wellness entries yet.</Text>
          )}
        </Paper>

        {/* Anthropometrics */}
        <Paper withBorder p="md">
          <Group justify="space-between" mb="sm">
            <Group gap="xs">
              <Ruler size={20} />
              <Text fw={500}>Anthropometrics</Text>
            </Group>
            {editingMeasurements ? (
              <Group gap={4}>
                <ActionIcon variant="subtle" color="blue" onClick={saveMeasurements}><Save size={16} /></ActionIcon>
                <ActionIcon variant="subtle" onClick={() => setEditingMeasurements(false)}><X size={16} /></ActionIcon>
              </Group>
            ) : (
              <ActionIcon variant="subtle" onClick={startEditingMeasurements}><Edit2 size={16} /></ActionIcon>
            )}
          </Group>
          {editingMeasurements ? (
            <Stack gap="xs">
              <Group gap="xs">
                <Text size="sm" w={96}>Height</Text>
                <TextInput
                  type="number"
                  style={{ flex: 1 }}
                  value={localHeight}
                  onChange={(e) => setLocalHeight(e.currentTarget.value ? Number(e.currentTarget.value) : '')}
                  placeholder="--"
                  size="sm"
                />
                <Text size="xs" c="dimmed">cm</Text>
              </Group>
              <Group gap="xs">
                <Text size="sm" w={96}>Arm Wingspan</Text>
                <TextInput
                  type="number"
                  style={{ flex: 1 }}
                  value={localWingspan}
                  onChange={(e) => setLocalWingspan(e.currentTarget.value ? Number(e.currentTarget.value) : '')}
                  placeholder="--"
                  size="sm"
                />
                <Text size="xs" c="dimmed">cm</Text>
              </Group>
              <Group gap="xs">
                <Text size="sm" w={96}>Leg Length</Text>
                <TextInput
                  type="number"
                  style={{ flex: 1 }}
                  value={localLegLength}
                  onChange={(e) => setLocalLegLength(e.currentTarget.value ? Number(e.currentTarget.value) : '')}
                  placeholder="--"
                  size="sm"
                />
                <Text size="xs" c="dimmed">cm</Text>
              </Group>
            </Stack>
          ) : (
            <Stack gap={4}>
              <Group justify="space-between">
                <Text size="sm">Height</Text>
                <Text size="sm" fw={500}>{meta.height_cm ? `${meta.height_cm} cm` : 'Not set'}</Text>
              </Group>
              <Group justify="space-between">
                <Text size="sm">Arm Wingspan</Text>
                <Text size="sm" fw={500}>{meta.arm_wingspan_cm ? `${meta.arm_wingspan_cm} cm` : 'Not set'}</Text>
              </Group>
              <Group justify="space-between">
                <Text size="sm">Leg Length</Text>
                <Text size="sm" fw={500}>{meta.leg_length_cm ? `${meta.leg_length_cm} cm` : 'Not set'}</Text>
              </Group>
            </Stack>
          )}
        </Paper>

        {/* Current Fatigue State */}
        {!currentBlockCacheMissing && (
          <Paper withBorder p="md">
            <Group justify="space-between" mb="sm" align="flex-start">
              <Group gap="xs">
                <HeartPulse size={20} />
                <Text fw={500}>Current Fatigue State</Text>
              </Group>
              {currentBlockBundle?.cached && <Badge color="blue" variant="light" size="sm">Cached</Badge>}
            </Group>
            {currentBlockLoading ? (
              <Group gap="xs">
                <Loader size="sm" />
                <Text size="sm" c="dimmed">Loading cached block analysis...</Text>
              </Group>
            ) : currentBlockWeekly ? (
              <Stack gap="xs">
                <Group justify="space-between" align="flex-end">
                  <Stack gap={0}>
                    <Text fz="h1" fw={700} c={fatigueBadgeColor(currentBlockFatigue)}>
                      {currentBlockFatigue !== null ? `${(currentBlockFatigue * 100).toFixed(0)}%` : 'N/A'}
                    </Text>
                    <Text size="sm" c="dimmed">{fatigueLabel(currentBlockFatigue)} current state</Text>
                  </Stack>
                  <Text size="xs" c="dimmed" ta="right">
                    {currentBlockBundle?.block.startDate} to {currentBlockBundle?.block.endDate}
                  </Text>
                </Group>
                <Group gap={6} wrap="wrap">
                  {typeof currentBlockWeekly.fatigue_components?.window_mean_fi === 'number' && (
                    <Badge variant="light" color="blue">
                      Mean {(currentBlockWeekly.fatigue_components.window_mean_fi * 100).toFixed(0)}%
                    </Badge>
                  )}
                  {typeof currentBlockWeekly.fatigue_components?.window_peak_fi === 'number' && (
                    <Badge variant="light" color="orange">
                      Peak {(currentBlockWeekly.fatigue_components.window_peak_fi * 100).toFixed(0)}%
                    </Badge>
                  )}
                  {currentBlockWeekly.fatigue_components?.fatigue_context_confidence && (
                    <Badge variant="light" color="gray">
                      {currentBlockWeekly.fatigue_components.fatigue_context_confidence} confidence
                    </Badge>
                  )}
                </Group>
                <Text fz="xs" c="dimmed" lh="lg">
                  Failures {((currentBlockWeekly.fatigue_components?.failure_stress ?? 0) * 100).toFixed(0)}%
                  {' '}· Spike {((currentBlockWeekly.fatigue_components?.acute_spike_stress ?? 0) * 100).toFixed(0)}%
                  {' '}· RPE {((currentBlockWeekly.fatigue_components?.rpe_stress ?? 0) * 100).toFixed(0)}%
                  {' '}· Reservoir {((currentBlockWeekly.fatigue_components?.chronic_load_stress ?? 0) * 100).toFixed(0)}%
                  {' '}· Strain {((currentBlockWeekly.fatigue_components?.monotony_stress ?? 0) * 100).toFixed(0)}%
                </Text>
              </Stack>
            ) : (
              <Text size="sm" c="dimmed">
                Cached block analysis unavailable.
              </Text>
            )}
          </Paper>
        )}

        {/* Per-Lift Breakdown */}
        {!currentBlockCacheMissing && (
          <Paper withBorder p="md" style={{ minWidth: 0 }}>
            <Group justify="space-between" mb="sm" align="flex-start">
              <Group gap="xs">
                <Activity size={20} />
                <Text fw={500}>Per-Lift Breakdown</Text>
              </Group>
              {currentBlockBundle?.cached && <Badge color="blue" variant="light" size="sm">Cached</Badge>}
            </Group>
            {currentBlockLoading ? (
              <Group gap="xs">
                <Loader size="sm" />
                <Text size="sm" c="dimmed">Loading cached lift data...</Text>
              </Group>
            ) : currentBlockWeekly ? (
              <Box style={{ overflowX: 'auto' }}>
                <Table striped highlightOnHover withTableBorder={false} withColumnBorders={false} miw={360}>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>Lift</Table.Th>
                      <Table.Th>Current</Table.Th>
                      <Table.Th>Trend</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {liftBreakdownRows.map((row) => (
                      <Table.Tr key={row.lift}>
                        <Table.Td fw={500}>{LIFT_LABELS[row.lift]}</Table.Td>
                        <Table.Td>{row.endStrength !== null ? displayWeight(row.endStrength, unit) : '--'}</Table.Td>
                        <Table.Td>
                          {typeof row.progressionRate === 'number' ? `${formatSignedKg(row.progressionRate, unit)}/wk` : '--'}
                        </Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </Box>
            ) : (
              <Text size="sm" c="dimmed">
                Cached lift breakdown unavailable.
              </Text>
            )}
          </Paper>
        )}

        {/* Program Phases */}
        <Paper withBorder p="md">
          <Group justify="space-between" mb="sm">
            <Group gap="xs">
              <TrendingUp size={20} />
              <Text fw={500}>Program Phases</Text>
            </Group>
            {editingPhases ? (
              <Group gap={4}>
                <ActionIcon variant="subtle" color="blue" onClick={addPhase}><Plus size={16} /></ActionIcon>
                <ActionIcon variant="subtle" color="blue" onClick={savePhases}><Save size={16} /></ActionIcon>
                <ActionIcon variant="subtle" onClick={() => setEditingPhases(false)}><X size={16} /></ActionIcon>
              </Group>
            ) : (
              <ActionIcon variant="subtle" onClick={startEditingPhases}><Edit2 size={16} /></ActionIcon>
            )}
          </Group>
          {editingPhases ? (
            <Stack gap="xs">
              {localPhases.map((phase, idx) => (
                <Group key={idx} gap="xs" p="xs" style={{ backgroundColor: 'var(--mantine-color-default)', borderRadius: 'var(--mantine-radius-sm)' }}>
                  <Box w={12} h={12} style={{ borderRadius: '50%', backgroundColor: phaseColor({ ...phase, block: 'current' }, localPhases) }} />
                  <TextInput
                    style={{ flex: 1 }}
                    value={phase.name}
                    onChange={(e) => updatePhase(idx, 'name', e.currentTarget.value)}
                    placeholder="Phase name"
                    size="xs"
                  />
                  <TextInput
                    type="number"
                    style={{ width: 48 }}
                    value={phase.start_week}
                    onChange={(e) => updatePhase(idx, 'start_week', Number(e.currentTarget.value) || 0)}
                    size="xs"
                  />
                  <Text size="xs">-</Text>
                  <TextInput
                    type="number"
                    style={{ width: 48 }}
                    value={phase.end_week}
                    onChange={(e) => updatePhase(idx, 'end_week', Number(e.currentTarget.value) || 0)}
                    size="xs"
                  />
                  <ActionIcon variant="subtle" color="red" onClick={() => removePhase(idx)}><Trash2 size={12} /></ActionIcon>
                </Group>
              ))}
            </Stack>
          ) : (
            <Stack gap={4}>
              {currentBlockPhases.length === 0 ? (
                <Text size="sm" c="dimmed">No phases defined for the current block.</Text>
              ) : (
                currentBlockPhases.map((phase, idx) => (
                  <Group key={idx} gap="xs">
                    <Box w={12} h={12} style={{ borderRadius: '50%', backgroundColor: phaseColor(phase, currentBlockPhases) }} />
                    <Text size="sm">W{phase.start_week}-W{phase.end_week}: {phase.name}</Text>
                  </Group>
                ))
              )}
            </Stack>
          )}
        </Paper>
      </SimpleGrid>

      {/* Lift Profiles Section */}
      <Paper withBorder p="md">
        <Group justify="space-between" mb="md">
          <Group gap="xs">
            <Dumbbell size={20} />
            <Text fw={500}>Lift Style Profiles</Text>
          </Group>
          <Group gap={4}>
            {LIFT_ORDER.map((lift) => (
              <Button
                key={lift}
                component={Link}
                to={`/lift-profiles/${lift}`}
                variant="subtle"
                size="compact-sm"
                leftSection={<Edit2 size={14} />}
              >
                {LIFT_LABELS[lift]}
              </Button>
            ))}
          </Group>
        </Group>

        {editingLiftProfiles ? (
          <SimpleGrid cols={{ base: 1, lg: 3 }} spacing="lg">
            {localLiftProfiles.map((profile) => (
              <Stack key={profile.lift} gap="sm" style={{ minWidth: 0 }}>
                <Group justify="space-between" align="center" style={{ borderBottom: '1px solid var(--mantine-color-default-border)', paddingBottom: 4 }}>
                  <Text size="sm" fw={500} tt="capitalize">{LIFT_LABELS[profile.lift]}</Text>
                  <Button
                    component={Link}
                    to={`/lift-profiles/${profile.lift}`}
                    variant="subtle"
                    size="compact-xs"
                    leftSection={<Sparkles size={12} />}
                  >
                    Open Profile
                  </Button>
                </Group>

                {/* Style Notes */}
                <Stack gap={4}>
                  <Text size="xs" c="dimmed">Style & Setup</Text>
                  <Textarea
                    rows={2}
                    value={profile.style_notes}
                    onChange={(e) => updateLocalProfile(profile.lift, { style_notes: e.currentTarget.value })}
                    placeholder={LIFT_STYLE_PLACEHOLDERS[profile.lift]}
                    size="xs"
                    styles={{ input: { maxWidth: '100%', minWidth: 0, width: '100%', overflowY: 'auto', resize: 'vertical' } }}
                  />
                </Stack>

                {/* Sticking Points */}
                <Stack gap={4}>
                  <Text size="xs" c="dimmed">Sticking Points</Text>
                  <Textarea
                    rows={2}
                    value={profile.sticking_points}
                    onChange={(e) => updateLocalProfile(profile.lift, { sticking_points: e.currentTarget.value })}
                    placeholder={STICKING_PLACEHOLDERS[profile.lift]}
                    size="xs"
                    styles={{ input: { maxWidth: '100%', minWidth: 0, width: '100%', overflowY: 'auto', resize: 'vertical' } }}
                  />
                </Stack>

                {/* Primary Muscle */}
                <Stack gap={4}>
                  <Text size="xs" c="dimmed">Primary Muscle Driving the Lift</Text>
                  <TextInput
                    value={profile.primary_muscle}
                    onChange={(e) => updateLocalProfile(profile.lift, { primary_muscle: e.currentTarget.value })}
                    placeholder={profile.lift === 'squat' ? 'e.g. Quad dominant' : profile.lift === 'bench' ? 'e.g. Tricep dominant' : 'e.g. Glute dominant'}
                    size="xs"
                  />
                </Stack>

                {/* Volume Tolerance */}
                <Stack gap={4}>
                  <Text size="xs" c="dimmed">Volume Recovery Tolerance</Text>
                  <SegmentedControl
                    fullWidth
                    size="xs"
                    data={[
                      { label: 'Low', value: 'low' },
                      { label: 'Moderate', value: 'moderate' },
                      { label: 'High', value: 'high' },
                    ]}
                    value={profile.volume_tolerance}
                    onChange={(v) => updateLocalProfile(profile.lift, { volume_tolerance: v as 'low' | 'moderate' | 'high' })}
                  />
                </Stack>

                <Stack gap={4}>
                  <Text size="xs" c="dimmed">Stimulus Coefficient</Text>
                  <TextInput
                    type="number"
                    step={0.05}
                    value={profile.stimulus_coefficient ?? 1}
                    onChange={(e) => updateLocalProfile(profile.lift, { stimulus_coefficient: coefficientValue(Number(e.currentTarget.value)) })}
                    size="xs"
                  />
                  {profile.stimulus_coefficient_reasoning && (
                    <Text size="xs" c="dimmed" lineClamp={3}>{profile.stimulus_coefficient_reasoning}</Text>
                  )}
                </Stack>
              </Stack>
            ))}
          </SimpleGrid>
        ) : (
          <SimpleGrid cols={{ base: 1, lg: 3 }} spacing="md">
            {displayProfiles.map((profile) => {
              const hasData = profile.style_notes || profile.sticking_points || profile.primary_muscle
              return (
                <Stack key={profile.lift} gap="xs" style={{ minWidth: 0 }}>
                  <Text size="sm" fw={500} tt="capitalize" style={{ borderBottom: '1px solid var(--mantine-color-default-border)', paddingBottom: 4 }}>{LIFT_LABELS[profile.lift]}</Text>
                  {hasData ? (
                    <>
                      {profile.style_notes && (
                        <div>
                          <Text size="xs" c="dimmed" mb={2}>Style</Text>
                          <Text size="xs" style={{ lineHeight: 1.6 }}>{profile.style_notes}</Text>
                        </div>
                      )}
                      {profile.sticking_points && (
                        <div>
                          <Text size="xs" c="dimmed" mb={2}>Sticking Points</Text>
                          <Text size="xs" c="orange" style={{ lineHeight: 1.6 }}>{profile.sticking_points}</Text>
                        </div>
                      )}
                      {profile.primary_muscle && (
                        <div>
                          <Text size="xs" c="dimmed" mb={2}>Primary Driver</Text>
                          <Text size="xs" fw={500}>{profile.primary_muscle}</Text>
                        </div>
                      )}
                      <Badge
                        variant="light"
                        color={profile.volume_tolerance === 'low' ? 'red' : profile.volume_tolerance === 'moderate' ? 'yellow' : 'green'}
                        size="sm"
                        tt="capitalize"
                      >
                        {profile.volume_tolerance} volume tolerance
                      </Badge>
                      <Badge variant="light" color="blue" size="sm">
                        Stimulus x{(profile.stimulus_coefficient ?? 1).toFixed(2)}
                      </Badge>
                    </>
                  ) : (
                    <Text size="xs" c="dimmed" fs="italic">No profile yet - click edit to add</Text>
                  )}
                </Stack>
              )
            })}
          </SimpleGrid>
        )}
      </Paper>

      <Modal
        opened={profileGuideOpen}
        onClose={() => setProfileGuideOpen(false)}
        title={profileGuideDraft ? `${LIFT_LABELS[profileGuideDraft.lift]} Lift Profile` : 'Lift Profile'}
        size="lg"
      >
        {profileGuideDraft && (
          <Stack gap="md">
            {profileGuideReview && (
              <Alert
                variant="light"
                color={profileGuideCanEstimate ? 'green' : 'yellow'}
                icon={<Sparkles size={16} />}
              >
                <Group justify="space-between" align="center" mb={(profileGuideReview.missing_details ?? []).length ? 'xs' : 0}>
                  <Text fw={500}>Profile score {profileGuideReview.completeness_score}%</Text>
                  <Badge color={profileGuideCanEstimate ? 'green' : 'yellow'} variant="light">
                    {profileGuideCanEstimate ? 'Estimate ready' : `Needs ${PROFILE_ESTIMATE_READY_SCORE}%`}
                  </Badge>
                </Group>
                <Text size="xs" c="dimmed" mb="xs">
                  {profileGuideReview.score_explanation ?? 'Score is 0-100 completeness for estimating a lift-specific INOL stimulus coefficient.'}
                </Text>
                {profileGuideReview.score_breakdown && (
                  <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="xs" mb="xs">
                    {Object.entries(profileGuideReview.score_breakdown).map(([key, part]) => (
                      <Paper key={key} withBorder p="xs">
                        <Text size="xs" fw={500} tt="capitalize">{key.split('_').join(' ')}</Text>
                        <Text size="sm" fw={700}>{part.score}/{part.max}</Text>
                        {(part.notes ?? []).slice(0, 2).map((note) => (
                          <Text key={note} size="xs" c="dimmed">{note}</Text>
                        ))}
                      </Paper>
                    ))}
                  </SimpleGrid>
                )}
                {(profileGuideReview.missing_details ?? []).length > 0 && (
                  <Stack gap={4}>
                    {(profileGuideReview.missing_details ?? []).map((detail) => (
                      <Text key={detail} size="xs">{detail}</Text>
                    ))}
                  </Stack>
                )}
                {(profileGuideReview.suggestions ?? []).length > 0 && (
                  <Stack gap={4} mt="xs">
                    {(profileGuideReview.suggestions ?? []).map((suggestion) => (
                      <Text key={suggestion} size="xs" c="dimmed">{suggestion}</Text>
                    ))}
                  </Stack>
                )}
              </Alert>
            )}

            <Textarea
              label="Style & Setup"
              rows={3}
              value={profileGuideDraft.style_notes}
              onChange={(e) => updateProfileGuideDraft({ style_notes: e.currentTarget.value })}
              placeholder={LIFT_STYLE_PLACEHOLDERS[profileGuideDraft.lift]}
              styles={{ input: { maxWidth: '100%', minWidth: 0, width: '100%', maxHeight: '28vh', overflowY: 'auto', resize: 'vertical' } }}
            />

            <Textarea
              label="Sticking Points"
              rows={2}
              value={profileGuideDraft.sticking_points}
              onChange={(e) => updateProfileGuideDraft({ sticking_points: e.currentTarget.value })}
              placeholder={STICKING_PLACEHOLDERS[profileGuideDraft.lift]}
              styles={{ input: { maxWidth: '100%', minWidth: 0, width: '100%', maxHeight: '24vh', overflowY: 'auto', resize: 'vertical' } }}
            />

            <TextInput
              label="Primary Muscle Driver"
              value={profileGuideDraft.primary_muscle}
              onChange={(e) => updateProfileGuideDraft({ primary_muscle: e.currentTarget.value })}
              placeholder={profileGuideDraft.lift === 'squat' ? 'Quad dominant' : profileGuideDraft.lift === 'bench' ? 'Tricep dominant' : 'Glute dominant'}
            />

            <Group grow align="flex-end">
              <SegmentedControl
                fullWidth
                data={[
                  { label: 'Low', value: 'low' },
                  { label: 'Moderate', value: 'moderate' },
                  { label: 'High', value: 'high' },
                ]}
                value={profileGuideDraft.volume_tolerance}
                onChange={(v) => updateProfileGuideDraft({ volume_tolerance: v as 'low' | 'moderate' | 'high' })}
              />
              <TextInput
                type="number"
                label="Stimulus Coefficient"
                step={0.05}
                value={profileGuideDraft.stimulus_coefficient ?? 1}
                onChange={(e) => updateProfileGuideDraft({ stimulus_coefficient: coefficientValue(Number(e.currentTarget.value)) })}
              />
            </Group>

            {profileGuideDraft.stimulus_coefficient_reasoning && (
              <Alert variant="light" color="blue">
                <Text size="sm">{profileGuideDraft.stimulus_coefficient_reasoning}</Text>
                {profileGuideDraft.stimulus_coefficient_confidence && (
                  <Badge mt="xs" variant="light" color="blue">
                    {profileGuideDraft.stimulus_coefficient_confidence} confidence
                  </Badge>
                )}
              </Alert>
            )}

            <Divider />

            <Text size="xs" c="dimmed">
              Estimate unlocks at {PROFILE_ESTIMATE_READY_SCORE}% profile score. Rewrite only cleans the text; estimate only applies the stimulus coefficient.
            </Text>

            <Group justify="space-between" gap="sm">
              <Button
                variant="light"
                leftSection={<Sparkles size={16} />}
                loading={profileGuideLoading}
                onClick={runProfileGuideReview}
              >
                Review
              </Button>
              <Group gap="sm">
                <Button
                  variant="light"
                  leftSection={<Sparkles size={16} />}
                  loading={profileGuideRewriting}
                  onClick={runRewriteProfile}
                >
                  Rewrite
                </Button>
                <Button
                  variant="light"
                  leftSection={<Sparkles size={16} />}
                  loading={profileGuideEstimating}
                  disabled={!profileGuideCanEstimate}
                  onClick={runEstimateStimulus}
                >
                  Estimate Stimulus
                </Button>
                <Button onClick={applyProfileGuide}>Apply</Button>
              </Group>
            </Group>
          </Stack>
        )}
      </Modal>
    </Stack>
  )
}
