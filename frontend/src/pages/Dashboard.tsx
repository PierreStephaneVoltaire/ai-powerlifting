import { useState, useEffect, useMemo } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { differenceInCalendarDays, format, parse } from 'date-fns'
import { useProgramStore } from '@/store/programStore'
import { useSettingsStore } from '@/store/settingsStore'
import { useUiStore } from '@/store/uiStore'
import { useCompetitionsStore } from '@/store/competitionsStore'
import { fetchWeightLog, updateMetaField, reviewLiftProfile, rewriteLiftProfile, estimateLiftProfileStimulus, fetchRankingPercentile, type LiftProfileReview, type RankingPercentileResult } from '@/api/client'
import {
  fetchAnalysisManifest,
  fetchAnalysisSection,
  queueAnalysisSections,
  type AnalysisSectionKey,
  type AnalysisWindow,
  type WeeklyAnalysis,
} from '@/api/analytics'
import { fetchCurrentProfile, type PublicProfile } from '@/api/profiles'
import { getSettings } from '@/api/settings'
import { daysUntil, formatDateShort } from '@/utils/dates'
import { displayWeight, toDisplayUnit, fromDisplayUnit } from '@/utils/units'
import { phaseColor, phasesForBlock } from '@/utils/phases'
import { resolveTrainingWeekForDate, weekStartForBlock } from '@/utils/weekStart'
import SetupOnboarding from '@/components/setup/SetupOnboarding'
import Num from '@/components/shared/Num'
import { Activity, Target, Scale, Trophy, TrendingUp, Edit2, Save, X, Plus, Trash2, Download, Dumbbell, Ruler, Sparkles, HeartPulse, User } from 'lucide-react'
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
import { useAuth } from '@/auth/AuthProvider'
import type { Exercise, PlannedExercise, Phase, WeightEntry, LiftProfile, Session, SessionWellness } from '@powerlifting/types'

const LIFT_ORDER = ['squat', 'bench', 'deadlift'] as const
type BigThreeLift = typeof LIFT_ORDER[number]
type MaxDrafts = Record<BigThreeLift, string>

const DASHBOARD_ANALYSIS_WINDOW = 'block'
const DASHBOARD_ANALYSIS_SECTIONS: AnalysisSectionKey[] = ['overview', 'fatigue_readiness', 'workload']
const PROFILE_ESTIMATE_READY_SCORE = 55
const LIFT_ALIASES: Record<LiftProfile['lift'], string[]> = {
  squat: ['squat'],
  bench: ['bench'],
  deadlift: ['deadlift'],
}

function hasCompletedSet(exercise: Exercise): boolean {
  const setCount = Math.max(0, Math.round(Number(exercise.sets) || 0))

  if (exercise.set_statuses?.length) {
    for (let index = 0; index < setCount; index += 1) {
      const status = exercise.set_statuses[index]
      if (status === 'completed' || status === undefined) return true
    }
    return false
  }

  if (exercise.failed_sets?.length) {
    const legacySetCount = Math.max(setCount, exercise.failed_sets.length)
    for (let index = 0; index < legacySetCount; index += 1) {
      if (exercise.failed_sets[index] !== true) return true
    }
    return false
  }

  if (exercise.failed) return false
  return setCount > 0
}

const LIFT_LABELS: Record<LiftProfile['lift'], string> = {
  squat: 'Squat',
  bench: 'Bench',
  deadlift: 'Deadlift',
}

const LIFT_COLORS: Record<LiftProfile['lift'], string> = {
  squat: 'var(--lift-squat)',
  bench: 'var(--lift-bench)',
  deadlift: 'var(--lift-deadlift)',
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

function fatigueColor(score: number | null): string {
  if (score === null) return 'var(--text-muted)'
  if (score > 0.65) return 'var(--fatigue-high)'
  if (score >= 0.4) return 'var(--fatigue-mid)'
  return 'var(--fatigue-low)'
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

function numberDraft(value: number | null | undefined): string {
  return typeof value === 'number' && Number.isFinite(value) ? String(value) : ''
}

function displayWeightDraft(kg: number | null | undefined, unit: 'kg' | 'lb'): string {
  return typeof kg === 'number' && Number.isFinite(kg) ? String(toDisplayUnit(kg, unit)) : ''
}

function parseRequiredNonNegativeDraft(value: string): number | null {
  const trimmed = value.trim()
  if (!trimmed) return null
  const parsed = Number(trimmed)
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null
}

function parseOptionalNonNegativeDraft(value: string): number | null | undefined {
  const trimmed = value.trim()
  if (!trimmed) return null
  const parsed = Number(trimmed)
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : undefined
}

function parseDisplayWeightDraft(value: string, unit: 'kg' | 'lb'): number | null {
  const parsed = parseRequiredNonNegativeDraft(value)
  return parsed === null ? null : fromDisplayUnit(parsed, unit)
}

function findLiftAnalysis(weekly: Partial<WeeklyAnalysis> | null, lift: LiftProfile['lift']) {
  if (!weekly) return undefined
  const exact = weekly.lifts?.[lift]
  if (exact) return exact
  return Object.entries(weekly.lifts ?? {}).find(([name]) => {
    const lowerName = name.toLowerCase()
    return LIFT_ALIASES[lift].some((alias) => lowerName.includes(alias))
  })?.[1]
}

function mergeDashboardAnalysisSections(
  payloads: Partial<Record<AnalysisSectionKey, Partial<WeeklyAnalysis>>>,
): Partial<WeeklyAnalysis> | null {
  const hasPayload = DASHBOARD_ANALYSIS_SECTIONS.some((section) => Boolean(payloads[section]))
  if (!hasPayload) return null
  return Object.assign(
    {},
    ...DASHBOARD_ANALYSIS_SECTIONS.map((section) => payloads[section] ?? {}),
  )
}

function sectionPending(
  statuses: Partial<Record<AnalysisSectionKey, string>>,
  payloads: Partial<Record<AnalysisSectionKey, Partial<WeeklyAnalysis>>>,
  section: AnalysisSectionKey,
): boolean {
  if (payloads[section]) return false
  const status = statuses[section]
  return status === undefined || status === 'missing' || status === 'pending' || status === 'running'
}

function phaseState(phase: Phase, currentWeek: number): 'completed' | 'current' | 'upcoming' {
  if (phase.end_week < currentWeek) return 'completed'
  if (phase.start_week <= currentWeek && phase.end_week >= currentWeek) return 'current'
  return 'upcoming'
}

export default function Dashboard() {
  const navigate = useNavigate()
  const { readOnly } = useAuth()
  const { program, version, isLoading, needsSetup, updateMaxes, updateBodyWeight, updatePhases, updateLiftProfiles } = useProgramStore()
  const { unit } = useSettingsStore()
  const { pushToast } = useUiStore()

  const [editingMaxes, setEditingMaxes] = useState(false)
  const [editingWeight, setEditingWeight] = useState(false)
  const [editingPhases, setEditingPhases] = useState(false)
  const [editingLiftProfiles, setEditingLiftProfiles] = useState(false)
  const [localMaxes, setLocalMaxes] = useState<MaxDrafts>({ squat: '', bench: '', deadlift: '' })
  const [localWeight, setLocalWeight] = useState('')
  const [localPhases, setLocalPhases] = useState<Phase[]>([])
  const [localLiftProfiles, setLocalLiftProfiles] = useState<LiftProfile[]>([])
  const [weightLog, setWeightLog] = useState<WeightEntry[]>([])
  const [editingMeasurements, setEditingMeasurements] = useState(false)
  const [localHeight, setLocalHeight] = useState('')
  const [localWingspan, setLocalWingspan] = useState('')
  const [localLegLength, setLocalLegLength] = useState('')
  const [profileGuideOpen, setProfileGuideOpen] = useState(false)
  const [profileGuideDraft, setProfileGuideDraft] = useState<LiftProfile | null>(null)
  const [profileGuideReview, setProfileGuideReview] = useState<LiftProfileReview | null>(null)
  const [profileGuideLoading, setProfileGuideLoading] = useState(false)
  const [profileGuideRewriting, setProfileGuideRewriting] = useState(false)
  const [profileGuideEstimating, setProfileGuideEstimating] = useState(false)
  const [dashboardAnalysisWindow, setDashboardAnalysisWindow] = useState<AnalysisWindow | null>(null)
  const [dashboardSectionPayloads, setDashboardSectionPayloads] = useState<Partial<Record<AnalysisSectionKey, Partial<WeeklyAnalysis>>>>({})
  const [dashboardSectionStatuses, setDashboardSectionStatuses] = useState<Partial<Record<AnalysisSectionKey, string>>>({})
  const [dashboardAnalysisError, setDashboardAnalysisError] = useState<string | null>(null)
  const [profileSnippet, setProfileSnippet] = useState<PublicProfile | null>(null)
  const [rankingPercentile, setRankingPercentile] = useState<RankingPercentileResult | null>(null)
  const [rankingPercentileLoading, setRankingPercentileLoading] = useState(false)
  const [rankingCountry, setRankingCountry] = useState<string | null>(null)
  const [rankingRegion, setRankingRegion] = useState<string | null>(null)
  const [settingsLoaded, setSettingsLoaded] = useState(false)
  const dashboardAsOfDate = useMemo(() => format(new Date(), 'yyyy-MM-dd'), [])

  useEffect(() => {
    if (version && program && !needsSetup) {
      fetchWeightLog(version)
        .then(setWeightLog)
        .catch((e) => console.error('Failed to load weight log:', e))
    }
  }, [version, program, needsSetup])

  useEffect(() => {
    if (program?.lift_profiles) {
      setLocalLiftProfiles(mergeLiftProfiles(program.lift_profiles))
    } else {
      setLocalLiftProfiles(mergeLiftProfiles())
    }
  }, [program?.lift_profiles])

  useEffect(() => {
    let cancelled = false

    if (!version || !program || needsSetup) {
      setDashboardAnalysisWindow(null)
      setDashboardSectionPayloads({})
      setDashboardSectionStatuses({})
      setDashboardAnalysisError(null)
      return
    }

    let pollTimer: number | undefined

    async function pollDashboardSections() {
      const statuses = await Promise.all(
        DASHBOARD_ANALYSIS_SECTIONS.map((section) =>
          fetchAnalysisSection<Partial<WeeklyAnalysis>>(dashboardAsOfDate, DASHBOARD_ANALYSIS_WINDOW, section),
        ),
      )
      if (cancelled) return

      setDashboardSectionStatuses(Object.fromEntries(statuses.map((status) => [status.sectionKey, status.status])))
      setDashboardSectionPayloads((current) => {
        const next = { ...current }
        for (const status of statuses) {
          if (status.status === 'complete' && status.payload) {
            next[status.sectionKey] = status.payload
          }
        }
        return next
      })

      const terminal = statuses.every((status) => status.status === 'complete' || status.status === 'error')
      if (!terminal) {
        pollTimer = window.setTimeout(() => {
          pollDashboardSections().catch((error) => {
            if (!cancelled) setDashboardAnalysisError(error instanceof Error ? error.message : String(error))
          })
        }, 2000)
      }
    }

    setDashboardAnalysisWindow(null)
    setDashboardSectionPayloads({})
    setDashboardSectionStatuses({})
    setDashboardAnalysisError(null)

    fetchAnalysisManifest(dashboardAsOfDate, DASHBOARD_ANALYSIS_WINDOW)
      .then((manifest) => {
        if (cancelled) return
        setDashboardAnalysisWindow(manifest.windows[DASHBOARD_ANALYSIS_WINDOW])
        setDashboardSectionStatuses(Object.fromEntries(
          DASHBOARD_ANALYSIS_SECTIONS.map((section) => [section, manifest.sections[section]?.status ?? 'missing']),
        ))
        return queueAnalysisSections({
          asOfDate: dashboardAsOfDate,
          windowKey: DASHBOARD_ANALYSIS_WINDOW,
          sections: DASHBOARD_ANALYSIS_SECTIONS,
        })
      })
      .then(() => pollDashboardSections())
      .catch((error) => {
        console.warn('Failed to load dashboard analysis sections:', error)
        if (!cancelled) {
          setDashboardAnalysisError(error instanceof Error ? error.message : String(error))
        }
      })

    return () => {
      cancelled = true
      if (pollTimer !== undefined) window.clearTimeout(pollTimer)
    }
  }, [version, program, needsSetup, dashboardAsOfDate])

  useEffect(() => {
    let cancelled = false

    if (!program || needsSetup) {
      setProfileSnippet(null)
      return
    }

    fetchCurrentProfile()
      .then((profile) => {
        if (!cancelled) setProfileSnippet(profile)
      })
      .catch(() => {
        if (!cancelled) setProfileSnippet(null)
      })

    return () => {
      cancelled = true
    }
  }, [program, needsSetup])

  // Load user's saved ranking location settings once
  useEffect(() => {
    let cancelled = false
    if (needsSetup) return
    getSettings()
      .then((s) => {
        if (!cancelled) {
          setRankingCountry(s.ranking_country)
          setRankingRegion(s.ranking_region)
        }
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setSettingsLoaded(true)
      })
    return () => { cancelled = true }
  }, [needsSetup])

  const { competitions: userCompetitions, loadAll: loadUserCompetitions } = useCompetitionsStore()

  useEffect(() => {
    if (!settingsLoaded) return
    loadUserCompetitions({ country: rankingCountry ?? undefined, state: rankingRegion ?? undefined })
  }, [settingsLoaded, rankingCountry, rankingRegion, loadUserCompetitions])

  // Load ranking percentile once we have actual maxes + bodyweight + settings
  // Uses actualMaxes (computed after program loads below) — but since this effect
  // depends on program we re-derive them inline here to avoid ordering issues.
  useEffect(() => {
    let cancelled = false
    if (needsSetup || !program) return

    const sexCode = (program.meta?.sex === 'female' ? 'F' : 'M')
    const bw = program.meta?.current_body_weight_kg
    if (!bw || bw <= 0) return

    // Derive actual block maxes inline (mirrors the computation below)
    const inline: Record<string, number> = { squat: 0, bench: 0, deadlift: 0 }
    for (const session of program.sessions ?? []) {
      if (!session.completed || session.status === 'skipped') continue
      if ((session.block || 'current') !== 'current') continue
      for (const exercise of session.exercises ?? []) {
        if (exercise.kg == null) continue
        const name = exercise.name.toLowerCase()
        if (name.includes('squat')     && exercise.kg > inline.squat)    inline.squat    = exercise.kg
        if (name.includes('bench')     && exercise.kg > inline.bench)    inline.bench    = exercise.kg
        if (name.includes('deadlift')  && exercise.kg > inline.deadlift) inline.deadlift = exercise.kg
      }
    }

    setRankingPercentileLoading(true)
    fetchRankingPercentile({
      squat_kg:    inline.squat    > 0 ? inline.squat    : undefined,
      bench_kg:    inline.bench    > 0 ? inline.bench    : undefined,
      deadlift_kg: inline.deadlift > 0 ? inline.deadlift : undefined,
      bodyweight_kg: bw,
      sex_code: sexCode,
      country: rankingCountry ?? undefined,
      region:  rankingRegion  ?? undefined,
    })
      .then((data) => { if (!cancelled) setRankingPercentile(data) })
      .catch(() => {})
      .finally(() => { if (!cancelled) setRankingPercentileLoading(false) })

    return () => { cancelled = true }
  }, [program, needsSetup, rankingCountry, rankingRegion])

  if (needsSetup) {
    return <SetupOnboarding />
  }

  if (isLoading || !program) {
    return (
      <Group justify="center" mih="50vh">
        <Loader />
      </Group>
    )
  }

  const { meta, sessions, phases } = program
  const currentBlockPhases = phasesForBlock(phases)
  const todayStr = format(new Date(), 'yyyy-MM-dd')
  const currentBlockWeekStartDay = weekStartForBlock(program, 'current')
  const currentWeekNumber = resolveTrainingWeekForDate(
    todayStr,
    meta.program_start ?? sessions[0]?.date ?? todayStr,
    currentBlockWeekStartDay,
    sessions,
    'current',
  )
  const profileFederation = profileSnippet?.federation || meta.federation || 'Federation unset'
  const profileWeightClass = profileSnippet?.weight_class_kg ?? meta.weight_class_kg
  const profileBio = profileSnippet?.bio?.trim()

  const upcomingComps = userCompetitions
    .filter((c) => c.user_status !== 'skipped' && c.user_status !== 'completed' && c.user_status !== 'available' && new Date(c.start_date) >= new Date())
    .sort((a, b) => a.start_date.localeCompare(b.start_date))

  const latestWeightKg = weightLog.length > 0 ? weightLog[0].kg : meta.current_body_weight_kg
  const weightClassProgress = meta.weight_class_kg > 0
    ? Math.min(100, (latestWeightKg / meta.weight_class_kg) * 100)
    : 0

  const actualMaxes = { squat: 0, bench: 0, deadlift: 0 }
  for (const session of sessions) {
    if (!session.completed) continue
    if (session.status === 'skipped') continue
    if ((session.block || 'current') !== 'current') continue
    for (const exercise of session.exercises) {
      if (exercise.kg == null) continue
      if (!hasCompletedSet(exercise)) continue
      const name = exercise.name.toLowerCase()
      if (name.includes('squat') && exercise.kg > actualMaxes.squat) actualMaxes.squat = exercise.kg
      if (name.includes('bench') && exercise.kg > actualMaxes.bench) actualMaxes.bench = exercise.kg
      if (name.includes('deadlift') && exercise.kg > actualMaxes.deadlift) actualMaxes.deadlift = exercise.kg
    }
  }

  const wellnessTrend = buildWellnessTrend(sessions)

  const nextWorkout = sessions
    .map((session, index) => ({ session, index }))
    .filter(({ session }) => (session.block ?? 'current') === 'current')
    .filter(({ session }) => session.status !== 'skipped')
    .filter(({ session }) => session.date >= todayStr)
    .filter(({ session }) => (session.planned_exercises?.length ?? 0) > 0 || (session.exercises?.length ?? 0) > 0)
    .sort((a, b) => a.session.date.localeCompare(b.session.date) || a.index - b.index)[0]?.session ?? null

  const MAX_VISIBLE_EXERCISES = 3

  const startEditingMaxes = () => {
    setLocalMaxes({
      squat: displayWeightDraft(meta.target_squat_kg, unit),
      bench: displayWeightDraft(meta.target_bench_kg, unit),
      deadlift: displayWeightDraft(meta.target_dl_kg, unit),
    })
    setEditingMaxes(true)
  }

  const saveMaxes = async () => {
    const squat = parseDisplayWeightDraft(localMaxes.squat, unit)
    const bench = parseDisplayWeightDraft(localMaxes.bench, unit)
    const deadlift = parseDisplayWeightDraft(localMaxes.deadlift, unit)
    if (squat === null || bench === null || deadlift === null) {
      pushToast({ message: 'Enter valid target maxes before saving', type: 'error' })
      return
    }

    try {
      await updateMaxes({ squat_kg: squat, bench_kg: bench, deadlift_kg: deadlift })
      pushToast({ message: 'Target maxes updated', type: 'success' })
      setEditingMaxes(false)
    } catch (err) {
      pushToast({ message: 'Failed to update maxes', type: 'error' })
    }
  }

  const startEditingWeight = () => {
    setLocalWeight(displayWeightDraft(latestWeightKg, unit))
    setEditingWeight(true)
  }

  const saveWeight = async () => {
    const weightKg = parseDisplayWeightDraft(localWeight, unit)
    if (weightKg === null) {
      pushToast({ message: 'Enter a valid body weight before saving', type: 'error' })
      return
    }

    try {
      await updateBodyWeight(weightKg)
      pushToast({ message: 'Body weight updated', type: 'success' })
      setEditingWeight(false)
    } catch (err) {
      pushToast({ message: 'Failed to update weight', type: 'error' })
    }
  }

  const startEditingMeasurements = () => {
    setLocalHeight(numberDraft(meta.height_cm))
    setLocalWingspan(numberDraft(meta.arm_wingspan_cm))
    setLocalLegLength(numberDraft(meta.leg_length_cm))
    setEditingMeasurements(true)
  }

  const saveMeasurements = async () => {
    const height = parseOptionalNonNegativeDraft(localHeight)
    const wingspan = parseOptionalNonNegativeDraft(localWingspan)
    const legLength = parseOptionalNonNegativeDraft(localLegLength)
    if (height === undefined || wingspan === undefined || legLength === undefined) {
      pushToast({ message: 'Enter valid measurements before saving', type: 'error' })
      return
    }

    try {
      await Promise.all([
        updateMetaField(version, 'height_cm', height),
        updateMetaField(version, 'arm_wingspan_cm', wingspan),
        updateMetaField(version, 'leg_length_cm', legLength),
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
  const currentBlockWeekly = mergeDashboardAnalysisSections(dashboardSectionPayloads)
  const currentBlockFatigue = currentBlockWeekly?.fatigue_index ?? null
  const currentBlockFatigueComponents = currentBlockWeekly?.fatigue_components ?? null
  const fatigueSectionLoading = sectionPending(dashboardSectionStatuses, dashboardSectionPayloads, 'fatigue_readiness')
  const workloadSectionLoading = sectionPending(dashboardSectionStatuses, dashboardSectionPayloads, 'workload')
  const localMaxesKg = LIFT_ORDER.reduce((acc, lift) => {
    acc[lift] = parseDisplayWeightDraft(localMaxes[lift], unit)
    return acc
  }, {} as Record<BigThreeLift, number | null>)
  const localMaxTotalKg = LIFT_ORDER.every((lift) => localMaxesKg[lift] !== null)
    ? LIFT_ORDER.reduce((sum, lift) => sum + (localMaxesKg[lift] ?? 0), 0)
    : null
  const liftBreakdownRows = LIFT_ORDER.map((lift) => {
    const liftAnalysis = findLiftAnalysis(currentBlockWeekly, lift)
    const actualMax = actualMaxes[lift] > 0 ? actualMaxes[lift] : null
    const endStrength = currentBlockWeekly?.current_maxes?.[lift] ?? actualMax
    return {
      lift,
      endStrength,
      progressionRate: liftAnalysis?.progression_rate_kg_per_week ?? null,
    }
  })
  const maxRows = [
    { lift: 'squat' as const, label: 'Squat', actual: actualMaxes.squat, target: meta.target_squat_kg, color: LIFT_COLORS.squat },
    { lift: 'bench' as const, label: 'Bench', actual: actualMaxes.bench, target: meta.target_bench_kg, color: LIFT_COLORS.bench },
    { lift: 'deadlift' as const, label: 'Deadlift', actual: actualMaxes.deadlift, target: meta.target_dl_kg, color: LIFT_COLORS.deadlift },
  ]
  const actualTotalKg = actualMaxes.squat + actualMaxes.bench + actualMaxes.deadlift
  const targetTotalKg = meta.target_total_kg || meta.target_squat_kg + meta.target_bench_kg + meta.target_dl_kg
  const measurementRows = [
    { label: 'Height', value: meta.height_cm ? `${meta.height_cm}` : '--', unit: 'cm' },
    { label: 'Arm wingspan', value: meta.arm_wingspan_cm ? `${meta.arm_wingspan_cm}` : '--', unit: 'cm' },
    { label: 'Leg length', value: meta.leg_length_cm ? `${meta.leg_length_cm}` : '--', unit: 'cm' },
  ]

  return (
    <Stack gap={0} className="if-mock-page" data-testid="dashboard-page">
      <div className="if-mock-header">
        <h1 className="if-mock-title">Dashboard</h1>
        <div className="if-mock-toolbar">
          <a className="if-mock-button" href="/api/export/xlsx" download="program_history.xlsx">
            <Download size={12} /> Excel
          </a>
          <a className="if-mock-button" href="/api/export/markdown" download="program_history.md">
            <Download size={12} /> Markdown
          </a>
        </div>
      </div>

      {profileSnippet && (
        <Link
          to="/profile"
          className="if-mock-card"
          data-testid="dashboard-profile-link"
          style={{
            alignItems: 'center',
            color: 'inherit',
            display: 'flex',
            gap: 16,
            justifyContent: 'space-between',
            marginBottom: 12,
            textDecoration: 'none',
          }}
        >
          <div style={{ minWidth: 0 }}>
            <div className="if-mock-card-label"><User size={12} /> Profile</div>
            <Text fw={600} c="var(--color-text-primary)" truncate>
              {profileSnippet.display_name}
            </Text>
            <Text size="xs" c="var(--color-text-secondary)" mt={2}>
              {profileFederation} - {profileWeightClass || '--'} kg
              {profileSnippet.practicing_for ? ` - ${profileSnippet.practicing_for}` : ''}
            </Text>
            {profileBio && (
              <Text size="sm" c="var(--color-text-secondary)" mt={6} lineClamp={2}>
                {profileBio}
              </Text>
            )}
          </div>
          <span className="if-mock-badge">View</span>
        </Link>
      )}

      <div className="if-dashboard-row if-dashboard-row-top">
        <section
          className="if-mock-card"
          data-testid="dashboard-next-workout"
          style={nextWorkout ? { cursor: 'pointer', textDecoration: 'none', color: 'inherit', display: 'block' } : undefined}
          onClick={nextWorkout ? () => navigate(`/session/${nextWorkout.date}`) : undefined}
          role={nextWorkout ? 'link' : undefined}
          tabIndex={nextWorkout ? 0 : undefined}
          onKeyDown={nextWorkout ? (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); navigate(`/session/${nextWorkout.date}`) } } : undefined}
        >
          <div className="if-mock-card-label"><Dumbbell size={12} /> Next workout</div>
          {nextWorkout ? (() => {
            const planned = nextWorkout.planned_exercises?.length ? nextWorkout.planned_exercises : nextWorkout.exercises
            const visible = planned.slice(0, MAX_VISIBLE_EXERCISES)
            const remaining = planned.length - visible.length
            return (
              <>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, marginBottom: 4 }}>
                  <span style={{ color: 'var(--color-text-primary)', fontSize: 13, fontWeight: 500 }}>{nextWorkout.day} · {formatDateShort(nextWorkout.date)}</span>
                  {daysUntil(nextWorkout.date) <= 0 ? (
                    <span className="if-mock-pill" style={{ background: 'var(--color-background-success)', borderColor: 'var(--color-border-success)', color: 'var(--color-text-success)' }}>Today</span>
                  ) : daysUntil(nextWorkout.date) === 1 ? (
                    <span className="if-mock-pill" style={{ background: 'var(--color-background-info)', borderColor: 'var(--color-border-info)', color: 'var(--color-text-info)' }}>Tomorrow</span>
                  ) : (
                    <span className="if-mock-num if-mock-muted" style={{ fontSize: 11 }}>{daysUntil(nextWorkout.date)}d</span>
                  )}
                </div>
                <div style={{ color: 'var(--color-text-secondary)', fontSize: 11, marginBottom: 8 }}>{nextWorkout.week}{nextWorkout.phase?.name ? ` · ${nextWorkout.phase.name}` : ''}</div>
                {visible.map((exercise, i) => (
                  <div key={i} className="if-compact-row">
                    <span style={{ color: 'var(--color-text-primary)', flex: 1, fontSize: 12, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{exercise.name}</span>
                    <span className="if-mock-num" style={{ fontSize: 11, flexShrink: 0 }}>{exercise.sets}×{exercise.reps}</span>
                    {exercise.kg != null && exercise.kg > 0 && (
                      <span className="if-mock-num if-mock-muted" style={{ fontSize: 11, flexShrink: 0, width: 'auto' }}>{displayWeight(exercise.kg, unit)}</span>
                    )}
                  </div>
                ))}
                {remaining > 0 && (
                  <div style={{ color: 'var(--color-text-secondary)', fontSize: 11, paddingTop: 4 }}>+{remaining} more</div>
                )}
              </>
            )
          })() : (
            <Text size="sm" c="dimmed">No planned workouts.</Text>
          )}
        </section>

        <section className="if-mock-card">
          <div className="if-mock-card-label"><Trophy size={12} /> Upcoming competitions</div>
          {upcomingComps.length > 0 ? upcomingComps.map((comp) => (
            <div className="if-compact-row" key={comp.master_id}>
              <span
                className="if-mock-badge"
                style={{
                  background: comp.user_status === 'confirmed' ? 'var(--color-background-success)' : 'var(--color-background-secondary)',
                  color: comp.user_status === 'confirmed' ? 'var(--color-text-success)' : 'var(--color-text-secondary)',
                }}
              >
                {comp.user_status}
              </span>
              <span style={{ color: 'var(--color-text-primary)', flex: 1, fontSize: 12, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {comp.name}
              </span>
              <span className="if-mock-num if-mock-muted" style={{ fontSize: 12 }}>{daysUntil(comp.start_date)}d</span>
            </div>
          )) : (
            <Text size="sm" c="dimmed">No upcoming competitions.</Text>
          )}
        </section>

        <section className="if-mock-card">
          <div style={{ alignItems: 'center', display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}>
            <div className="if-mock-card-label" style={{ marginBottom: 0 }}><TrendingUp size={12} /> Actual vs target maxes</div>
            {editingMaxes ? (
              <div style={{ display: 'flex', gap: 4 }}>
                <button className="if-mock-icon-button" onClick={saveMaxes} aria-label="Save target maxes" data-testid="dashboard-save-target-maxes"><Save size={15} /></button>
                <button className="if-mock-icon-button" onClick={() => setEditingMaxes(false)} aria-label="Cancel target maxes edit" data-testid="dashboard-cancel-target-maxes"><X size={15} /></button>
              </div>
            ) : (
              <button className="if-mock-icon-button" onClick={startEditingMaxes} disabled={readOnly} aria-label="Edit target maxes" data-testid="dashboard-edit-target-maxes"><Edit2 size={15} /></button>
            )}
          </div>
          {maxRows.map(({ lift, label, actual, target, color }) => {
            const pct = target > 0 ? Math.min(100, (actual / target) * 100) : 0
            return (
              <div className="if-progress-row" key={lift}>
                <span className="if-progress-label">{label}</span>
                <div className="if-progress-track"><div className="if-progress-fill" style={{ width: `${pct}%`, background: color }} /></div>
                <span className="if-progress-value">{actual > 0 ? displayWeight(actual, unit) : '--'}</span>
                {editingMaxes ? (
                  <TextInput
                    type="number"
                    inputMode="decimal"
                    value={localMaxes[lift]}
                    onChange={(e) => {
                      const value = e.currentTarget.value
                      setLocalMaxes(prev => ({ ...prev, [lift]: value }))
                    }}
                    aria-label={`${lift} target max`}
                    data-testid={`dashboard-target-${lift}`}
                    size="xs"
                    styles={{ input: { fontFamily: 'var(--font-mono)', fontSize: 11, minHeight: 24, padding: '2px 4px', width: 64 } }}
                  />
                ) : (
                  <span className="if-progress-target">↑ {target > 0 ? displayWeight(target, unit) : '--'}</span>
                )}
              </div>
            )
          })}
          <div className="if-divider-top" style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span style={{ color: 'var(--color-text-secondary)', fontSize: 12 }}>Total</span>
            <span className="if-mock-num" style={{ fontSize: 13, fontWeight: 500 }}>
              {actualTotalKg > 0 ? displayWeight(actualTotalKg, unit) : '--'}
              <span className="if-mock-muted" style={{ fontSize: 11 }}> / {targetTotalKg > 0 ? displayWeight(targetTotalKg, unit) : '--'} target</span>
            </span>
          </div>
        </section>

        <section className="if-mock-card">
          <div style={{ alignItems: 'center', display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
            <div className="if-mock-card-label" style={{ marginBottom: 0 }}><Ruler size={12} /> Anthropometrics</div>
            {editingMeasurements ? (
              <div style={{ display: 'flex', gap: 4 }}>
                <button className="if-mock-icon-button" onClick={saveMeasurements} aria-label="Save measurements" data-testid="dashboard-save-measurements"><Save size={15} /></button>
                <button className="if-mock-icon-button" onClick={() => setEditingMeasurements(false)} aria-label="Cancel measurements edit" data-testid="dashboard-cancel-measurements"><X size={15} /></button>
              </div>
            ) : (
              <button className="if-mock-icon-button" onClick={startEditingMeasurements} disabled={readOnly} aria-label="Edit measurements" data-testid="dashboard-edit-measurements"><Edit2 size={15} /></button>
            )}
          </div>
          {editingMeasurements ? (
            <Stack gap={8}>
              {[
                { label: 'Height', value: localHeight, set: setLocalHeight, test: 'dashboard-height' },
                { label: 'Arm wingspan', value: localWingspan, set: setLocalWingspan, test: 'dashboard-wingspan' },
                { label: 'Leg length', value: localLegLength, set: setLocalLegLength, test: 'dashboard-leg-length' },
              ].map((row) => (
                <Group key={row.label} gap="xs" wrap="nowrap">
                  <Text size="xs" c="dimmed" w={86}>{row.label}</Text>
                  <TextInput type="number" value={row.value} onChange={(e) => row.set(e.currentTarget.value)} size="xs" style={{ flex: 1 }} data-testid={row.test} />
                  <Text size="xs" c="dimmed">cm</Text>
                </Group>
              ))}
            </Stack>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {measurementRows.map((row) => (
                <div key={row.label}>
                  <div style={{ color: 'var(--color-text-secondary)', fontSize: 10, marginBottom: 2 }}>{row.label}</div>
                  <div className="if-mock-num" style={{ fontSize: 22, fontWeight: 500 }}>
                    {row.value} <span className="if-mock-muted" style={{ fontSize: 13 }}>{row.unit}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

  
         <section className="if-mock-card" data-testid="dashboard-ranking-percentile">
          <div style={{ alignItems: 'baseline', display: 'flex', gap: 8, marginBottom: 12 }}>
            <div className="if-mock-card-label" style={{ marginBottom: 0 }}>
              <Trophy size={12} /> Percentile rankings
            </div>
            {rankingPercentile?.weight_class_label && (
              <span style={{ color: 'var(--color-text-secondary)', fontSize: 10 }}>
                {rankingPercentile.weight_class_label} class · last 3 years · deduplicated by lifter
              </span>
            )}
          </div>
          {rankingPercentileLoading ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <Loader size="xs" />
              <Text size="xs" c="dimmed">Loading rankings...</Text>
            </div>
          ) : !rankingPercentile ? (
            <Text size="xs" c="dimmed">
              {meta.current_body_weight_kg > 0
                ? 'Rankings unavailable — dataset may still be loading.'
                : 'Set your body weight to see percentile rankings.'}
            </Text>
          ) : (() => {
            // beaten = % of lifters the user beat; top% = 100 - beaten, rounded to nearest 10
            const fmtTop = (beaten: number | null | undefined): string | null => {
              if (typeof beaten !== 'number') return null
              return `top ${Math.max(1, Math.round((100 - beaten) / 10) * 10)}%`
            }
            const barPct = (userKg: number, mean: number | null | undefined, beaten: number | null | undefined): number => {
              if (mean && mean > 0) return Math.min(100, (userKg / mean) * 100);
              if (typeof beaten === 'number') return Math.min(100, Math.max(0, beaten));
              return 0;
            }

            const actualTotal = actualMaxes.squat + actualMaxes.bench + actualMaxes.deadlift
            const LIFT_ROWS: Array<{ key: keyof typeof rankingPercentile.global; label: string; userKg: number; color: string }> = [
              { key: 'squat',    label: 'Squat',    userKg: actualMaxes.squat,    color: LIFT_COLORS.squat },
              { key: 'bench',    label: 'Bench',    userKg: actualMaxes.bench,    color: LIFT_COLORS.bench },
              { key: 'deadlift', label: 'Deadlift', userKg: actualMaxes.deadlift, color: LIFT_COLORS.deadlift },
            ]
            return (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                {LIFT_ROWS.map(({ key, label, userKg, color }) => {
                  if (userKg <= 0) return null
                  const g  = rankingPercentile.global?.[key] as number | null
                  const n  = rankingPercentile.national?.[key] as number | null
                  const r  = rankingPercentile.regional?.[key] as number | null
                  type CardKey = keyof typeof rankingPercentile.global
                  const top10k = `top10_mean_${key}` as CardKey
                  const gMean = rankingPercentile.global?.[top10k] as number | null
                  const nMean = (rankingPercentile.national?.[top10k] ?? null) as number | null
                  const rMean = (rankingPercentile.regional?.[top10k] ?? null) as number | null
                  if (typeof g !== 'number' && typeof n !== 'number' && typeof r !== 'number') return null

                  const SCOPES: Array<{ beaten: number | null; mean: number | null; label: string }> = [
                    { beaten: g, mean: gMean, label: 'worldwide' },
                    ...(rankingCountry ? [{ beaten: n, mean: nMean, label: `in ${rankingCountry}` }] : []),
                    ...(rankingRegion  ? [{ beaten: r, mean: rMean, label: `in ${rankingRegion}`  }] : []),
                  ]

                  return (
                    <div key={key}>
                      {/* Lift name + current value */}
                      <div style={{ color: color, fontSize: 11, fontWeight: 600, letterSpacing: '0.06em', marginBottom: 6, textTransform: 'uppercase' }}>
                        {label} — {displayWeight(userKg, unit)}
                      </div>
                      {/* One text + bar block per scope */}
                      {SCOPES.map(({ beaten, mean, label: scopeLabel }) => {
                        const top = fmtTop(beaten)
                        if (!top) return null
                        const pct = barPct(userKg, mean, beaten)
                        return (
                          <div key={scopeLabel} style={{ marginBottom: 8 }}>
                            <div style={{ color: 'var(--color-text-secondary)', fontSize: 11, marginBottom: 3 }}>
                              {top} {scopeLabel}
                            </div>
                            <div style={{ alignItems: 'center', display: 'flex', gap: 6 }}>
                              <div className="if-progress-track" style={{ flex: 1 }}>
                                <div className="if-progress-fill" style={{ width: `${pct}%`, background: color }} />
                              </div>
                              {mean && mean > 0 && (
                                <span className="if-progress-target" style={{ width: 'auto', flexShrink: 0 }}>↑ {displayWeight(mean, unit)} avg</span>
                              )}
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  )
                })}
                {!rankingCountry && (
                  <Text size="xs" c="dimmed">Set your country in Settings to see national rankings.</Text>
                )}
                {rankingCountry && !rankingRegion && (
                  <Text size="xs" c="dimmed">Set your region in Settings to see regional rankings.</Text>
                )}
              </div>
            )
          })()}
        </section>
      </div>

      <div className="if-dashboard-row if-dashboard-row-mid">
        <section className="if-mock-card">
          <div style={{ alignItems: 'center', display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
            <div className="if-mock-card-label" style={{ marginBottom: 0 }}><Scale size={12} /> Body weight</div>
            {editingWeight ? (
              <div style={{ display: 'flex', gap: 4 }}>
                <button className="if-mock-icon-button" onClick={saveWeight} aria-label="Save body weight" data-testid="dashboard-save-body-weight"><Save size={15} /></button>
                <button className="if-mock-icon-button" onClick={() => setEditingWeight(false)} aria-label="Cancel body weight edit" data-testid="dashboard-cancel-body-weight"><X size={15} /></button>
              </div>
            ) : (
              <button className="if-mock-icon-button" onClick={startEditingWeight} disabled={readOnly} aria-label="Edit body weight" data-testid="dashboard-edit-body-weight"><Edit2 size={15} /></button>
            )}
          </div>
          {editingWeight ? (
            <TextInput type="number" inputMode="decimal" value={localWeight} onChange={(e) => setLocalWeight(e.currentTarget.value)} data-testid="dashboard-body-weight" />
          ) : (
            <div className="if-mock-num" style={{ fontSize: 'clamp(28px, 2.4vw, 36px)', fontWeight: 500, lineHeight: 1.1, whiteSpace: 'nowrap' }}>{displayWeight(latestWeightKg, unit)}</div>
          )}
          <div style={{ color: 'var(--color-text-secondary)', fontSize: 11, marginTop: 3 }}>Target: {meta.weight_class_kg} kg class</div>
          <div className="if-progress-track" style={{ marginTop: 10, width: '100%' }}><div className="if-progress-fill" style={{ width: `${weightClassProgress}%`, background: 'var(--accent-blue)' }} /></div>
          <div style={{ color: 'var(--color-text-secondary)', fontSize: 10, marginTop: 4 }}>{weightClassProgress.toFixed(0)}% to class limit</div>
        </section>

        <section className="if-mock-card">
          <div style={{ alignItems: 'center', display: 'flex', justifyContent: 'space-between', marginBottom: 10 }}>
            <div className="if-mock-card-label" style={{ marginBottom: 0 }}><HeartPulse size={12} /> Subjective wellness</div>
            {wellnessTrend.overallAverage !== null && <span className="if-mock-muted" style={{ fontSize: 11 }}>{wellnessTrend.overallAverage.toFixed(1)} / 5 avg</span>}
          </div>
          {wellnessTrend.overallAverage !== null ? (
            <>
              <div style={{ display: 'grid', gap: 4, gridTemplateColumns: 'repeat(4, 1fr)', marginBottom: 10, textAlign: 'center' }}>
                {wellnessTrend.buckets.map((bucket) => (
                  <div key={bucket.label}>
                    <div style={{ color: 'var(--color-text-secondary)', fontSize: 10 }}>{bucket.label}</div>
                    <div className="if-mock-num" style={{ color: bucket.average !== null && bucket.average < 3 ? 'hsl(25,80%,60%)' : 'var(--color-text-primary)', fontSize: 15, fontWeight: 500 }}>{bucket.average !== null ? bucket.average.toFixed(1) : '--'}</div>
                  </div>
                ))}
              </div>
              <div className="if-divider-top" style={{ display: 'grid', gap: 4, gridTemplateColumns: 'repeat(5, 1fr)', textAlign: 'center' }}>
                {WELLNESS_METRICS.map(({ key, label }) => {
                  const average = wellnessTrend.metricAverages[key]
                  return (
                    <div key={key}>
                      <div style={{ color: 'var(--color-text-secondary)', fontSize: 10 }}>{label}</div>
                      <div className="if-mock-num" style={{ color: average !== null && average < 3 ? 'hsl(25,80%,60%)' : 'var(--color-text-primary)', fontSize: 13 }}>{average !== null ? average.toFixed(1) : '--'}</div>
                    </div>
                  )
                })}
              </div>
            </>
          ) : (
            <Text size="sm" c="dimmed">No wellness entries yet.</Text>
          )}
        </section>

        <section className="if-mock-card">
          <div className="if-mock-card-label"><Activity size={12} /> Fatigue state</div>
          {fatigueSectionLoading ? (
            <Group gap="xs"><Loader size="sm" /><Text size="sm" c="dimmed">Loading...</Text></Group>
          ) : currentBlockFatigueComponents || currentBlockFatigue !== null ? (
            <>
              <div className="if-mock-num" style={{ color: fatigueColor(currentBlockFatigue), fontSize: 42, fontWeight: 500, lineHeight: 1, marginBottom: 4 }}>
                {currentBlockFatigue !== null ? `${(currentBlockFatigue * 100).toFixed(0)}%` : 'N/A'}
              </div>
              <div style={{ color: 'var(--color-text-secondary)', fontSize: 12, marginBottom: 8 }}>{fatigueLabel(currentBlockFatigue)} current state</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 8 }}>
                {typeof currentBlockFatigueComponents?.window_mean_fi === 'number' && <span className="if-mock-pill">Mean {(currentBlockFatigueComponents.window_mean_fi * 100).toFixed(0)}%</span>}
                {typeof currentBlockFatigueComponents?.window_peak_fi === 'number' && <span className="if-mock-pill" style={{ background: 'var(--color-background-warning)', borderColor: 'var(--color-border-warning)', color: 'var(--color-text-warning)' }}>Peak {(currentBlockFatigueComponents.window_peak_fi * 100).toFixed(0)}%</span>}
                {currentBlockFatigueComponents?.fatigue_context_confidence && <span className="if-mock-pill" style={{ background: 'var(--color-background-success)', borderColor: 'var(--color-border-success)', color: 'var(--color-text-success)' }}>{currentBlockFatigueComponents.fatigue_context_confidence} confidence</span>}
              </div>
              <div style={{ color: 'var(--color-text-secondary)', fontSize: 11, lineHeight: 1.6 }}>
                Failures {((currentBlockFatigueComponents?.failure_stress ?? 0) * 100).toFixed(0)}% · Spike {((currentBlockFatigueComponents?.acute_spike_stress ?? 0) * 100).toFixed(0)}% · RPE {((currentBlockFatigueComponents?.rpe_stress ?? 0) * 100).toFixed(0)}% · Reservoir {((currentBlockFatigueComponents?.chronic_load_stress ?? 0) * 100).toFixed(0)}% · Strain {((currentBlockFatigueComponents?.monotony_stress ?? 0) * 100).toFixed(0)}%
              </div>
              <div style={{ color: 'var(--color-text-secondary)', fontSize: 10, marginTop: 4 }}>
                {dashboardAnalysisWindow ? `${dashboardAnalysisWindow.start} -> ${dashboardAnalysisWindow.end}` : 'Current block'}
              </div>
            </>
          ) : dashboardAnalysisError ? (
            <Text size="sm" c="red">Analysis unavailable.</Text>
          ) : (
            <Text size="sm" c="dimmed">Fatigue analysis unavailable.</Text>
          )}
        </section>

        <section className="if-mock-card" style={{ minWidth: 0 }}>
          <div className="if-mock-card-label"><TrendingUp size={12} /> Per-lift breakdown</div>
          <div style={{ borderBottom: '0.5px solid var(--color-border-tertiary)', color: 'var(--color-text-secondary)', display: 'grid', fontSize: 10, gap: 4, gridTemplateColumns: '1fr 80px 60px', letterSpacing: '0.07em', marginBottom: 4, paddingBottom: 5, textTransform: 'uppercase' }}>
            <span>Lift</span><span style={{ textAlign: 'right' }}>Current</span><span style={{ textAlign: 'right' }}>Trend</span>
          </div>
          {workloadSectionLoading ? (
            <Text size="sm" c="dimmed">Loading lift data...</Text>
          ) : currentBlockWeekly?.lifts ? liftBreakdownRows.map((row) => (
            <div className="if-lift-row" key={row.lift}>
              <span style={{ color: 'var(--color-text-primary)', fontSize: 13 }}>{LIFT_LABELS[row.lift]}</span>
              <span className="if-mock-num" style={{ fontSize: 13, textAlign: 'right' }}>{row.endStrength !== null ? displayWeight(row.endStrength, unit) : '--'}</span>
              <span className="if-mock-num" style={{ color: typeof row.progressionRate === 'number' && row.progressionRate > 0 ? 'var(--color-text-success)' : 'var(--color-text-secondary)', fontSize: 11, textAlign: 'right' }}>{typeof row.progressionRate === 'number' ? `${formatSignedKg(row.progressionRate, unit)}/wk` : '--'}</span>
            </div>
          )) : dashboardAnalysisError ? (
            <Text size="sm" c="red">Lift analysis unavailable.</Text>
          ) : (
            <Text size="sm" c="dimmed">Lift breakdown unavailable.</Text>
          )}
        </section>
      </div>

      <div className="if-dashboard-row if-dashboard-row-bottom">
        <section className="if-mock-card if-dashboard-phases-card">
          <div style={{ alignItems: 'center', display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}>
            <div>
              <div className="if-mock-card-label" style={{ marginBottom: 0 }}><TrendingUp size={12} /> Program phases</div>
              <div className="if-dashboard-phase-week">Week {currentWeekNumber}</div>
            </div>
            {editingPhases ? (
              <div style={{ display: 'flex', gap: 4 }}>
                <button className="if-mock-icon-button" onClick={addPhase} aria-label="Add phase"><Plus size={15} /></button>
                <button className="if-mock-icon-button" onClick={savePhases} aria-label="Save phases"><Save size={15} /></button>
                <button className="if-mock-icon-button" onClick={() => setEditingPhases(false)} aria-label="Cancel phase edit"><X size={15} /></button>
              </div>
            ) : (
              <button className="if-mock-icon-button" onClick={startEditingPhases} disabled={readOnly} aria-label="Edit phases"><Edit2 size={15} /></button>
            )}
          </div>
          {editingPhases ? (
            <Stack gap={6}>
              {localPhases.map((phase, idx) => (
                <Group key={`${phase.name}-${idx}`} gap="xs" wrap="nowrap">
                  <Box w={9} h={9} style={{ borderRadius: '50%', backgroundColor: phaseColor({ ...phase, block: 'current' }, localPhases), flexShrink: 0 }} />
                  <TextInput value={phase.name} onChange={(e) => updatePhase(idx, 'name', e.currentTarget.value)} size="xs" style={{ flex: 1 }} />
                  <TextInput type="number" value={phase.start_week} onChange={(e) => updatePhase(idx, 'start_week', Number(e.currentTarget.value) || 0)} size="xs" style={{ width: 48 }} />
                  <Text size="xs" c="dimmed">-</Text>
                  <TextInput type="number" value={phase.end_week} onChange={(e) => updatePhase(idx, 'end_week', Number(e.currentTarget.value) || 0)} size="xs" style={{ width: 48 }} />
                  <button className="if-mock-icon-button" onClick={() => removePhase(idx)} aria-label="Remove phase"><Trash2 size={13} /></button>
                </Group>
              ))}
            </Stack>
          ) : currentBlockPhases.length > 0 ? (
            <div className="if-dashboard-phase-list">
              {currentBlockPhases.map((phase) => {
                const color = phaseColor(phase, currentBlockPhases)
                const state = phaseState(phase, currentWeekNumber)
                return (
                  <div
                    key={`${phase.name}-${phase.start_week}`}
                    className="if-dashboard-phase-row"
                    data-status={state}
                    data-testid={`dashboard-phase-${state}`}
                  >
                    <span className="if-dashboard-phase-dot" style={{ background: color }} />
                    <span className="if-dashboard-phase-range">W{phase.start_week}-{phase.end_week}</span>
                    <span className="if-dashboard-phase-name">{phase.name}</span>
                  </div>
                )
              })}
            </div>
          ) : (
            <Text size="sm" c="dimmed">No phases defined for the current block.</Text>
          )}
        </section>

        <section className="if-mock-card">
          <div style={{ alignItems: 'center', display: 'flex', flexWrap: 'wrap', gap: 6, justifyContent: 'space-between', marginBottom: 12 }}>
            <div className="if-mock-card-label" style={{ marginBottom: 0 }}><Dumbbell size={12} /> Lift style profiles</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
              {LIFT_ORDER.map((lift) => (
                <Link key={lift} className="if-mock-button" to={`/lift-profiles/${lift}`} aria-disabled={readOnly} style={{ fontSize: 11, minHeight: 24, padding: '3px 9px' }}>
                  <Edit2 size={11} /> {LIFT_LABELS[lift]}
                </Link>
              ))}
            </div>
          </div>
          <div style={{ display: 'grid', gap: 10, gridTemplateColumns: 'repeat(3, minmax(0, 1fr))' }}>
            {displayProfiles.map((profile) => {
              const color = LIFT_COLORS[profile.lift]
              const hasData = profile.style_notes || profile.sticking_points || profile.primary_muscle
              return (
                <div key={profile.lift} style={{ minWidth: 0 }}>
                  <div style={{ color, fontSize: 11, fontWeight: 500, letterSpacing: '0.06em', marginBottom: 6, textTransform: 'uppercase' }}>{LIFT_LABELS[profile.lift]}</div>
                  {hasData ? (
                    <>
                      <div style={{ color: 'var(--color-text-secondary)', fontSize: 11, lineHeight: 1.6, marginBottom: 6 }}>{profile.style_notes || 'No style notes yet.'}</div>
                      <div style={{ color: 'var(--color-text-secondary)', fontSize: 10, letterSpacing: '0.07em', marginBottom: 4, textTransform: 'uppercase' }}>Sticking point</div>
                      <div style={{ color: 'var(--color-text-warning)', fontSize: 11, lineHeight: 1.5, marginBottom: 6 }}>{profile.sticking_points || '--'}</div>
                      <div style={{ color: 'var(--color-text-secondary)', fontSize: 10, letterSpacing: '0.07em', marginBottom: 4, textTransform: 'uppercase' }}>Primary driver</div>
                      <div style={{ color: 'var(--color-text-secondary)', fontSize: 11 }}>{profile.primary_muscle || '--'}</div>
                      <div style={{ marginTop: 8 }}>
                        <span className="if-mock-pill" style={{ background: 'var(--color-background-warning)', borderColor: 'var(--color-border-warning)', color: 'var(--color-text-warning)' }}>
                          {profile.volume_tolerance} volume tolerance
                        </span>
                      </div>
                    </>
                  ) : (
                    <Text size="xs" c="dimmed">No profile yet.</Text>
                  )}
                </div>
              )
            })}
          </div>
        </section>
      </div>

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
                disabled={readOnly}
              >
                Review
              </Button>
              <Group gap="sm">
                <Button
                  variant="light"
                  leftSection={<Sparkles size={16} />}
                  loading={profileGuideRewriting}
                  onClick={runRewriteProfile}
                  disabled={readOnly}
                >
                  Rewrite
                </Button>
                <Button
                  variant="light"
                  leftSection={<Sparkles size={16} />}
                  loading={profileGuideEstimating}
                  disabled={!profileGuideCanEstimate || readOnly}
                  onClick={runEstimateStimulus}
                >
                  Estimate Stimulus
                </Button>
                <Button onClick={applyProfileGuide} disabled={readOnly}>Apply</Button>
              </Group>
            </Group>
          </Stack>
        )}
      </Modal>
    </Stack>
  )
}
