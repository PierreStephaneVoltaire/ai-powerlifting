import { useState, useEffect, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  Activity, Download, AlertTriangle, CheckCircle, TrendingUp, Dumbbell, Trophy,
  Scale, Moon, Beef, Ruler, Utensils, Info, RefreshCw,
} from 'lucide-react'
import {
  fetchAnalysisManifest,
  fetchAnalysisSection,
  invalidateAnalysisSections,
  queueAnalysisSections,
  type AnalysisSectionKey,
  type AnalysisWindow,
  type AnalysisWindowKey,
  type WeeklyAnalysis,
} from '@/api/analytics'
import { useProgramStore } from '@/store/programStore'
import { useAuth } from '@/auth/AuthProvider'
import { fetchWeightLog, fetchGlossary } from '@/api/client'
import { executedSets, exerciseVolume, normalizeExerciseName } from '@/utils/volume'
import { useSettingsStore } from '@/store/settingsStore'
import { calculateDots } from '@/utils/dots'
import { calculateIpfGl, getIpfGlModeLabel, type IpfGlMode } from '@/utils/ipfGl'
import { toDisplayUnit, displayWeight } from '@/utils/units'
import { buildBodyweightTrend, latestBodyweightOnOrBefore, mergeBodyweightEntries } from '@/utils/bodyweight'
import { programWeekEndDate, programWeekStartDate, resolveTrainingWeekForDate, trainingWeekStartForDate, weekStartForBlock } from '@/utils/weekStart'
import { FORMULA_DESCRIPTIONS } from '@/constants/formulaDescriptions'
import type { WeightEntry, GlossaryExercise, ExerciseCategory, Session, WeekStartDay } from '@powerlifting/types'
import { ResponsiveContainer, LineChart, Line, CartesianGrid, XAxis, YAxis, Tooltip as RechartsTooltip, ReferenceLine, Legend } from 'recharts'
import {
  Stack, Group, Paper, SimpleGrid, Text, Title, Badge, Table,
  Button, Center, Select, Progress, Accordion, SegmentedControl, Box, Loader, Tooltip,
} from '@mantine/core'
import { AiAnalysis } from '@/components/analysis/AiAnalysis'
import { AlertsStrip } from '@/components/analysis/AlertsStrip'
import { LifetimeComparePanel, PastBlocksPanel } from '@/components/analysis/BlockAnalytics'
import { PeakingTimeline } from '@/components/analysis/PeakingTimeline'
import { WeeklyData } from '@/components/analysis/WeeklyData'

// ─── Helpers ──────────────────────────────────────────────────────────────────

type WeeksMode = number | 'current' | 'block'
type AnalysisSection = 'weekly' | 'blocks' | 'compare'
type AnalysisViewMode = 'raw' | 'graph'

const ANALYSIS_SECTIONS: AnalysisSection[] = ['weekly', 'blocks', 'compare']
const ANALYSIS_VIEW_MODES: AnalysisViewMode[] = ['raw', 'graph']
const WEEK_MODE_NUMBERS = new Set(['1', '2', '4', '8'])

function parseAnalysisSection(searchParams: URLSearchParams): AnalysisSection {
  const raw = searchParams.get('type') ?? searchParams.get('section')
  return ANALYSIS_SECTIONS.includes(raw as AnalysisSection) ? raw as AnalysisSection : 'weekly'
}

function parseAnalysisViewMode(raw: string | null): AnalysisViewMode {
  return ANALYSIS_VIEW_MODES.includes(raw as AnalysisViewMode) ? raw as AnalysisViewMode : 'raw'
}

function parseWeeksMode(raw: string | null): WeeksMode {
  if (raw === 'current' || raw === 'block') return raw
  if (raw && WEEK_MODE_NUMBERS.has(raw)) return Number(raw)
  return 4
}

const RPE_TABLE_PRIMARY = new Map<string, number>([
  ['1-10', 1.000], ['2-10', 0.960], ['3-10', 0.930], ['4-10', 0.900], ['5-10', 0.880], ['6-10', 0.860],
  ['1-9', 1.000], ['2-9', 0.940], ['3-9', 0.900], ['4-9', 0.870], ['5-9', 0.845], ['6-9', 0.825],
  ['1-8', 1.000], ['2-8', 0.920], ['3-8', 0.875], ['4-8', 0.845], ['5-8', 0.815], ['6-8', 0.795],
  ['1-7', 1.000], ['2-7', 0.900], ['3-7', 0.850], ['4-7', 0.820], ['5-7', 0.795], ['6-7', 0.775],
  ['1-6', 1.000], ['2-6', 0.880], ['3-6', 0.830], ['4-6', 0.800], ['5-6', 0.775], ['6-6', 0.755],
])

const CONSERVATIVE_REP_PCT: Record<number, number> = {
  1: 1.000,
  2: 0.955,
  3: 0.925,
  4: 0.898,
  5: 0.875,
}

function estimateAnalysisE1rm(kg: number, reps: number, rpe?: number | null): number | null {
  if (kg <= 0 || reps <= 0) return null

  if (rpe != null && Number.isFinite(rpe)) {
    const rpeInt = Math.trunc(rpe)
    if (reps >= 1 && reps <= 6 && rpeInt >= 6 && rpeInt <= 10) {
      const pct = RPE_TABLE_PRIMARY.get(`${reps}-${rpeInt}`)
      return pct ? kg / pct : null
    }
    return null
  }

  const pct = CONSERVATIVE_REP_PCT[reps]
  return pct ? kg / pct : null
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

function complianceBadgeColor(pct: number | null): string {
  if (pct === null) return 'gray'
  if (pct >= 80) return 'green'
  if (pct >= 50) return 'yellow'
  return 'red'
}

function readinessZoneLabel(zone: string): string {
  if (zone === 'green') return 'Ready'
  if (zone === 'yellow') return 'Caution'
  if (zone === 'red') return 'Recovery'
  return zone.replace(/_/g, ' ')
}

function compStatusBadge(status: string) {
  const colors: Record<string, string> = {
    confirmed: 'green',
    optional: 'blue',
    completed: 'gray',
    skipped: 'gray',
  }
  return <Badge variant="light" color={colors[status] || 'gray'} size="sm">{status}</Badge>
}

function isInsufficientData(value: unknown): value is { status: 'insufficient_data'; reason: string } {
  return !!value && typeof value === 'object' && 'status' in value
}

function toDateStr(date: Date): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function getAnalysisWindow(
  mode: WeeksMode,
  sessions: Session[] = [],
  programStart?: string | null,
  weekStartDay: WeekStartDay = 'Monday',
  asOfDate = toDateStr(new Date()),
) {
  const currentWeek = resolveTrainingWeekForDate(
    asOfDate,
    programStart ?? sessions[0]?.date ?? asOfDate,
    weekStartDay,
    sessions,
    'current',
  )
  let weekStart: number
  let weekEnd: number

  if (mode === 'current') {
    weekStart = currentWeek
    weekEnd = currentWeek
  } else if (mode === 'block') {
    weekStart = 1
    weekEnd = currentWeek
  } else {
    const weeks = Math.max(1, mode)
    weekEnd = currentWeek
    weekStart = Math.max(1, currentWeek - weeks)
  }

  const start = programWeekStartDate(programStart ?? sessions[0]?.date ?? asOfDate, weekStart, weekStartDay)
  const end = programWeekEndDate(programStart ?? sessions[0]?.date ?? asOfDate, weekEnd, weekStartDay)

  return {
    start: programStart && start < programStart ? programStart : start,
    end,
    weekStart,
    weekEnd,
    weeks: Math.max(1, weekEnd - weekStart + 1),
    currentWeek,
  }
}

function banisterBadgeColor(tsb: number) {
  if (tsb < -30) return 'red'
  if (tsb < -10) return 'orange'
  if (tsb <= 5) return 'yellow'
  if (tsb <= 15) return 'green'
  return 'gray'
}

function decouplingBadgeColor(value: number) {
  if (value < 0) return 'red'
  if (value < 5) return 'yellow'
  return 'green'
}

function taperQualityBadgeColor(label: string) {
  if (label === 'excellent') return 'green'
  if (label === 'good') return 'blue'
  if (label === 'acceptable') return 'yellow'
  return 'red'
}

function specificityStatusBadgeColor(status?: string) {
  if (status === 'within_expected') return 'green'
  if (status === 'below_expected') return 'yellow'
  if (status === 'above_expected') return 'red'
  return 'gray'
}

function specificityStatusLabel(status?: string) {
  if (status === 'within_expected') return 'Within expected range'
  if (status === 'below_expected') return 'Below expected'
  if (status === 'above_expected') return 'Above expected'
  return 'No band'
}

function volumeConfidenceColor(confidence?: string) {
  if (confidence === 'high') return 'green'
  if (confidence === 'medium') return 'blue'
  if (confidence === 'low') return 'yellow'
  return 'gray'
}

const LIFT_LABELS: Record<string, string> = { squat: 'Squat', bench: 'Bench', deadlift: 'Deadlift' }

const DEFAULT_INOL_THRESHOLDS: Record<string, { low: number; high: number }> = {
  squat: { low: 1.6, high: 3.5 },
  bench: { low: 2.0, high: 5.0 },
  deadlift: { low: 1.0, high: 2.5 },
}

const ACWR_ZONE_META: Record<string, { color: string; label: string }> = {
  detraining_trend: { color: 'gray', label: 'Detraining trend' },
  steady_load: { color: 'green', label: 'Steady load' },
  rapid_increase: { color: 'yellow', label: 'Rapid increase' },
  load_spike: { color: 'red', label: 'Load spike' },
  undertraining: { color: 'gray', label: 'Detraining trend' },
  optimal: { color: 'green', label: 'Steady load' },
  caution: { color: 'yellow', label: 'Rapid increase' },
  danger: { color: 'red', label: 'Load spike' },
  unknown: { color: 'gray', label: 'Unknown' },
}

function getInolThresholds(lift: string, thresholds?: Record<string, { low: number; high: number }>) {
  return thresholds?.[lift] ?? DEFAULT_INOL_THRESHOLDS[lift] ?? { low: 2.0, high: 4.0 }
}

function getInolZoneMeta(value: number, thresholds: { low: number; high: number }) {
  if (value < thresholds.low) {
    return { color: 'yellow', label: 'Low stimulus' }
  }
  if (value > thresholds.high) {
    return { color: 'red', label: 'Overreaching' }
  }
  return { color: 'green', label: 'Productive' }
}

function getAcwrZoneMeta(zone?: string | null) {
  return ACWR_ZONE_META[zone ?? 'unknown'] ?? {
    color: 'gray',
    label: zone ? zone.replace(/_/g, ' ') : 'Unknown',
  }
}

type TrendRow = {
  week: number
  squat: number | null
  bench: number | null
  deadlift: number | null
  total: number | null
  dots: number | null
  ipfGl: number | null
  ipfGlMode: IpfGlMode | null
}

function InfoLabel({ label, help }: { label: string; help: string }) {
  return (
    <Group gap={4} justify="center" wrap="nowrap">
      <Text fz="xs" c="dimmed">{label}</Text>
      <Tooltip label={help} withArrow multiline w={260}>
        <Info size={12} style={{ cursor: 'help', color: 'var(--mantine-color-gray-6)' }} />
      </Tooltip>
    </Group>
  )
}

function analysisKeyForMode(mode: WeeksMode): AnalysisWindowKey {
  if (mode === 'current') return 'current'
  if (mode === 'block') return 'block'
  return `previous_${mode}` as AnalysisWindowKey
}

const DETERMINISTIC_ANALYSIS_SECTIONS: AnalysisSectionKey[] = [
  'overview',
  'fatigue_readiness',
  'peaking',
  'workload',
  'alerts',
]

function emptyWeeklyAnalysis(window: AnalysisWindow): WeeklyAnalysis {
  return {
    week: window.currentWeek,
    selected_week_start: window.weekStart,
    selected_week_end: window.weekEnd,
    selected_week_count: window.weeks,
    window_start: window.start,
    window_end: window.end,
    selected_session_context: [],
    block: 'current',
    lifts: {},
    fatigue_index: null,
    fatigue_components: null,
    compliance: null,
    current_maxes: null,
    estimated_dots: null,
    estimated_dots_reason: null,
    projections: [],
    projection_reason: null,
    flags: [],
    sessions_analyzed: 0,
    exercise_stats: {},
    alerts: [],
  }
}

function mergeWeeklySections(
  window: AnalysisWindow,
  payloads: Partial<Record<AnalysisSectionKey, Partial<WeeklyAnalysis>>>,
): WeeklyAnalysis | null {
  const hasPayload = DETERMINISTIC_ANALYSIS_SECTIONS.some((section) => Boolean(payloads[section]))
  if (!hasPayload) return null
  return Object.assign(
    emptyWeeklyAnalysis(window),
    ...DETERMINISTIC_ANALYSIS_SECTIONS.map((section) => payloads[section] ?? {}),
  )
}

// ─── Main component ────────────────────────────────────────────────────────────

export default function AnalysisPage() {
  const { program, version } = useProgramStore()
  const { unit, sex } = useSettingsStore()
  const { readOnly } = useAuth()
  const [searchParams, setSearchParams] = useSearchParams()

  const weeksMode = parseWeeksMode(searchParams.get('weeks'))
  const viewMode = parseAnalysisViewMode(searchParams.get('view'))
  const activeSection = parseAnalysisSection(searchParams)
  const analysisKey = analysisKeyForMode(weeksMode)
  const [analysisWindows, setAnalysisWindows] = useState<Record<AnalysisWindowKey, AnalysisWindow> | null>(null)
  const [sectionPayloads, setSectionPayloads] = useState<Partial<Record<AnalysisSectionKey, Partial<WeeklyAnalysis>>>>({})
  const [sectionStatuses, setSectionStatuses] = useState<Partial<Record<AnalysisSectionKey, string>>>({})
  const [latestGeneratedAt, setLatestGeneratedAt] = useState<string | null>(null)
  const [analysisRefreshNonce, setAnalysisRefreshNonce] = useState(0)
  const [loading, setLoading] = useState(false)
  const [regenerating, setRegenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [weightLog, setWeightLog] = useState<WeightEntry[]>([])
  const [glossary, setGlossary] = useState<GlossaryExercise[]>([])
  const asOfDate = useMemo(() => toDateStr(new Date()), [])
  const currentWeekStartDay = weekStartForBlock(program, 'current')

  const updateAnalysisParams = (updates: { type?: AnalysisSection; weeks?: WeeksMode; view?: AnalysisViewMode }) => {
    setSearchParams((current) => {
      const next = new URLSearchParams(current)

      if (updates.type !== undefined) {
        next.delete('section')
        updates.type === 'weekly' ? next.delete('type') : next.set('type', updates.type)
      }

      if (updates.weeks !== undefined) {
        String(updates.weeks) === '4' ? next.delete('weeks') : next.set('weeks', String(updates.weeks))
      }

      if (updates.view !== undefined) {
        updates.view === 'raw' ? next.delete('view') : next.set('view', updates.view)
      }

      return next
    })
  }

  const analysisWindow = useMemo(
    () => {
      const cached = analysisWindows?.[analysisKey]
      if (cached) return cached
      const fallback = getAnalysisWindow(weeksMode, program?.sessions ?? [], program?.meta?.program_start, currentWeekStartDay, asOfDate)
      return {
        key: analysisKey,
        label: analysisKey === 'current' ? 'Current Week' : analysisKey === 'block' ? 'Full Block' : `Previous ${weeksMode} Week${weeksMode === 1 ? '' : 's'}`,
        ...fallback,
      }
    },
    [analysisKey, analysisWindows, asOfDate, currentWeekStartDay, program?.meta?.program_start, program?.sessions, weeksMode],
  )
  const data = useMemo(
    () => mergeWeeklySections(analysisWindow, sectionPayloads),
    [analysisWindow, sectionPayloads],
  )

  const effectiveWeeks = analysisWindow.weeks
  const pendingSectionCount = useMemo(
    () => DETERMINISTIC_ANALYSIS_SECTIONS.filter((section) => {
      const status = sectionStatuses[section]
      return status === 'pending' || status === 'running' || status === 'missing'
    }).length,
    [sectionStatuses],
  )

  const competitions = useMemo(() => {
    return (program?.competitions || []).sort((a, b) => a.date.localeCompare(b.date))
  }, [program?.competitions])

  const upcomingCompetition = useMemo(() => {
    return competitions.find(c => (c.status === 'confirmed' || c.status === 'optional') && c.date >= asOfDate) || null
  }, [asOfDate, competitions])

  const analysisWindowStartStr = useMemo(
    () => analysisWindow.start,
    [analysisWindow.start],
  )
  const analysisWindowEndStr = analysisWindow.end

  const banister = data?.banister && !isInsufficientData(data.banister) ? data.banister : null
  const decoupling = data?.decoupling && !isInsufficientData(data.decoupling) ? data.decoupling : null
  const taperQuality = data?.taper_quality && !isInsufficientData(data.taper_quality) ? data.taper_quality : null
  const projectionCalibration = data?.projection_calibration ?? null
  const peakingTimeline = data?.peaking_timeline ?? null
  const volumeLandmarkEntries = data?.volume_landmarks
    ? (Object.entries(data.volume_landmarks).filter(([, value]) => !isInsufficientData(value)) as Array<[string, any]>)
    : []

  useEffect(() => {
    let cancelled = false
    let pollTimer: number | undefined

    async function pollSections() {
      const statuses = await Promise.all(
        DETERMINISTIC_ANALYSIS_SECTIONS.map((section) =>
          fetchAnalysisSection<Partial<WeeklyAnalysis>>(asOfDate, analysisKey, section),
        ),
      )
      if (cancelled) return

      setSectionStatuses(Object.fromEntries(statuses.map((status) => [status.sectionKey, status.status])))
      setSectionPayloads((current) => {
        const next = { ...current }
        for (const status of statuses) {
          if (status.status === 'complete' && status.payload) {
            next[status.sectionKey] = status.payload
          }
        }
        return next
      })
      const generated = statuses
        .map((status) => status.generatedAt)
        .filter((value): value is string => Boolean(value))
        .sort()
        .slice(-1)[0]
      if (generated) setLatestGeneratedAt(generated)

      const terminal = statuses.every((status) => status.status === 'complete' || status.status === 'error')
      const hasAnyPayload = statuses.some((status) => status.status === 'complete' && status.payload)
      setLoading(!terminal && !hasAnyPayload)
      if (!terminal) {
        pollTimer = window.setTimeout(() => {
          pollSections().catch((e) => {
            if (!cancelled) setError(e.message)
          })
        }, 2000)
      }
    }

    setLoading(true)
    setError(null)
    setLatestGeneratedAt(null)
    setSectionPayloads({})
    setSectionStatuses({})

    fetchAnalysisManifest(asOfDate, analysisKey)
      .then((manifest) => {
        if (cancelled) return
        setAnalysisWindows(manifest.windows)
        setSectionStatuses(Object.fromEntries(
          DETERMINISTIC_ANALYSIS_SECTIONS.map((section) => [section, manifest.sections[section]?.status ?? 'missing']),
        ))
        return queueAnalysisSections({
          asOfDate,
          windowKey: analysisKey,
          sections: DETERMINISTIC_ANALYSIS_SECTIONS,
        })
      })
      .then(() => pollSections())
      .catch((e) => {
        if (!cancelled) {
          setError(e.message)
          setLoading(false)
        }
      })

    return () => {
      cancelled = true
      if (pollTimer !== undefined) window.clearTimeout(pollTimer)
    }
  }, [analysisKey, analysisRefreshNonce, asOfDate])

  useEffect(() => {
    fetchWeightLog(version).then(setWeightLog).catch(console.error)
    fetchGlossary().then(setGlossary).catch(console.error)
  }, [version])

  const handleRegenerateAnalysis = async () => {
    setRegenerating(true)
    setError(null)
    try {
      setSectionPayloads({})
      setSectionStatuses({})
      await invalidateAnalysisSections({
        asOfDate,
        windowKey: analysisKey,
        sections: DETERMINISTIC_ANALYSIS_SECTIONS,
      })
      setAnalysisRefreshNonce((value) => value + 1)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setRegenerating(false)
    }
  }

  const filteredSessions = useMemo(() => {
    if (!program?.sessions) return []
    return program.sessions.filter(s =>
      (s.block ?? 'current') === 'current' &&
      s.completed &&
      s.week_number >= analysisWindow.weekStart &&
      s.week_number <= analysisWindow.weekEnd &&
      s.date <= analysisWindowEndStr
    )
  }, [program?.sessions, analysisWindow.weekEnd, analysisWindow.weekStart, analysisWindowEndStr])

  const bodyweightSessions = useMemo(() => {
    if (!program?.sessions) return []
    return program.sessions.filter(s =>
      (s.block ?? 'current') === 'current' &&
      s.status !== 'skipped' &&
      s.date >= analysisWindowStartStr &&
      s.date <= analysisWindowEndStr
    )
  }, [analysisWindowEndStr, analysisWindowStartStr, program?.sessions])

  const glossaryMuscles = useMemo(() => {
    const lookup = new Map<string, { primary: string[]; secondary: string[]; tertiary: string[] }>()
    for (const ex of glossary) {
      lookup.set(normalizeExerciseName(ex.name), {
        primary: ex.primary_muscles,
        secondary: ex.secondary_muscles,
        tertiary: ex.tertiary_muscles ?? [],
      })
    }
    return lookup
  }, [glossary])

  const glossaryCategory = useMemo(() => {
    const lookup = new Map<string, ExerciseCategory>()
    for (const ex of glossary) {
      lookup.set(normalizeExerciseName(ex.name), ex.category)
    }
    return lookup
  }, [glossary])

  const muscleGroupAvgWeekly = useMemo(() => {
    if (!glossaryMuscles.size || !filteredSessions.length) return { sets: {}, volume: {} }
    const periodWeeks = Math.max(1, effectiveWeeks)
    const mgSets: Record<string, number> = {}
    const mgVol: Record<string, number> = {}
    for (const s of filteredSessions) {
      for (const ex of s.exercises || []) {
        const muscles = glossaryMuscles.get(normalizeExerciseName(ex.name))
        if (!muscles) continue
        const sets = executedSets(ex)
        const vol = exerciseVolume(ex)
        for (const m of muscles.primary) { mgSets[m] = (mgSets[m] || 0) + sets; mgVol[m] = (mgVol[m] || 0) + vol }
        for (const m of muscles.secondary) { mgSets[m] = (mgSets[m] || 0) + sets * 0.5; mgVol[m] = (mgVol[m] || 0) + vol * 0.5 }
        for (const m of muscles.tertiary) { mgSets[m] = (mgSets[m] || 0) + sets * 0.25; mgVol[m] = (mgVol[m] || 0) + vol * 0.25 }
      }
    }
    const avgSets: Record<string, number> = {}
    const avgVol: Record<string, number> = {}
    for (const m of Object.keys(mgSets)) {
      avgSets[m] = Math.round((mgSets[m] / periodWeeks) * 10) / 10
      avgVol[m] = Math.round(mgVol[m] / periodWeeks)
    }
    return { sets: avgSets, volume: avgVol }
  }, [effectiveWeeks, glossaryMuscles, filteredSessions])

  const perLiftDetails = useMemo(() => {
    if (!glossaryCategory.size || !filteredSessions.length) return {}
    const numWeeks = new Set(filteredSessions.map(s => s.week_number)).size || 1
    const result: Record<string, { frequency: number; raw_sets: number; accessories: { name: string; sets: number; volume: number }[] }> = {}
    for (const [liftName, category] of [['squat', 'squat'], ['bench', 'bench'], ['deadlift', 'deadlift']] as const) {
      let liftSessions = 0, rawSets = 0
      const accessoryMap: Record<string, { sets: number; volume: number }> = {}
      for (const s of filteredSessions) {
        let hasLift = false
        for (const ex of s.exercises || []) {
          const sets = executedSets(ex)
          if (sets <= 0) continue
          const exLower = ex.name.toLowerCase().trim()
          const info = glossaryCategory.get(normalizeExerciseName(ex.name))
          const isMainLift = exLower === liftName || (liftName === 'bench' && exLower === 'bench press')
          if (isMainLift || (info && info === category)) hasLift = true
          if (isMainLift) rawSets += sets
          if (info && info === category && !isMainLift) {
            const vol = exerciseVolume(ex)
            if (!accessoryMap[ex.name]) accessoryMap[ex.name] = { sets: 0, volume: 0 }
            accessoryMap[ex.name].sets += sets
            accessoryMap[ex.name].volume += vol
          }
        }
        if (hasLift) liftSessions++
      }
      result[liftName] = {
        frequency: Math.round((liftSessions / numWeeks) * 10) / 10,
        raw_sets: rawSets,
        accessories: Object.entries(accessoryMap).map(([name, d]) => ({ name, ...d })).sort((a, b) => b.volume - a.volume),
      }
    }
    return result
  }, [glossaryCategory, filteredSessions])

  const avgSessionsPerWeek = data ? Math.round((data.sessions_analyzed / effectiveWeeks) * 10) / 10 : null

  const nutritionTrend = useMemo(() => {
    if (!program?.diet_notes?.length) return null
    const inWindow = program.diet_notes
      .filter(n => n.date >= analysisWindowStartStr && n.date <= analysisWindowEndStr)
      .sort((a, b) => a.date.localeCompare(b.date))
    if (!inWindow.length) return null

    const withCalories = inWindow.filter(n => n.avg_daily_calories != null)
    const withWater = inWindow.filter(n => n.water_intake != null)
    const withProtein = inWindow.filter(n => n.avg_protein_g != null)
    const withCarb = inWindow.filter(n => n.avg_carb_g != null)
    const withFat = inWindow.filter(n => n.avg_fat_g != null)
    const withSleep = inWindow.filter(n => n.avg_sleep_hours != null)
    const consistent = inWindow.filter(n => n.consistent).length

    const weeklyMap = new Map<string, { calories: number[]; water: number[]; protein: number[]; carb: number[]; fat: number[]; sleep: number[]; consistent: number; total: number }>()
    for (const note of inWindow) {
      const weekKey = trainingWeekStartForDate(note.date, program.meta.program_start, currentWeekStartDay)
      const bucket = weeklyMap.get(weekKey) || { calories: [], water: [], protein: [], carb: [], fat: [], sleep: [], consistent: 0, total: 0 }
      if (note.avg_daily_calories != null) bucket.calories.push(note.avg_daily_calories)
      if (note.water_intake != null) bucket.water.push(note.water_intake)
      if (note.avg_protein_g != null) bucket.protein.push(note.avg_protein_g)
      if (note.avg_carb_g != null) bucket.carb.push(note.avg_carb_g)
      if (note.avg_fat_g != null) bucket.fat.push(note.avg_fat_g)
      if (note.avg_sleep_hours != null) bucket.sleep.push(note.avg_sleep_hours)
      if (note.consistent) bucket.consistent += 1
      bucket.total += 1
      weeklyMap.set(weekKey, bucket)
    }

    const avg = (arr: number[]) => arr.length ? arr.reduce((s, v) => s + v, 0) / arr.length : null

    const weekly = Array.from(weeklyMap.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([week, b]) => ({
        week,
        calories: avg(b.calories),
        water: avg(b.water),
        protein: avg(b.protein),
        carb: avg(b.carb),
        fat: avg(b.fat),
        sleep: avg(b.sleep),
        consistency: b.total ? Math.round((b.consistent / b.total) * 100) : null,
      }))

    const calcDelta = (key: keyof typeof weekly[0]): number | null => {
      const pts = weekly.filter(w => w[key] != null)
      if (pts.length < 2) return null
      const first = pts[0][key] as number
      const last = pts[pts.length - 1][key] as number
      return Math.round(((last - first) / Math.max(1, pts.length - 1)) * 10) / 10
    }

    return {
      avgCalories: withCalories.length ? Math.round(withCalories.reduce((s, n) => s + (n.avg_daily_calories || 0), 0) / withCalories.length) : null,
      avgWater: withWater.length ? Math.round(withWater.reduce((s, n) => s + (n.water_intake || 0), 0) / withWater.length * 10) / 10 : null,
      avgProtein: withProtein.length ? Math.round(withProtein.reduce((s, n) => s + (n.avg_protein_g || 0), 0) / withProtein.length) : null,
      avgCarb: withCarb.length ? Math.round(withCarb.reduce((s, n) => s + (n.avg_carb_g || 0), 0) / withCarb.length) : null,
      avgFat: withFat.length ? Math.round(withFat.reduce((s, n) => s + (n.avg_fat_g || 0), 0) / withFat.length) : null,
      avgSleep: withSleep.length ? Math.round(withSleep.reduce((s, n) => s + (n.avg_sleep_hours || 0), 0) / withSleep.length * 10) / 10 : null,
      weekly,
      caloriesChangePerWeek: calcDelta('calories'),
      waterChangePerWeek: calcDelta('water'),
      proteinChangePerWeek: calcDelta('protein'),
      carbChangePerWeek: calcDelta('carb'),
      fatChangePerWeek: calcDelta('fat'),
      sleepChangePerWeek: calcDelta('sleep'),
      waterUnit: withWater[0]?.water_unit || 'litres',
      consistencyPct: inWindow.length ? Math.round((consistent / inWindow.length) * 100) : null,
      entries: inWindow.length,
    }
  }, [currentWeekStartDay, program, analysisWindowEndStr, analysisWindowStartStr])

  const bodyweightEntries = useMemo(
    () => mergeBodyweightEntries(weightLog, bodyweightSessions),
    [bodyweightSessions, weightLog],
  )

  const weightTrend = useMemo(
    () => buildBodyweightTrend(bodyweightEntries, analysisWindowStartStr, analysisWindowEndStr),
    [analysisWindowEndStr, analysisWindowStartStr, bodyweightEntries],
  )

  const banisterSeries = useMemo(() => {
    if (!banister) return []
    return banister.series.filter(point => point.date >= analysisWindowStartStr && point.date <= analysisWindowEndStr)
  }, [banister, analysisWindowEndStr, analysisWindowStartStr])

  const dotsTrend = useMemo(() => {
    if (!filteredSessions.length) return null
    type WeekData = {
      squat: number
      bench: number
      deadlift: number
      bw: number
      date: string | null
      hasSquat: boolean
      hasBench: boolean
      hasDeadlift: boolean
    }
    const byWeek = new Map<number, WeekData>()

    for (const s of filteredSessions) {
      const wn = s.week_number
      if (!wn) continue
      if (!byWeek.has(wn)) byWeek.set(wn, { squat: 0, bench: 0, deadlift: 0, bw: 0, date: null, hasSquat: false, hasBench: false, hasDeadlift: false })
      const w = byWeek.get(wn)!
      if (!w.date || s.date < w.date) w.date = s.date

      if (s.body_weight_kg && s.body_weight_kg > w.bw) w.bw = s.body_weight_kg

      for (const ex of s.exercises || []) {
        const name = ex.name.toLowerCase()
        const kg = ex.kg || 0
        const reps = ex.reps || 0
        if (executedSets(ex) <= 0) continue
        const rpe = (ex as { rpe?: number | null }).rpe ?? s.session_rpe
        const e1rm = estimateAnalysisE1rm(kg, reps, rpe)
        if (e1rm == null) continue
        if (name === 'squat' || (name.includes('squat') && !name.includes('hack') && !name.includes('split'))) {
          w.squat = Math.max(w.squat, e1rm)
          w.hasSquat = true
        } else if (name === 'bench press' || name === 'bench') {
          w.bench = Math.max(w.bench, e1rm)
          w.hasBench = true
        } else if (name === 'deadlift' || (name.includes('deadlift') && !name.includes('rdl') && !name.includes('romanian'))) {
          w.deadlift = Math.max(w.deadlift, e1rm)
          w.hasDeadlift = true
        }
      }
    }

    const rows: TrendRow[] = Array.from(byWeek.entries())
      .sort(([a], [b]) => a - b)
      .map(([wn, d]) => {
        let bw = d.bw
        if (!bw) bw = latestBodyweightOnOrBefore(bodyweightEntries, d.date ?? analysisWindowEndStr) ?? 0

        const total = (d.squat > 0 ? d.squat : 0) + (d.bench > 0 ? d.bench : 0) + (d.deadlift > 0 ? d.deadlift : 0)
        const dots = total > 0 && bw > 0 ? calculateDots(total, bw, sex) : null
        const hasFullSbd = d.hasSquat && d.hasBench && d.hasDeadlift
        const hasBenchOnly = d.hasBench && !d.hasSquat && !d.hasDeadlift
        const ipfGl = bw > 0 && hasFullSbd && total > 0
          ? calculateIpfGl(total, bw, sex, 'classic_powerlifting')
          : bw > 0 && hasBenchOnly && d.bench > 0
            ? calculateIpfGl(d.bench, bw, sex, 'classic_bench')
            : null
        const ipfGlMode: IpfGlMode | null = hasFullSbd && total > 0
          ? 'classic_powerlifting'
          : hasBenchOnly && d.bench > 0
            ? 'classic_bench'
            : null
        return {
          week: wn,
          squat: d.squat > 0 ? Math.round(d.squat * 10) / 10 : null,
          bench: d.bench > 0 ? Math.round(d.bench * 10) / 10 : null,
          deadlift: d.deadlift > 0 ? Math.round(d.deadlift * 10) / 10 : null,
          total: total > 0 ? Math.round(total * 10) / 10 : null,
          dots,
          ipfGl,
          ipfGlMode,
        }
      })
      .filter(r => r.squat || r.bench || r.deadlift)

    if (!rows.length) return null

    const withDots = rows.filter(r => r.dots !== null)
    let dotsChange: number | null = null
    if (withDots.length >= 2) {
      dotsChange = Math.round(((withDots[withDots.length - 1].dots! - withDots[0].dots!) / Math.max(1, withDots.length - 1)) * 100) / 100
    }

    return { rows, dotsChange }
  }, [analysisWindowEndStr, bodyweightEntries, filteredSessions, sex])

  const ipfGlTrend = useMemo(() => {
    if (!dotsTrend?.rows.length) return null
    const comparable = dotsTrend.rows.filter((r): r is TrendRow & { ipfGl: number; ipfGlMode: IpfGlMode } => r.ipfGl !== null && r.ipfGlMode !== null)
    if (comparable.length < 2) return null
    const modes = new Set(comparable.map(r => r.ipfGlMode))
    if (modes.size !== 1) return null
    const change = Math.round(((comparable[comparable.length - 1].ipfGl - comparable[0].ipfGl) / Math.max(1, comparable.length - 1)) * 100) / 100
    return { change, mode: comparable[0].ipfGlMode }
  }, [dotsTrend])

  const highestMaxes = useMemo(() => {
    if (!dotsTrend || !dotsTrend.rows.length) return null
    let squat = 0, bench = 0, deadlift = 0
    for (const r of dotsTrend.rows) {
      if (r.squat && r.squat > squat) squat = r.squat
      if (r.bench && r.bench > bench) bench = r.bench
      if (r.deadlift && r.deadlift > deadlift) deadlift = r.deadlift
    }
    if (!squat && !bench && !deadlift) return null
    
    const total = squat + bench + deadlift
    let bw = weightTrend?.latest || 0
    if (!bw && bodyweightEntries.length) bw = bodyweightEntries[bodyweightEntries.length - 1].kg
    const dots = total > 0 && bw > 0 ? calculateDots(total, bw, sex) : null

    return { squat: squat || null, bench: bench || null, deadlift: deadlift || null, total, dots }
    }, [bodyweightEntries, dotsTrend, weightTrend, sex])
  const sleepTrend = useMemo(() => {
    const weeks = nutritionTrend?.weekly.filter(w => w.sleep != null) || []
    if (!weeks.length) return null
    const avg = nutritionTrend!.avgSleep
    const delta = nutritionTrend!.sleepChangePerWeek
    return { avg, delta, weekly: weeks }
  }, [nutritionTrend])

  return (
    <Stack gap="lg">
      <Group justify="space-between" wrap="wrap">
        <Title order={2}>Analysis</Title>
        <SegmentedControl
          value={activeSection}
          onChange={(value) => updateAnalysisParams({ type: value as AnalysisSection })}
          data={[
            { value: 'weekly', label: 'Weekly' },
            { value: 'blocks', label: 'Past Blocks' },
            { value: 'compare', label: 'Lifetime Compare' },
          ]}
        />
      </Group>

      {activeSection === 'weekly' && (
        <>
      <Group justify="space-between" wrap="wrap">
        <Title order={2}>Weekly Analysis</Title>
        <Group gap="sm" wrap="wrap">
          <Select
            size="sm"
            value={String(weeksMode)}
            onChange={(val) => {
              if (!val) return
              updateAnalysisParams({ weeks: parseWeeksMode(val) })
            }}
            data={[
              { value: 'current', label: 'Current Week' },
              { value: '1', label: 'Previous Week' },
              { value: '2', label: 'Previous 2 Weeks' },
              { value: '4', label: 'Previous 4 Weeks' },
              { value: '8', label: 'Previous 8 Weeks' },
              { value: 'block', label: 'Full Block (W1 → now)' },
            ]}
            w={200}
          />
          <SegmentedControl
            size="xs"
            value={viewMode}
            onChange={(v) => updateAnalysisParams({ view: v as AnalysisViewMode })}
            data={[
              { value: 'raw', label: 'Table' },
              { value: 'graph', label: 'Charts' },
            ]}
          />
          <Button
            component="a"
            href="/api/export/xlsx"
            download="program_history.xlsx"
            size="sm"
            leftSection={<Download size={16} />}
          >
            Export Excel
          </Button>
          <Button
            component="a"
            href="/api/export/markdown"
            download="program_history.md"
            size="sm"
            variant="light"
            leftSection={<Download size={16} />}
          >
            Export Markdown
          </Button>
          <Button
            size="sm"
            variant="light"
            color="orange"
            leftSection={<RefreshCw size={16} />}
            loading={regenerating}
            onClick={handleRegenerateAnalysis}
            disabled={readOnly}
          >
            Regenerate Weekly Analysis
          </Button>
          {latestGeneratedAt && !regenerating && (
            <Badge color="gray" variant="light" size="sm">
              Generated {new Date(latestGeneratedAt).toLocaleDateString()}
            </Badge>
          )}
          {pendingSectionCount > 0 && (
            <Badge color="blue" variant="light" size="sm">
              {pendingSectionCount} updating
            </Badge>
          )}
        </Group>
      </Group>

      {loading && !data && <Center mih="20vh"><Loader /></Center>}

      {error && (
        <Paper withBorder p="md" style={{ borderColor: 'var(--mantine-color-red-4)' }}>
          <Text c="red">{error}</Text>
        </Paper>
      )}

      {data && (
        <>
          <AlertsStrip alerts={data.alerts || []} />

          {/* Top summary cards */}
          <SimpleGrid cols={{ base: 1, sm: 2, xl: 4 }} spacing="md">
            <Paper withBorder p="md">
              <Group gap="xs" mb="xs">
                <Dumbbell size={18} />
                <Text fw={500}>Estimated 1 Rep Maxes</Text>
              </Group>
              {highestMaxes ? (
                <Stack gap="xs">
                  <SimpleGrid cols={3}>
                    <Stack gap={2} ta="center">
                      <Text fz="xs" c="dimmed">Squat</Text>
                      <Text fz="lg" fw={700}>{highestMaxes.squat !== null ? toDisplayUnit(highestMaxes.squat, unit).toFixed(1) : '--'}</Text>
                    </Stack>
                    <Stack gap={2} ta="center">
                      <Text fz="xs" c="dimmed">Bench</Text>
                      <Text fz="lg" fw={700}>{highestMaxes.bench !== null ? toDisplayUnit(highestMaxes.bench, unit).toFixed(1) : '--'}</Text>
                    </Stack>
                    <Stack gap={2} ta="center">
                      <Text fz="xs" c="dimmed">Deadlift</Text>
                      <Text fz="lg" fw={700}>{highestMaxes.deadlift !== null ? toDisplayUnit(highestMaxes.deadlift, unit).toFixed(1) : '--'}</Text>
                    </Stack>
                  </SimpleGrid>
                  {highestMaxes.dots !== null && (
                    <Text fz="sm" c="dimmed">Est. DOTS: <Text span fw={500} c="var(--mantine-color-text)">{highestMaxes.dots.toFixed(2)}</Text></Text>
                  )}
                  <Text fz="xs" c="dimmed">
                    via session e1RM
                  </Text>
                </Stack>
              ) : data.current_maxes ? (
                <Stack gap="xs">
                  <SimpleGrid cols={3}>
                    <Stack gap={2} ta="center">
                      <Text fz="xs" c="dimmed">Squat</Text>
                      <Text fz="lg" fw={700}>{data.current_maxes.squat ? toDisplayUnit(data.current_maxes.squat, unit).toFixed(1) : '--'}</Text>
                    </Stack>
                    <Stack gap={2} ta="center">
                      <Text fz="xs" c="dimmed">Bench</Text>
                      <Text fz="lg" fw={700}>{data.current_maxes.bench ? toDisplayUnit(data.current_maxes.bench, unit).toFixed(1) : '--'}</Text>
                    </Stack>
                    <Stack gap={2} ta="center">
                      <Text fz="xs" c="dimmed">Deadlift</Text>
                      <Text fz="lg" fw={700}>{data.current_maxes.deadlift ? toDisplayUnit(data.current_maxes.deadlift, unit).toFixed(1) : '--'}</Text>
                    </Stack>
                  </SimpleGrid>
                  {data.estimated_dots !== null && (
                    <Text fz="sm" c="dimmed">Est. DOTS: <Text span fw={500} c="var(--mantine-color-text)">{data.estimated_dots.toFixed(2)}</Text></Text>
                  )}
                  {data.current_maxes.method && (
                    <Text fz="xs" c="dimmed">
                      via {data.current_maxes.method === 'comp_results' ? 'competition' : data.current_maxes.method === 'session_estimated' ? 'session data' : data.current_maxes.method}
                    </Text>
                  )}
                </Stack>
              ) : (
                <Text fz="sm" c="dimmed">No max data available</Text>
              )}
            </Paper>

            <Paper withBorder p="md">
              <Group gap="xs" mb="sm">
                <CheckCircle size={18} />
                <Text fw={500}>Compliance</Text>
              </Group>
              {data.compliance ? (
                <Stack gap="sm">
                  <SimpleGrid cols={3} spacing="xs">
                    <Stack gap={0} ta="center">
                      <Text fz="xs" c="dimmed">Sessions</Text>
                      <Text fz="xl" fw={700} c={complianceBadgeColor(data.compliance.pct)}>{data.compliance.pct.toFixed(0)}%</Text>
                      <Text fz="xs" c="dimmed">{data.compliance.completed}/{data.compliance.planned}</Text>
                    </Stack>
                    <Stack gap={0} ta="center">
                      <Text fz="xs" c="dimmed">Sets</Text>
                      <Text fz="xl" fw={700} c={complianceBadgeColor(data.compliance.set_pct ?? 0)}>{(data.compliance.set_pct ?? 0).toFixed(0)}%</Text>
                      <Text fz="xs" c="dimmed">{(data.compliance.completed_sets ?? 0)}/{(data.compliance.planned_sets ?? 0)}</Text>
                    </Stack>
                    <Stack gap={0} ta="center">
                      <Text fz="xs" c="dimmed">Volume</Text>
                      <Text fz="xl" fw={700} c={complianceBadgeColor(data.compliance.vol_pct ?? 0)}>{(data.compliance.vol_pct ?? 0).toFixed(0)}%</Text>
                      <Text fz="xs" c="dimmed" truncate>{Math.round(toDisplayUnit(data.compliance.completed_volume ?? 0, unit)).toLocaleString()} {unit}</Text>
                    </Stack>
                  </SimpleGrid>
                  <Box>
                    <Text fz="xs" c="dimmed" ta="center">{data.compliance.phase} block</Text>
                    {avgSessionsPerWeek !== null && <Text fz="xs" c="dimmed" ta="center">Avg {avgSessionsPerWeek} sessions/wk</Text>}
                  </Box>
                </Stack>
              ) : <Text fz="sm" c="dimmed">No compliance data</Text>}
            </Paper>

            <Paper withBorder p="md">
              <Group gap="xs" mb="xs">
                <Activity size={18} />
                <Text fw={500}>Current Fatigue State</Text>
              </Group>
              <Stack gap={2}>
                <Text fz="2rem" fw={700} c={fatigueBadgeColor(data.fatigue_index)}>
                  {data.fatigue_index !== null ? (data.fatigue_index * 100).toFixed(0) + '%' : 'N/A'}
                </Text>
                <Text fz="sm" c="dimmed">{fatigueLabel(data.fatigue_index)} current state</Text>
                <Group gap="xs" wrap="wrap">
                  {typeof data.fatigue_components?.window_mean_fi === 'number' && (
                    <Badge variant="light" color="blue">
                      Window mean {(data.fatigue_components.window_mean_fi * 100).toFixed(0)}%
                    </Badge>
                  )}
                  {typeof data.fatigue_components?.window_peak_fi === 'number' && (
                    <Badge variant="light" color="orange">
                      Window peak {(data.fatigue_components.window_peak_fi * 100).toFixed(0)}%
                    </Badge>
                  )}
                </Group>
                <Text fz="xs" c="dimmed" lh="lg">
                  Failures: {((data.fatigue_components?.failure_stress ?? 0) * 100).toFixed(0)}%
                  &middot; Spike: {((data.fatigue_components?.acute_spike_stress ?? 0) * 100).toFixed(0)}%
                  &middot; RPE: {((data.fatigue_components?.rpe_stress ?? 0) * 100).toFixed(0)}%
                  &middot; Reservoir: {((data.fatigue_components?.chronic_load_stress ?? 0) * 100).toFixed(0)}%
                  &middot; Streak: {((data.fatigue_components?.overload_streak ?? 0) * 100).toFixed(0)}%
                  &middot; Intensity: {((data.fatigue_components?.intensity_density_stress ?? 0) * 100).toFixed(0)}%
                  &middot; Strain: {((data.fatigue_components?.monotony_stress ?? 0) * 100).toFixed(0)}%
                </Text>
                {data.fatigue_components?.reservoir_dimension_stress && (
                  <Group gap={6} wrap="wrap" mt={4}>
                    {Object.entries(data.fatigue_components.reservoir_dimension_stress).map(([dim, value]) => (
                      <Badge key={dim} variant="light" color={value >= 0.75 ? 'red' : value >= 0.5 ? 'orange' : 'gray'} style={{ textTransform: 'capitalize' }}>
                        {dim} {(value * 100).toFixed(0)}%
                      </Badge>
                    ))}
                  </Group>
                )}
                {data.fatigue_components?.fatigue_context_confidence && (
                  <Text fz="xs" c="dimmed" mt="xs">
                    Context: {typeof data.fatigue_components.fatigue_context_days_used === 'number'
                      ? `${data.fatigue_components.fatigue_context_days_used}d`
                      : `${data.fatigue_components.fatigue_context_weeks_used ?? 0}w`} ({data.fatigue_components.fatigue_context_confidence} confidence)
                  </Text>
                )}
              </Stack>
            </Paper>

            <Paper withBorder p="md">
              <Group gap="xs" mb="xs" justify="space-between" align="flex-start">
                <Group gap="xs">
                  <Activity size={18} />
                  <Text fw={500}>Readiness</Text>
                </Group>
                {data.readiness_score && (
                  <Badge variant="light" color={data.readiness_score.zone} size="sm">
                    {readinessZoneLabel(data.readiness_score.zone)}
                  </Badge>
                )}
              </Group>
              {data.readiness_score ? (
                <Stack gap={2}>
                  <Text fz="2rem" fw={700}>{data.readiness_score.score.toFixed(0)}</Text>
                  <SimpleGrid cols={2} spacing="xs" mt={4}>
                    <Stack gap={0}>
                      <Text fz="xs" c="dimmed">Training</Text>
                      <Text fz="sm" fw={700}>{data.readiness_score.training_score?.toFixed(0) ?? '--'}</Text>
                    </Stack>
                    <Stack gap={0}>
                      <Text fz="xs" c="dimmed">External</Text>
                      <Text fz="sm" fw={700}>{data.readiness_score.external_score?.toFixed(0) ?? '--'}</Text>
                    </Stack>
                  </SimpleGrid>
                  <Text fz="xs" c="dimmed" lh="lg">
                    Fatigue: {((data.readiness_score.components.fatigue_norm ?? 0) * 100).toFixed(0)}%
                    &middot; RPE drift: {((data.readiness_score.components.rpe_drift ?? 0) * 100).toFixed(0)}%
                    &middot; Wellness: {((data.readiness_score.components.wellness ?? 0) * 100).toFixed(0)}%
                    &middot; Trend: {((data.readiness_score.components.performance_trend ?? 0) * 100).toFixed(0)}%
                    &middot; BW deviation: {((data.readiness_score.components.bw_deviation ?? 0) * 100).toFixed(0)}%
                  </Text>
                  <Text fz="xs" c="dimmed">
                    Confidence: overall {((data.readiness_score.readiness_confidence ?? 0) * 100).toFixed(0)}%
                    {' '}| training {((data.readiness_score.training_readiness_confidence ?? 0) * 100).toFixed(0)}%
                    {' '}| external {((data.readiness_score.external_readiness_confidence ?? 0) * 100).toFixed(0)}%
                  </Text>
                </Stack>
              ) : <Text fz="sm" c="dimmed">N/A</Text>}
            </Paper>
          </SimpleGrid>

          {/* Peaking Layer */}
          {(data.banister || data.decoupling || taperQuality) && (
            <Stack gap="md">
              <Paper withBorder p="md">
                <Group gap="xs" mb="sm" justify="space-between" align="flex-start">
                  <Group gap="xs">
                    <TrendingUp size={18} />
                    <Text fw={500}>Form / Peaking Readiness</Text>
                  </Group>
                  {banister && (
                    <Badge variant="light" color={banisterBadgeColor(banister.tsb_today)} size="sm">
                      {banister.tsb_label}
                    </Badge>
                  )}
                </Group>

                {banister ? (
                  <Stack gap="md">
                    <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="sm">
                      <Stack gap={2} ta="center" p="sm" style={{ borderRadius: 'var(--mantine-radius-sm)', background: 'var(--mantine-color-orange-light)' }}>
                        <InfoLabel label="CTL / Fitness" help="Chronic training load. A longer-horizon fitness signal built from your recent workload history." />
                        <Text fz="xl" fw={700} c="var(--mantine-color-text)">{banister.ctl_today.toFixed(1)}</Text>
                      </Stack>
                      <Stack gap={2} ta="center" p="sm" style={{ borderRadius: 'var(--mantine-radius-sm)', background: 'var(--mantine-color-red-light)' }}>
                        <InfoLabel label="ATL / Fatigue" help="Acute training load. A shorter-horizon fatigue signal that reacts faster to recent hard training." />
                        <Text fz="xl" fw={700} c="var(--mantine-color-text)">{banister.atl_today.toFixed(1)}</Text>
                      </Stack>
                      <Stack gap={2} ta="center" p="sm" style={{ borderRadius: 'var(--mantine-radius-sm)', background: 'var(--mantine-color-blue-light)' }}>
                        <InfoLabel label="TSB / Form" help="Training stress balance. CTL minus ATL. Higher values usually mean fresher; very negative values usually mean accumulated fatigue." />
                        <Text fz="xl" fw={700} c={banisterBadgeColor(banister.tsb_today)}>{banister.tsb_today.toFixed(1)}</Text>
                      </Stack>
                    </SimpleGrid>

                    {banisterSeries.length > 0 ? (
                      <>
                        <Box style={{ width: '100%', height: 320 }}>
                          <ResponsiveContainer width="100%" height="100%">
                            <LineChart data={banisterSeries}>
                              <CartesianGrid
                                strokeDasharray="3 3"
                                vertical={false}
                                stroke="var(--mantine-color-default-border)"
                              />
                              <XAxis
                                dataKey="date"
                                tickFormatter={(value) => String(value).slice(5)}
                                minTickGap={18}
                                tick={{ fill: 'var(--mantine-color-dimmed)' }}
                                axisLine={{ stroke: 'var(--mantine-color-default-border)' }}
                                tickLine={{ stroke: 'var(--mantine-color-default-border)' }}
                              />
                              <YAxis
                                tick={{ fill: 'var(--mantine-color-dimmed)' }}
                                axisLine={{ stroke: 'var(--mantine-color-default-border)' }}
                                tickLine={{ stroke: 'var(--mantine-color-default-border)' }}
                              />
                              <RechartsTooltip
                                labelFormatter={(label) => `Date: ${String(label)}`}
                                contentStyle={{
                                  backgroundColor: 'var(--mantine-color-body)',
                                  border: '1px solid var(--mantine-color-default-border)',
                                  color: 'var(--mantine-color-text)',
                                }}
                                labelStyle={{ color: 'var(--mantine-color-text)' }}
                                itemStyle={{ color: 'var(--mantine-color-text)' }}
                              />
                              <Legend />
                              <Line type="monotone" dataKey="ctl" name="CTL" stroke="#f59e0b" strokeWidth={2} dot={false} />
                              <Line type="monotone" dataKey="atl" name="ATL" stroke="#ef4444" strokeWidth={2} dot={false} />
                              <Line type="monotone" dataKey="tsb" name="TSB" stroke="#3b82f6" strokeWidth={2} dot={false} />
                              {upcomingCompetition && (
                                <ReferenceLine
                                  x={upcomingCompetition.date}
                                  stroke="var(--mantine-color-dimmed)"
                                  strokeDasharray="4 4"
                                  label={{ value: 'Comp', position: 'insideTopRight' }}
                                />
                              )}
                            </LineChart>
                          </ResponsiveContainer>
                        </Box>
                        {upcomingCompetition && (
                          <Text fz="xs" c="dimmed">
                            Competition marker: {upcomingCompetition.name} on {upcomingCompetition.date}
                          </Text>
                        )}
                      </>
                    ) : (
                      <Text fz="sm" c="dimmed">No Banister datapoints fall inside the selected window.</Text>
                    )}
                  </Stack>
                ) : (
                  <Text fz="sm" c="dimmed">
                    {isInsufficientData(data.banister) ? data.banister.reason : 'No Banister data available.'}
                  </Text>
              )}
            </Paper>

            {peakingTimeline && (
              <PeakingTimeline data={peakingTimeline} />
            )}

              <SimpleGrid cols={{ base: 1, lg: taperQuality ? 2 : 1 }} spacing="md">
                <Paper withBorder p="md">
                  <Group gap="xs" mb="sm" justify="space-between" align="flex-start">
                    <Group gap="xs">
                      <Dumbbell size={18} />
                      <Text fw={500}>Strength-Fatigue Decoupling</Text>
                    </Group>
                    {decoupling && decoupling.current && (
                      <Badge variant="light" color={decouplingBadgeColor(decoupling.current.decoupling)} size="sm">
                        {decoupling.current.decoupling >= 0 ? 'Positive' : 'Negative'}
                      </Badge>
                    )}
                  </Group>

                  {decoupling ? (
                    <Stack gap="sm">
                      {decoupling.current ? (
                        <>
                          <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="sm">
                            <Stack gap={2} ta="center" p="sm" style={{ borderRadius: 'var(--mantine-radius-sm)', background: 'var(--mantine-color-default-hover)' }}>
                              <Text fz="xs" c="dimmed">Decoupling</Text>
                              <Text fz="xl" fw={700} c={decouplingBadgeColor(decoupling.current.decoupling)}>
                                {decoupling.current.decoupling.toFixed(2)}
                              </Text>
                            </Stack>
                            <Stack gap={2} ta="center" p="sm" style={{ borderRadius: 'var(--mantine-radius-sm)', background: 'var(--mantine-color-default-hover)' }}>
                              <Text fz="xs" c="dimmed">e1RM slope</Text>
                              <Text fz="xl" fw={700} c={decoupling.current.e1rm_slope_pct_per_week >= 0 ? 'green' : 'red'}>
                                {decoupling.current.e1rm_slope_pct_per_week >= 0 ? '+' : ''}{decoupling.current.e1rm_slope_pct_per_week.toFixed(2)}%/wk
                              </Text>
                            </Stack>
                            <Stack gap={2} ta="center" p="sm" style={{ borderRadius: 'var(--mantine-radius-sm)', background: 'var(--mantine-color-default-hover)' }}>
                              <Text fz="xs" c="dimmed">Fatigue slope</Text>
                              <Text fz="xl" fw={700} c={decoupling.current.fi_slope_pct_points_per_week <= 0 ? 'green' : 'red'}>
                                {decoupling.current.fi_slope_pct_points_per_week >= 0 ? '+' : ''}{decoupling.current.fi_slope_pct_points_per_week.toFixed(2)} pp/wk
                              </Text>
                            </Stack>
                          </SimpleGrid>
                          {decoupling.flags.length > 0 && (
                            <Group gap="xs" wrap="wrap">
                              {decoupling.flags.map(flag => (
                                <Badge key={flag} color="yellow" variant="light">{flag}</Badge>
                              ))}
                            </Group>
                          )}
                          {decoupling.series.length > 0 && (
                            <Box style={{ overflowX: 'auto' }}>
                              <Table fz="sm">
                                <Table.Thead>
                                  <Table.Tr>
                                    <Table.Th>Week Start</Table.Th>
                                    <Table.Th ta="right">Decoupling</Table.Th>
                                  </Table.Tr>
                                </Table.Thead>
                                <Table.Tbody>
                                  {decoupling.series.slice(-4).map(point => (
                                    <Table.Tr key={point.week_start}>
                                      <Table.Td fw={500}>{point.week_start}</Table.Td>
                                      <Table.Td ta="right" c={decouplingBadgeColor(point.decoupling)}>
                                        {point.decoupling >= 0 ? '+' : ''}{point.decoupling.toFixed(2)}
                                      </Table.Td>
                                    </Table.Tr>
                                  ))}
                                </Table.Tbody>
                              </Table>
                            </Box>
                          )}
                        </>
                      ) : (
                        <Text fz="sm" c="dimmed">No decoupling window available yet.</Text>
                      )}
                    </Stack>
                  ) : (
                    <Text fz="sm" c="dimmed">
                      {isInsufficientData(data.decoupling) ? data.decoupling.reason : 'No decoupling data available.'}
                    </Text>
                  )}
                </Paper>

                {taperQuality && (
                  <Paper withBorder p="md">
                    <Group gap="xs" mb="sm" justify="space-between" align="flex-start">
                      <Group gap="xs">
                        <Trophy size={18} />
                        <Text fw={500}>Taper Quality Score</Text>
                      </Group>
                      <Badge variant="light" color={taperQualityBadgeColor(taperQuality.label)} size="sm">
                        {taperQuality.label}
                      </Badge>
                    </Group>

                    <Stack gap="sm">
                      <Group align="baseline" gap="sm">
                        <Text fz="2rem" fw={700}>{taperQuality.score.toFixed(0)}</Text>
                        <Text fz="sm" c="dimmed">/ 100</Text>
                      </Group>
                      <Text fz="xs" c="dimmed">Weeks to comp: {taperQuality.weeks_to_comp.toFixed(1)}</Text>
                      <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="sm">
                        <Stack gap={2} ta="center" p="xs" style={{ borderRadius: 'var(--mantine-radius-sm)', background: 'var(--mantine-color-default-hover)' }}>
                          <Text fz="xs" c="dimmed">Volume</Text>
                          <Text fz="lg" fw={700}>{(taperQuality.components.volume_reduction * 100).toFixed(0)}%</Text>
                        </Stack>
                        <Stack gap={2} ta="center" p="xs" style={{ borderRadius: 'var(--mantine-radius-sm)', background: 'var(--mantine-color-default-hover)' }}>
                          <Text fz="xs" c="dimmed">Intensity</Text>
                          <Text fz="lg" fw={700}>{(taperQuality.components.intensity_maintained * 100).toFixed(0)}%</Text>
                        </Stack>
                        <Stack gap={2} ta="center" p="xs" style={{ borderRadius: 'var(--mantine-radius-sm)', background: 'var(--mantine-color-default-hover)' }}>
                          <Text fz="xs" c="dimmed">Fatigue Trend</Text>
                          <Text fz="lg" fw={700}>{(taperQuality.components.fatigue_trend * 100).toFixed(0)}%</Text>
                        </Stack>
                        <Stack gap={2} ta="center" p="xs" style={{ borderRadius: 'var(--mantine-radius-sm)', background: 'var(--mantine-color-default-hover)' }}>
                          <Text fz="xs" c="dimmed">TSB</Text>
                          <Text fz="lg" fw={700}>{(taperQuality.components.tsb * 100).toFixed(0)}%</Text>
                        </Stack>
                      </SimpleGrid>
                    </Stack>
                  </Paper>
                )}
              </SimpleGrid>
            </Stack>
          )}

          {/* INOL */}
          {data.inol && data.inol.avg_inol && (
            <Paper withBorder p="md">
              <Group gap="xs" mb="sm">
                <Text fw={500}>Stimulus-Adjusted INOL (Window Average)</Text>
                <Tooltip label="INOL means intensity-number-of-lifts. Here it is adjusted by your lift-profile stimulus coefficient to reflect how hard the same workload is for you." withArrow multiline w={320}>
                  <Info size={14} style={{ cursor: 'help', color: 'var(--mantine-color-gray-6)' }} />
                </Tooltip>
              </Group>
              <SimpleGrid cols={3} mb="sm">
                {Object.entries(data.inol.avg_inol).map(([lift, val]) => {
                  const coefficient = data.inol?.stimulus_coefficients?.[lift] ?? 1
                  const baseThresholds = getInolThresholds(lift, data.inol?.thresholds)
                  const adjusted = data.inol?.phase_adjusted_thresholds?.[lift]
                  const displayThresholds = adjusted
                    ? { low: adjusted.display_low, high: adjusted.display_high }
                    : baseThresholds
                  const zoneMeta = getInolZoneMeta(val, displayThresholds)
                  const raw = data.inol?.raw_avg_inol?.[lift]
                  const trend = data.inol?.trend_pressure?.[lift]
                  const rampGrace = data.inol?.ramp_up_grace?.[lift]
                  return (
                    <Stack key={lift} gap={2} ta="center" p="sm" style={{ borderRadius: 'var(--mantine-radius-sm)', background: `var(--mantine-color-${zoneMeta.color}-light)` }}>
                      <Text fz="xs" c="dimmed" tt="capitalize">{lift}</Text>
                      <Text fz="xl" fw={700} c={zoneMeta.color}>{val.toFixed(2)}</Text>
                      {typeof raw === 'number' && <Text fz="xs" c="dimmed">Raw {raw.toFixed(2)}</Text>}
                      <Text fz="xs" c="dimmed">Stimulus x{coefficient.toFixed(2)}</Text>
                      <Text fz="xs" c="dimmed">{zoneMeta.label}</Text>
                      <Text fz="xs" c="dimmed" visibleFrom="sm">
                        Target {(adjusted?.low ?? baseThresholds.low).toFixed(1)} - {(adjusted?.high ?? baseThresholds.high).toFixed(1)}
                      </Text>
                      <Text fz="xs" c="dimmed" visibleFrom="sm">
                        Display {displayThresholds.low.toFixed(1)} - {displayThresholds.high.toFixed(1)}
                      </Text>
                      {trend && (
                        <Text fz="xs" c="dimmed" visibleFrom="sm">
                          Trend {(trend.value * 100).toFixed(0)}%
                        </Text>
                      )}
                      {rampGrace && <Badge color="blue" variant="light" size="xs">Ramp-up grace</Badge>}
                    </Stack>
                  )
                })}
              </SimpleGrid>
              {data.inol.flags.length > 0 && (
                <Group gap="xs" wrap="wrap">
                  {data.inol.flags.map(flag => (
                    <Badge key={flag} color="yellow" variant="light">{flag}</Badge>
                  ))}
                </Group>
              )}
            </Paper>
          )}

          {volumeLandmarkEntries.length > 0 && (
            <Paper withBorder p="md">
              <Group gap="xs" mb="sm" justify="space-between" align="flex-start">
                <Group gap="xs">
                  <Dumbbell size={18} />
                  <Text fw={500}>Volume Landmarks</Text>
                </Group>
                <Text fz="xs" c="dimmed">MEV / MAV / MRV from whole-program history</Text>
              </Group>
              <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="md">
                {volumeLandmarkEntries.map(([lift, landmark]) => (
                  <Stack
                    key={lift}
                    gap="xs"
                    p="sm"
                    style={{ borderRadius: 'var(--mantine-radius-sm)', background: 'var(--mantine-color-default-hover)' }}
                  >
                    <Group justify="space-between" align="center">
                      <Text fw={500} tt="capitalize">{lift}</Text>
                      <Badge variant="light" color={volumeConfidenceColor(landmark.confidence)}>
                        {landmark.confidence}
                      </Badge>
                    </Group>
                    <Group justify="space-between">
                      <Text fz="xs" c="dimmed">MV</Text>
                      <Text fz="sm" fw={700}>{landmark.mv !== null ? `${landmark.mv.toFixed(1)} sets` : '--'}</Text>
                    </Group>
                    <Group justify="space-between">
                      <Text fz="xs" c="dimmed">MEV</Text>
                      <Text fz="sm" fw={700}>{landmark.mev !== null ? `${landmark.mev.toFixed(1)} sets` : '--'}</Text>
                    </Group>
                    <Group justify="space-between">
                      <Text fz="xs" c="dimmed">MAV</Text>
                      <Text fz="sm" fw={700}>{landmark.mav !== null ? `${landmark.mav.toFixed(1)} sets` : '--'}</Text>
                    </Group>
                    <Group justify="space-between">
                      <Text fz="xs" c="dimmed">MRV</Text>
                      <Text fz="sm" fw={700}>{landmark.mrv !== null ? `${landmark.mrv.toFixed(1)} sets` : '--'}</Text>
                    </Group>
                  </Stack>
                ))}
              </SimpleGrid>
            </Paper>
          )}

          {/* ACWR */}
          {data.acwr && !('status' in data.acwr) && (
            <Paper withBorder p="md">
              <Group justify="space-between" mb="sm">
                <Group gap="xs">
                  <Text fw={500}>EWMA ACWR (daily workload ratio)</Text>
                  <Tooltip label="EWMA ACWR means exponentially weighted moving average acute:chronic workload ratio. It compares short-term load to longer-term load while weighting recent work more heavily." withArrow multiline w={340}>
                    <Info size={14} style={{ cursor: 'help', color: 'var(--mantine-color-gray-6)' }} />
                  </Tooltip>
                </Group>
                <Badge
                  color={getAcwrZoneMeta((data.acwr as any).composite_zone).color}
                  variant="light"
                >
                  Composite: {(data.acwr as any).composite?.toFixed(2) ?? 'N/A'}
                  <Text span visibleFrom="sm"> ({(data.acwr as any).composite_label ?? getAcwrZoneMeta((data.acwr as any).composite_zone).label})</Text>
                </Badge>
              </Group>
              <Text fz="xs" c="dimmed" mb="sm">
                Daily EWMA acute/chronic ratio. The labels describe workload pattern, not validated injury risk.
              </Text>
              <SimpleGrid cols={4} spacing="md">
                {Object.entries((data.acwr as any).dimensions).map(([dim, info]: [string, any]) => {
                  const zoneMeta = getAcwrZoneMeta(info.zone)
                  return (
                    <Stack key={dim} gap={2} ta="center" p="sm" style={{ borderRadius: 'var(--mantine-radius-sm)', background: `var(--mantine-color-${zoneMeta.color}-light)` }}>
                      <Text fz="xs" tt="capitalize">{dim}</Text>
                      <Text fz="xl" fw={700}>{info.value?.toFixed(2) ?? '--'}</Text>
                      <Text fz="xs" visibleFrom="sm">{info.label ?? zoneMeta.label}</Text>
                    </Stack>
                  )
                })}
              </SimpleGrid>
            </Paper>
          )}
          {data.acwr && 'status' in data.acwr && (
            <Paper withBorder p="md">
              <Group gap="xs" mb="xs">
                <Text fw={500}>EWMA ACWR (daily workload ratio)</Text>
                <Tooltip label="EWMA ACWR means exponentially weighted moving average acute:chronic workload ratio. It compares short-term load to longer-term load while weighting recent work more heavily." withArrow multiline w={340}>
                  <Info size={14} style={{ cursor: 'help', color: 'var(--mantine-color-gray-6)' }} />
                </Tooltip>
              </Group>
              <Text fz="sm" c="dimmed">{(data.acwr as any).reason ?? 'Not enough data yet. Keep logging sessions.'}</Text>
            </Paper>
          )}

          {/* RI Distribution */}
          {data.ri_distribution && (
            <Paper withBorder p="md">
              <Text fw={500} mb="sm">Relative Intensity Distribution</Text>
              <SimpleGrid cols={3} mb="md">
                {(['heavy', 'moderate', 'light'] as const).map(bucket => {
                  const info = data.ri_distribution!.overall[bucket]
                  const color = bucket === 'heavy' ? 'red' : bucket === 'moderate' ? 'green' : 'blue'
                  return (
                    <Stack key={bucket} gap={2} ta="center" p="sm" style={{ borderRadius: 'var(--mantine-radius-sm)', background: `var(--mantine-color-${color}-light)` }}>
                      <Text fz="xs" tt="capitalize">{bucket}</Text>
                      <Text fz="xl" fw={700}>{info.pct.toFixed(0)}%</Text>
                      <Text fz="xs">{info.count} sets</Text>
                    </Stack>
                  )
                })}
              </SimpleGrid>
              {Object.keys(data.ri_distribution.per_lift).length > 0 && (
                <Box style={{ overflowX: 'auto' }}>
                  <Table fz="sm">
                    <Table.Thead><Table.Tr><Table.Th>Lift</Table.Th><Table.Th ta="right">Heavy %</Table.Th><Table.Th ta="right">Moderate %</Table.Th><Table.Th ta="right">Light %</Table.Th></Table.Tr></Table.Thead>
                    <Table.Tbody>
                      {Object.entries(data.ri_distribution.per_lift).map(([lift, buckets]) => (
                        <Table.Tr key={lift}>
                          <Table.Td fw={500}>{lift}</Table.Td>
                          <Table.Td ta="right" c="red">{buckets.heavy.pct.toFixed(0)}%</Table.Td>
                          <Table.Td ta="right" c="green">{buckets.moderate.pct.toFixed(0)}%</Table.Td>
                          <Table.Td ta="right" c="blue">{buckets.light.pct.toFixed(0)}%</Table.Td>
                        </Table.Tr>
                      ))}
                    </Table.Tbody>
                  </Table>
                </Box>
              )}
            </Paper>
          )}

          {/* Specificity Ratio */}
          {data.specificity_ratio && (
            <Paper withBorder p="md">
              <Group justify="space-between" align="flex-start" mb="sm">
                <Group gap="xs">
                  <Text fw={500}>Specificity Ratio</Text>
                  <Tooltip label="Specificity ratio shows how much of your work is directly specific to competition. Narrow counts only SBD sets. Broad counts SBD plus closely related secondary work." withArrow multiline w={320}>
                    <Info size={14} style={{ cursor: 'help', color: 'var(--mantine-color-gray-6)' }} />
                  </Tooltip>
                </Group>
                {data.specificity_ratio.expected_band ? (
                  <Group gap="xs" wrap="wrap" justify="flex-end">
                    <Badge
                      variant="light"
                      color={specificityStatusBadgeColor(data.specificity_ratio.narrow_status)}
                    >
                      Narrow {specificityStatusLabel(data.specificity_ratio.narrow_status)}
                    </Badge>
                    <Badge
                      variant="light"
                      color={specificityStatusBadgeColor(data.specificity_ratio.broad_status)}
                    >
                      Broad {specificityStatusLabel(data.specificity_ratio.broad_status)}
                    </Badge>
                  </Group>
                ) : (
                  <Badge variant="light" color="gray">No upcoming comp band</Badge>
                )}
              </Group>
              {data.specificity_target_competition && (
                <Text fz="xs" c="dimmed" mb="sm">
                  Specificity target: {data.specificity_target_competition.name ?? 'Upcoming meet'}
                  {data.specificity_target_competition.date ? ` (${data.specificity_target_competition.date})` : ''}
                  {data.specificity_target_competition.selection_reason ? ` • ${String(data.specificity_target_competition.selection_reason).replace(/_/g, ' ')}` : ''}
                </Text>
              )}
              <SimpleGrid cols={2} spacing="md">
                <Stack gap="xs">
                  <Text fz="xs" c="dimmed">Narrow (SBD only)</Text>
                  <Progress value={Math.min(data.specificity_ratio.narrow * 100, 100)} />
                  <Text fz="sm" fw={500}>{(data.specificity_ratio.narrow * 100).toFixed(1)}%</Text>
                </Stack>
                <Stack gap="xs">
                  <Text fz="xs" c="dimmed">Broad (SBD + secondary)</Text>
                  <Progress value={Math.min(data.specificity_ratio.broad * 100, 100)} color="blue" />
                  <Text fz="sm" fw={500}>{(data.specificity_ratio.broad * 100).toFixed(1)}%</Text>
                </Stack>
              </SimpleGrid>
              {data.specificity_ratio.expected_band && (
                <Text fz="xs" c="dimmed" mt="sm">
                  Expected band at {data.specificity_ratio.expected_band.weeks_to_comp?.toFixed(1) ?? '--'} weeks out:
                  {' '}
                  narrow {data.specificity_ratio.expected_band.narrow.min.toFixed(2)} - {data.specificity_ratio.expected_band.narrow.max.toFixed(2)}
                  {' '}| broad {data.specificity_ratio.expected_band.broad.min.toFixed(2)} - {data.specificity_ratio.expected_band.broad.max.toFixed(2)}
                </Text>
              )}
              <Text fz="xs" c="dimmed" mt="sm">{data.specificity_ratio.sbd_sets} SBD sets / {data.specificity_ratio.total_sets} total sets</Text>
              {data.specificity_ratio.flags && data.specificity_ratio.flags.length > 0 && (
                <Group gap="xs" wrap="wrap" mt="sm">
                  {data.specificity_ratio.flags.map(flag => (
                    <Badge key={flag} color="yellow" variant="light">{flag}</Badge>
                  ))}
                </Group>
              )}
            </Paper>
          )}

          {/* Fatigue Dimensions */}
          {data.fatigue_dimensions && Object.keys(data.fatigue_dimensions.weekly).length > 0 && (
            <Paper withBorder p="md">
              <Text fw={500} mb="sm">Fatigue Dimensions (Weekly)</Text>
              <Box visibleFrom="sm" style={{ overflowX: 'auto' }}>
                <Table fz="sm">
                  <Table.Thead><Table.Tr><Table.Th>Week</Table.Th><Table.Th ta="right">Axial</Table.Th><Table.Th ta="right">Neural</Table.Th><Table.Th ta="right">Peripheral</Table.Th><Table.Th ta="right">Systemic</Table.Th></Table.Tr></Table.Thead>
                  <Table.Tbody>
                    {Object.entries(data.fatigue_dimensions.weekly)
                      .sort(([a], [b]) => Number(a) - Number(b)).slice(-8)
                      .map(([week, dims]) => (
                        <Table.Tr key={week}>
                          <Table.Td fw={500}>W{week}</Table.Td>
                          <Table.Td ta="right">{dims.axial.toFixed(1)}</Table.Td>
                          <Table.Td ta="right">{dims.neural.toFixed(1)}</Table.Td>
                          <Table.Td ta="right">{dims.peripheral.toFixed(1)}</Table.Td>
                          <Table.Td ta="right">{dims.systemic.toFixed(1)}</Table.Td>
                        </Table.Tr>
                      ))}
                  </Table.Tbody>
                </Table>
              </Box>
              <Stack hiddenFrom="sm" gap="xs">
                {Object.entries(data.fatigue_dimensions.weekly)
                  .sort(([a], [b]) => Number(a) - Number(b)).slice(-8)
                  .map(([week, dims]) => (
                    <Paper key={week} p="sm" bg="var(--mantine-color-default-hover)" radius="sm">
                      <Text fw={700} mb={4}>Week {week}</Text>
                      <SimpleGrid cols={4} spacing="xs">
                        <Stack gap={0} ta="center">
                          <Text fz="xs" c="dimmed">Axial</Text>
                          <Text fz="sm" fw={500}>{dims.axial.toFixed(1)}</Text>
                        </Stack>
                        <Stack gap={0} ta="center">
                          <Text fz="xs" c="dimmed">Neural</Text>
                          <Text fz="sm" fw={500}>{dims.neural.toFixed(1)}</Text>
                        </Stack>
                        <Stack gap={0} ta="center">
                          <Text fz="xs" c="dimmed">Periph</Text>
                          <Text fz="sm" fw={500}>{dims.peripheral.toFixed(1)}</Text>
                        </Stack>
                        <Stack gap={0} ta="center">
                          <Text fz="xs" c="dimmed">Systemic</Text>
                          <Text fz="sm" fw={500}>{dims.systemic.toFixed(1)}</Text>
                        </Stack>
                      </SimpleGrid>
                    </Paper>
                  ))}
              </Stack>
            </Paper>
          )}

          {/* Projections */}
          {data.projections.filter(p => p && typeof p === 'object').length > 0 ? (
            <Stack gap="sm">
              <Group justify="space-between" align="center">
                <Group gap="xs">
                  <TrendingUp size={18} />
                  <Text fw={500}>Projections</Text>
                </Group>
                {projectionCalibration?.calibrated && (
                  <Badge variant="light" color="teal">
                    Calibrated from {projectionCalibration.meets} meet{projectionCalibration.meets === 1 ? '' : 's'}
                  </Badge>
                )}
              </Group>
              <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="md">
                {data.projections.filter(p => p && typeof p === 'object').map((proj, i) => (
                  <Paper key={i} withBorder p="md">
                    <Group gap="xs" mb="xs">
                      <TrendingUp size={18} />
                      <Text fw={500}>{proj.comp_name || 'Projected Total'}</Text>
                    </Group>
                    <Text fz="2rem" fw={700}>{toDisplayUnit(proj.total || 0, unit).toFixed(1)} {unit}</Text>
                    <Text fz="sm" c="dimmed" mt="xs">
                      Confidence: {((proj.confidence || 0) * 100).toFixed(0)}%
                      {typeof proj.weeks_to_comp === 'number' && ` (${proj.weeks_to_comp.toFixed(1)} wks out)`}
                    </Text>
                    {proj.method && <Text fz="xs" c="dimmed">via {proj.method === 'session_estimated' ? 'session e1RM' : proj.method}</Text>}
                  </Paper>
                ))}
              </SimpleGrid>
            </Stack>
          ) : (
            <Paper withBorder p="md">
              <Group gap="xs" mb="xs">
                <TrendingUp size={18} />
                <Text fw={500}>Projected Total</Text>
              </Group>
              <Text fz="lg" c="dimmed">{data.projection_reason || 'No competition date set'}</Text>
            </Paper>
          )}

          {/* DOTS & e1RM Trend */}
          {dotsTrend && dotsTrend.rows.length >= 2 && (
            <Paper withBorder p="md">
              <Group gap="xs" mb="sm">
                <TrendingUp size={18} />
                <Text fw={500}>e1RM Progression &amp; DOTS Trend</Text>
                {dotsTrend.dotsChange !== null && (
                  <Badge color={dotsTrend.dotsChange >= 0 ? 'green' : 'red'} variant="light" ml="auto">
                    {dotsTrend.dotsChange >= 0 ? '+' : ''}{dotsTrend.dotsChange} DOTS/wk
                  </Badge>
                )}
                {ipfGlTrend && (
                  <Badge color={ipfGlTrend.change >= 0 ? 'green' : 'red'} variant="light" ml="xs">
                    {ipfGlTrend.change >= 0 ? '+' : ''}{ipfGlTrend.change} {getIpfGlModeLabel(ipfGlTrend.mode)} GL/wk
                  </Badge>
                )}
              </Group>
              <Box style={{ overflowX: 'auto' }}>
                <Table fz="sm">
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>W</Table.Th>
                      <Table.Th ta="right">Squat</Table.Th>
                      <Table.Th ta="right">Bench</Table.Th>
                      <Table.Th ta="right">Deadlift</Table.Th>
                      <Table.Th ta="right" visibleFrom="sm">Total</Table.Th>
                      <Table.Th ta="right">DOTS</Table.Th>
                      <Table.Th ta="right" visibleFrom="sm">IPF GL</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {dotsTrend.rows.map(r => (
                      <Table.Tr key={r.week}>
                        <Table.Td fw={500}>W{r.week}</Table.Td>
                        <Table.Td ta="right">{r.squat !== null ? toDisplayUnit(r.squat, unit).toFixed(1) : '--'}</Table.Td>
                        <Table.Td ta="right">{r.bench !== null ? toDisplayUnit(r.bench, unit).toFixed(1) : '--'}</Table.Td>
                        <Table.Td ta="right">{r.deadlift !== null ? toDisplayUnit(r.deadlift, unit).toFixed(1) : '--'}</Table.Td>
                        <Table.Td ta="right" fw={500} visibleFrom="sm">{r.total !== null ? toDisplayUnit(r.total, unit).toFixed(1) : '--'}</Table.Td>
                        <Table.Td ta="right" fw={700} c="blue">{r.dots?.toFixed(2) ?? '--'}</Table.Td>
                        <Table.Td ta="right" visibleFrom="sm">
                          {r.ipfGl !== null && r.ipfGlMode !== null ? (
                            <Stack gap={0} align="flex-end">
                              <Text span fw={700} fz="sm">{r.ipfGl.toFixed(2)}</Text>
                              <Text span fz="xs" c="dimmed">{getIpfGlModeLabel(r.ipfGlMode)}</Text>
                            </Stack>
                          ) : (
                            <Text span fz="sm" c="dimmed">--</Text>
                          )}
                        </Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </Box>
              <Text fz="xs" c="dimmed" mt="xs">
                DOTS uses table-based session e1RM and nearest bodyweight. IPF GL uses Classic Powerlifting for full SBD weeks and Classic Bench for bench-only weeks.
              </Text>
            </Paper>
          )}

          {/* Body Weight Trend */}
          {weightTrend && (
            <Paper withBorder p="md">
              <Group gap="xs" mb="sm">
                <Scale size={18} />
                <Text fw={500}>Body Weight Trend</Text>
              </Group>
              <Group align="baseline" gap="md">
                <Text fz="2rem" fw={700}>{toDisplayUnit(weightTrend.latest, unit).toFixed(1)} {unit}</Text>
                <Text fz="sm" fw={500} c={weightTrend.change >= 0 ? 'yellow' : 'green'}>
                  {weightTrend.change >= 0 ? '+' : ''}{toDisplayUnit(Math.abs(weightTrend.change), unit).toFixed(1)} {unit} over {effectiveWeeks} wk{effectiveWeeks !== 1 ? 's' : ''}
                </Text>
              </Group>
              <SimpleGrid cols={{ base: 4, md: 8 }} mt="sm">
                {weightTrend.entries.map(e => (
                  <Stack key={e.date} gap={2} ta="center">
                    <Text fz="xs" c="dimmed">{e.date.slice(5)}</Text>
                    <Text fz="sm" fw={500}>{toDisplayUnit(e.kg, unit).toFixed(1)}</Text>
                  </Stack>
                ))}
              </SimpleGrid>
            </Paper>
          )}

          {/* Sleep Trend */}
          {sleepTrend && (
            <Paper withBorder p="md">
              <Group gap="xs" mb="sm">
                <Moon size={18} />
                <Text fw={500}>Sleep Trend</Text>
              </Group>
              <Group align="baseline" gap="md" mb="sm">
                {sleepTrend.avg !== null && <Text fz="2rem" fw={700}>{sleepTrend.avg} hrs/night avg</Text>}
                {sleepTrend.delta !== null && (
                  <Text fz="sm" fw={500} c={sleepTrend.delta >= 0 ? 'green' : 'red'}>
                    {sleepTrend.delta >= 0 ? '+' : ''}{sleepTrend.delta} hrs/wk
                  </Text>
                )}
              </Group>
              <SimpleGrid cols={{ base: 3, sm: 6 }}>
                {sleepTrend.weekly.filter(w => w.sleep != null).map(w => (
                  <Stack key={w.week} gap={2} ta="center" p="xs" style={{ borderRadius: 'var(--mantine-radius-sm)', background: 'var(--mantine-color-default-hover)' }}>
                    <Text fz="xs" c="dimmed">{w.week.slice(5)}</Text>
                    <Text fz="sm" fw={700} c={(w.sleep as number) >= 7 ? 'green' : (w.sleep as number) >= 6 ? 'yellow' : 'red'}>
                      {(w.sleep as number).toFixed(1)}h
                    </Text>
                  </Stack>
                ))}
              </SimpleGrid>
              <Text fz="xs" c="dimmed" mt="xs">
                {sleepTrend.avg !== null && sleepTrend.avg >= 7 ? '✓ Meeting 7hr+ target' : '⚠ Below 7hr target — may impact recovery'}
              </Text>
            </Paper>
          )}

          {/* Nutrition Trend */}
          {nutritionTrend && (
            <Paper withBorder p="md">
              <Group gap="xs" mb="sm">
                <Utensils size={18} />
                <Text fw={500}>Nutrition Trend</Text>
              </Group>
              <SimpleGrid cols={{ base: 2, md: 4, lg: 6 }} mb="sm">
                {nutritionTrend.avgCalories !== null && (
                  <Stack gap={2} ta="center">
                    <Text fz="xs" c="dimmed">Avg Calories</Text>
                    <Text fz="lg" fw={700}>{nutritionTrend.avgCalories.toLocaleString()}</Text>
                    {nutritionTrend.caloriesChangePerWeek !== null && (
                      <Text fz="xs" fw={500} c={nutritionTrend.caloriesChangePerWeek >= 0 ? 'yellow' : 'green'}>
                        {nutritionTrend.caloriesChangePerWeek >= 0 ? '+' : ''}{nutritionTrend.caloriesChangePerWeek}/wk
                      </Text>
                    )}
                  </Stack>
                )}
                {nutritionTrend.avgProtein !== null && (
                  <Stack gap={2} ta="center">
                    <Group gap={4} justify="center">
                      <Beef size={12} />
                      <Text fz="xs" c="dimmed">Avg Protein</Text>
                    </Group>
                    <Text fz="lg" fw={700}>{nutritionTrend.avgProtein}g</Text>
                    {nutritionTrend.proteinChangePerWeek !== null && (
                      <Text fz="xs" fw={500} c={nutritionTrend.proteinChangePerWeek >= 0 ? 'green' : 'red'}>
                        {nutritionTrend.proteinChangePerWeek >= 0 ? '+' : ''}{nutritionTrend.proteinChangePerWeek}g/wk
                      </Text>
                    )}
                  </Stack>
                )}
                {nutritionTrend.avgCarb !== null && (
                  <Stack gap={2} ta="center">
                    <Text fz="xs" c="dimmed">Avg Carbs</Text>
                    <Text fz="lg" fw={700}>{nutritionTrend.avgCarb}g</Text>
                    {nutritionTrend.carbChangePerWeek !== null && (
                      <Text fz="xs" fw={500} c={nutritionTrend.carbChangePerWeek >= 0 ? 'yellow' : 'orange'}>
                        {nutritionTrend.carbChangePerWeek >= 0 ? '+' : ''}{nutritionTrend.carbChangePerWeek}g/wk
                      </Text>
                    )}
                  </Stack>
                )}
                {nutritionTrend.avgFat !== null && (
                  <Stack gap={2} ta="center">
                    <Text fz="xs" c="dimmed">Avg Fat</Text>
                    <Text fz="lg" fw={700}>{nutritionTrend.avgFat}g</Text>
                    {nutritionTrend.fatChangePerWeek !== null && (
                      <Text fz="xs" fw={500} c={nutritionTrend.fatChangePerWeek >= 0 ? 'yellow' : 'green'}>
                        {nutritionTrend.fatChangePerWeek >= 0 ? '+' : ''}{nutritionTrend.fatChangePerWeek}g/wk
                      </Text>
                    )}
                  </Stack>
                )}
                {nutritionTrend.avgWater !== null && (
                  <Stack gap={2} ta="center">
                    <Text fz="xs" c="dimmed">Avg Water</Text>
                    <Text fz="lg" fw={700}>{nutritionTrend.avgWater} {nutritionTrend.waterUnit === 'litres' ? 'L' : 'cups'}</Text>
                    {nutritionTrend.waterChangePerWeek !== null && (
                      <Text fz="xs" fw={500} c={nutritionTrend.waterChangePerWeek >= 0 ? 'blue' : 'orange'}>
                        {nutritionTrend.waterChangePerWeek >= 0 ? '+' : ''}{nutritionTrend.waterChangePerWeek}/wk
                      </Text>
                    )}
                  </Stack>
                )}
                {nutritionTrend.consistencyPct !== null && (
                  <Stack gap={2} ta="center">
                    <Text fz="xs" c="dimmed">Consistency</Text>
                    <Text fz="lg" fw={700} c={nutritionTrend.consistencyPct >= 80 ? 'green' : nutritionTrend.consistencyPct >= 50 ? 'yellow' : 'red'}>
                      {nutritionTrend.consistencyPct}%
                    </Text>
                  </Stack>
                )}
              </SimpleGrid>
            </Paper>
          )}

          {/* Athlete Measurements */}
          {(program?.meta?.height_cm || program?.meta?.arm_wingspan_cm || program?.meta?.leg_length_cm) && (
            <Paper withBorder p="md">
              <Group gap="xs" mb="sm">
                <Ruler size={18} />
                <Text fw={500}>Athlete Measurements</Text>
                <Text fz="xs" c="dimmed" ml="auto">Edit on Dashboard</Text>
              </Group>
              <SimpleGrid cols={3} spacing="md">
                {program.meta.height_cm && (
                  <Stack gap={2} ta="center" p="xs" style={{ borderRadius: 'var(--mantine-radius-sm)', background: 'var(--mantine-color-default-hover)' }}>
                    <Text fz="xs" c="dimmed">Height</Text>
                    <Text fz="lg" fw={700}>{program.meta.height_cm} cm</Text>
                  </Stack>
                )}
                {program.meta.arm_wingspan_cm && (
                  <Stack gap={2} ta="center" p="xs" style={{ borderRadius: 'var(--mantine-radius-sm)', background: 'var(--mantine-color-default-hover)' }}>
                    <Text fz="xs" c="dimmed">Arm Wingspan</Text>
                    <Text fz="lg" fw={700}>{program.meta.arm_wingspan_cm} cm</Text>
                  </Stack>
                )}
                {program.meta.leg_length_cm && (
                  <Stack gap={2} ta="center" p="xs" style={{ borderRadius: 'var(--mantine-radius-sm)', background: 'var(--mantine-color-default-hover)' }}>
                    <Text fz="xs" c="dimmed">Leg Length</Text>
                    <Text fz="lg" fw={700}>{program.meta.leg_length_cm} cm</Text>
                  </Stack>
                )}
              </SimpleGrid>
            </Paper>
          )}

          {program?.lift_profiles && program.lift_profiles.length > 0 && (
            <Paper withBorder p="md">
              <Group gap="xs" mb="sm">
                <Dumbbell size={18} />
                <Text fw={500}>Lift Style Profiles</Text>
                <Text fz="xs" c="dimmed" ml="auto">Edit on Dashboard</Text>
              </Group>
              <SimpleGrid cols={{ base: 1, lg: 3 }}>
                {program.lift_profiles.map((profile) => (
                  <Stack key={profile.lift} gap="xs" p="sm" style={{ borderRadius: 'var(--mantine-radius-sm)', background: 'var(--mantine-color-default-hover)' }}>
                    <Text fw={500} fz="sm" tt="capitalize" pb="xs" style={{ borderBottom: '1px solid var(--mantine-color-default-border)' }}>
                      {LIFT_LABELS[profile.lift] || profile.lift}
                    </Text>
                    {profile.style_notes && (
                      <Stack gap={2}>
                        <Text fz="xs" c="dimmed">Style &amp; Setup</Text>
                        <Text fz="xs" lh="lg">{profile.style_notes}</Text>
                      </Stack>
                    )}
                    {profile.sticking_points && (
                      <Stack gap={2}>
                        <Text fz="xs" c="dimmed">Sticking Points</Text>
                        <Text fz="xs" lh="lg" c="orange">{profile.sticking_points}</Text>
                      </Stack>
                    )}
                    {profile.primary_muscle && (
                      <Stack gap={2}>
                        <Text fz="xs" c="dimmed">Primary Driver</Text>
                        <Text fz="xs" fw={500}>{profile.primary_muscle}</Text>
                      </Stack>
                    )}
                    <Badge
                      color={profile.volume_tolerance === 'low' ? 'red' : profile.volume_tolerance === 'moderate' ? 'yellow' : 'green'}
                      variant="light"
                      tt="capitalize"
                    >
                      {profile.volume_tolerance} volume tolerance
                    </Badge>
                  </Stack>
                ))}
              </SimpleGrid>
            </Paper>
          )}

          {/* Competitions */}
          {competitions.length > 0 && (
            <Paper withBorder p="md">
              <Group gap="xs" mb="sm">
                <Trophy size={18} />
                <Text fw={500}>Competitions</Text>
              </Group>
              <Box style={{ overflowX: 'auto' }}>
                <Table fz="sm">
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>Name</Table.Th>
                      <Table.Th>Date</Table.Th>
                      <Table.Th visibleFrom="sm">Status</Table.Th>
                      <Table.Th ta="right" visibleFrom="sm">Squat</Table.Th>
                      <Table.Th ta="right" visibleFrom="sm">Bench</Table.Th>
                      <Table.Th ta="right" visibleFrom="sm">Deadlift</Table.Th>
                      <Table.Th ta="right">Total</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {competitions.map(c => (
                      <Table.Tr key={c.date + c.name}>
                        <Table.Td fw={500}>{c.name}</Table.Td>
                        <Table.Td c="dimmed">{c.date}</Table.Td>
                        <Table.Td visibleFrom="sm">{compStatusBadge(c.status)}</Table.Td>
                        {c.results ? (
                          <>
                            <Table.Td ta="right" visibleFrom="sm">{toDisplayUnit(c.results.squat_kg, unit).toFixed(1)}</Table.Td>
                            <Table.Td ta="right" visibleFrom="sm">{toDisplayUnit(c.results.bench_kg, unit).toFixed(1)}</Table.Td>
                            <Table.Td ta="right" visibleFrom="sm">{toDisplayUnit(c.results.deadlift_kg, unit).toFixed(1)}</Table.Td>
                            <Table.Td ta="right" fw={700}>{toDisplayUnit(c.results.total_kg, unit).toFixed(1)}</Table.Td>
                          </>
                        ) : (
                          <>
                            <Table.Td ta="right" c="dimmed" visibleFrom="sm">--</Table.Td>
                            <Table.Td ta="right" c="dimmed" visibleFrom="sm">--</Table.Td>
                            <Table.Td ta="right" c="dimmed" visibleFrom="sm">--</Table.Td>
                            <Table.Td ta="right" c="dimmed">--</Table.Td>
                          </>
                        )}
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </Box>
            </Paper>
          )}

          <WeeklyData
            data={data}
            viewMode={viewMode}
            perLiftDetails={perLiftDetails}
            muscleGroupAvgWeekly={muscleGroupAvgWeekly}
            analysisWeeks={effectiveWeeks}
            unit={unit}
          />
          <AiAnalysis effectiveWeeks={effectiveWeeks} weeksMode={weeksMode} readOnly={readOnly} />

          {/* Formula Reference */}
          <Accordion mt="xl" variant="separated" defaultValue="formulas-outer">
            <Accordion.Item value="formulas-outer">
              <Accordion.Control>
                <Text size="sm" fw={500} c="dimmed">How These Numbers Are Calculated</Text>
              </Accordion.Control>
              <Accordion.Panel>
                <Accordion variant="contained">
                  {FORMULA_DESCRIPTIONS.map(formula => (
                    <Accordion.Item
                      key={formula.id}
                      value={formula.id}
                      id={`formula-${formula.id}`}
                      style={{ scrollMarginTop: '6rem' }}
                    >
                      <Accordion.Control>
                        <Text size="sm" fw={500}>{formula.title}</Text>
                      </Accordion.Control>
                      <Accordion.Panel>
                        <Stack gap="xs">
                          <Text size="sm">{formula.summary}</Text>
                          <Box component="pre" fz="xs" p="sm" style={{ background: 'var(--mantine-color-dark-8, #1a1b1e)', borderRadius: 'var(--mantine-radius-sm)', overflowX: 'auto', fontFamily: 'monospace', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>{formula.formula}</Box>
                          {formula.variables && (
                            <SimpleGrid cols={2} spacing="xs">
                              {formula.variables.map(v => (
                                <Text key={v.name} size="xs"><Text span ff="monospace">{v.name}</Text>: {v.description}</Text>
                              ))}
                            </SimpleGrid>
                          )}
                          {formula.thresholds && (
                            <Table fz="xs" mt="xs">
                              <Table.Thead><Table.Tr><Table.Th ta="left">Condition</Table.Th><Table.Th ta="left">Value</Table.Th><Table.Th ta="left">Flag</Table.Th></Table.Tr></Table.Thead>
                              <Table.Tbody>{formula.thresholds.map(t => <Table.Tr key={t.label}><Table.Td>{t.label}</Table.Td><Table.Td>{t.value}</Table.Td><Table.Td>{t.flag || '—'}</Table.Td></Table.Tr>)}</Table.Tbody>
                            </Table>
                          )}
                        </Stack>
                      </Accordion.Panel>
                    </Accordion.Item>
                  ))}
                </Accordion>
              </Accordion.Panel>
            </Accordion.Item>
          </Accordion>

          {/* Flags */}
          {data.flags.length > 0 && (
            <Paper withBorder p="md">
              <Group gap="xs" mb="sm">
                <AlertTriangle size={18} color="var(--mantine-color-yellow-5)" />
                <Text fw={500}>Flags</Text>
              </Group>
              <Group gap="xs" wrap="wrap">
                {data.flags.map(flag => (
                  <Badge key={flag} color="yellow" variant="light">{flag}</Badge>
                ))}
              </Group>
            </Paper>
          )}

          {/* Footer */}
          <Text size="xs" c="dimmed">
            Week {analysisWindow.weekStart === analysisWindow.weekEnd ? analysisWindow.weekStart : `${analysisWindow.weekStart}-${analysisWindow.weekEnd}`} selected
            {' '}({data.block}) &middot; {data.sessions_analyzed} sessions analyzed
            {weeksMode === 'block' && ` · Full block (${effectiveWeeks} wks)`}
          </Text>
        </>
      )}

      {!data && !loading && !error && (
        <Center mih="20vh">
          <Text c="dimmed">No analysis data available for the selected period.</Text>
        </Center>
      )}
        </>
      )}

      {activeSection === 'blocks' && <PastBlocksPanel unit={unit} readOnly={readOnly} />}
      {activeSection === 'compare' && <LifetimeComparePanel unit={unit} readOnly={readOnly} />}
    </Stack>
  )
}
