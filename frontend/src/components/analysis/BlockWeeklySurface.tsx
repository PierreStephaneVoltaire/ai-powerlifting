import { useEffect, useMemo, useState } from 'react'
import {
  Activity,
  Beef,
  Brain,
  CheckCircle,
  Dumbbell,
  Info,
  Moon,
  RefreshCw,
  Ruler,
  Scale,
  TrendingUp,
  Utensils,
} from 'lucide-react'
import {
  Badge,
  Box,
  Button,
  Group,
  Paper,
  Progress,
  SimpleGrid,
  Loader,
  Stack,
  Table,
  Text,
  Tooltip,
  SegmentedControl,
} from '@mantine/core'
import type { Program, Session, WeightEntry, GlossaryExercise, ExerciseCategory } from '@powerlifting/types'
import type { Sex } from '@powerlifting/types'
import type { Unit } from '@/store/settingsStore'
import { calculateDots } from '@/utils/dots'
import { calculateIpfGl, getIpfGlModeLabel, type IpfGlMode } from '@/utils/ipfGl'
import { toDisplayUnit } from '@/utils/units'
import { buildBodyweightTrend, latestBodyweightOnOrBefore, mergeBodyweightEntries } from '@/utils/bodyweight'
import { fetchGlossary, fetchWeightLog } from '@/api/client'
import {
  type BlockAnalysisBundle,
  type CorrelationReport,
  type WeeklyAnalysis,
  fetchBlockCorrelationReport,
} from '@/api/analytics'
import { executedSets, exerciseVolume, normalizeExerciseName } from '@/utils/volume'
import { WeeklyData } from '@/components/analysis/WeeklyData'

function estimateAnalysisE1rm(kg: number, reps: number, rpe?: number | null): number | null {
  if (kg <= 0 || reps <= 0) return null
  const RPE_TABLE_PRIMARY = new Map<string, number>([
    ['1-10', 1.000], ['2-10', 0.960], ['3-10', 0.930], ['4-10', 0.900], ['5-10', 0.880], ['6-10', 0.860],
    ['1-9', 1.000], ['2-9', 0.940], ['3-9', 0.900], ['4-9', 0.870], ['5-9', 0.845], ['6-9', 0.825],
    ['1-8', 1.000], ['2-8', 0.920], ['3-8', 0.875], ['4-8', 0.845], ['5-8', 0.815], ['6-8', 0.795],
    ['1-7', 1.000], ['2-7', 0.900], ['3-7', 0.850], ['4-7', 0.820], ['5-7', 0.795], ['6-7', 0.775],
    ['1-6', 1.000], ['2-6', 0.880], ['3-6', 0.830], ['4-6', 0.800], ['5-6', 0.775], ['6-6', 0.755],
  ])
  const CONSERVATIVE_REP_PCT: Record<number, number> = {
    1: 1.000, 2: 0.955, 3: 0.925, 4: 0.898, 5: 0.875,
  }
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

function getInolThresholds(lift: string, thresholds?: Record<string, { low: number; high: number }>) {
  const defaultThresholds: Record<string, { low: number; high: number }> = {
    squat: { low: 1.6, high: 3.5 },
    bench: { low: 2.0, high: 5.0 },
    deadlift: { low: 1.0, high: 2.5 },
  }
  return thresholds?.[lift] ?? defaultThresholds[lift] ?? { low: 2.0, high: 4.0 }
}

function getInolZoneMeta(value: number, thresholds: { low: number; high: number }) {
  if (value < thresholds.low) return { color: 'yellow', label: 'Low stimulus' }
  if (value > thresholds.high) return { color: 'red', label: 'Overreaching' }
  return { color: 'green', label: 'Productive' }
}

function getAcwrZoneMeta(zone?: string | null) {
  const map: Record<string, { color: string; label: string }> = {
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
  return map[zone ?? 'unknown'] ?? { color: 'gray', label: zone ? zone.replace(/_/g, ' ') : 'Unknown' }
}

function formatSignedDeltaKg(deltaKg: number, unit: Unit) {
  const value = toDisplayUnit(Math.abs(deltaKg), unit).toFixed(1)
  return `${deltaKg >= 0 ? '+' : '-'}${value} ${unit}`
}

function analysisWindowDates(bundle: BlockAnalysisBundle) {
  return {
    start: bundle.block.startDate,
    end: bundle.block.endDate,
    weekStart: bundle.block.weekStart,
    weekEnd: bundle.block.weekEnd,
    weeks: bundle.block.weekCount,
  }
}

function buildBlockSessions(program: Program | null, block: string): Session[] {
  return (program?.sessions ?? []).filter((session) => (session.block ?? 'current') === block && session.completed)
}

function buildBlockBodyweightSessions(program: Program | null, block: string, startDate: string, endDate: string): Session[] {
  return (program?.sessions ?? []).filter((session) =>
    (session.block ?? 'current') === block &&
    session.status !== 'skipped' &&
    session.date >= startDate &&
    session.date <= endDate
  )
}

export function BlockWeeklySurface({
  program,
  bundle,
  unit,
  sex,
  version,
}: {
  program: Program | null
  bundle: BlockAnalysisBundle
  unit: Unit
  sex: Sex
  version: string
}) {
  const [viewMode, setViewMode] = useState<'raw' | 'graph'>('raw')
  const [weightLog, setWeightLog] = useState<WeightEntry[]>([])
  const [glossary, setGlossary] = useState<GlossaryExercise[]>([])
  const [correlationReport, setCorrelationReport] = useState<CorrelationReport | null>(null)
  const [correlationLoading, setCorrelationLoading] = useState(false)
  const [correlationError, setCorrelationError] = useState<string | null>(null)

  const analysisWindow = useMemo(() => analysisWindowDates(bundle), [bundle])
  const filteredSessions = useMemo(
    () => buildBlockSessions(program, bundle.block.block).filter((s) => s.week_number >= analysisWindow.weekStart && s.week_number <= analysisWindow.weekEnd && s.date <= analysisWindow.end),
    [analysisWindow.end, analysisWindow.weekEnd, analysisWindow.weekStart, bundle.block.block, program],
  )
  const bodyweightSessions = useMemo(
    () => buildBlockBodyweightSessions(program, bundle.block.block, analysisWindow.start, analysisWindow.end),
    [analysisWindow.end, analysisWindow.start, bundle.block.block, program],
  )

  useEffect(() => {
    fetchWeightLog(version).then(setWeightLog).catch(() => undefined)
    fetchGlossary().then(setGlossary).catch(() => undefined)
  }, [version])

  const loadCorrelation = (refresh = false, cacheOnly = false) => {
    if (analysisWindow.weeks < 4) {
      setCorrelationReport(null)
      setCorrelationError(null)
      setCorrelationLoading(false)
      return
    }
    setCorrelationLoading(true)
    setCorrelationError(null)
    fetchBlockCorrelationReport(bundle.block.blockKey, { refresh, cacheOnly })
      .then(setCorrelationReport)
      .catch((error: unknown) => setCorrelationError(error instanceof Error ? error.message : 'Failed to load ROI correlation'))
      .finally(() => setCorrelationLoading(false))
  }

  useEffect(() => {
    loadCorrelation(false, true)
  }, [analysisWindow.weeks, bundle.block.blockKey])

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

  const avgSessionsPerWeek = Math.round((bundle.weekly.sessions_analyzed / Math.max(1, analysisWindow.weeks)) * 10) / 10

  const muscleGroupAvgWeekly = useMemo(() => {
    if (!glossaryMuscles.size || !filteredSessions.length) return { sets: {}, volume: {} }
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
      avgSets[m] = Math.round((mgSets[m] / Math.max(1, analysisWindow.weeks)) * 10) / 10
      avgVol[m] = Math.round(mgVol[m] / Math.max(1, analysisWindow.weeks))
    }
    return { sets: avgSets, volume: avgVol }
  }, [analysisWindow.weeks, filteredSessions, glossaryMuscles])

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
          const exLower = ex.name.toLowerCase().trim()
          const info = glossaryCategory.get(normalizeExerciseName(ex.name))
          const isMainLift = exLower === liftName || (liftName === 'bench' && exLower === 'bench press')
          if (isMainLift || (info && info === category)) hasLift = true
          if (isMainLift) rawSets += executedSets(ex)
          if (info && info === category && !isMainLift) {
            const sets = executedSets(ex)
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
  }, [filteredSessions, glossaryCategory])

  const projectionCalibration = bundle.weekly.projection_calibration ?? null

  const nutritionTrend = useMemo(() => {
    if (!program?.diet_notes?.length) return null
    const inWindow = program.diet_notes
      .filter((n) => n.date >= analysisWindow.start && n.date <= analysisWindow.end)
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
      const d = new Date(note.date)
      const day = d.getDay() || 7
      d.setDate(d.getDate() - day + 1)
      const weekKey = d.toISOString().slice(0, 10)
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
    const weekly = Array.from(weeklyMap.entries()).sort(([a], [b]) => a.localeCompare(b)).map(([week, b]) => ({
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
  }, [analysisWindow.end, analysisWindow.start, program?.diet_notes])

  const fallbackBodyweight = useMemo(() => {
    const competitionBodyweight = bundle.historical.competitionOutcome?.bodyweightKg ?? null
    const latestSessionWeight = [...filteredSessions].reverse().find((session) => typeof session.body_weight_kg === 'number')?.body_weight_kg ?? null
    const latestLogWeight = weightLog.length > 0 ? weightLog[weightLog.length - 1].kg : null
    return competitionBodyweight ?? latestSessionWeight ?? latestLogWeight
  }, [bundle.historical.competitionOutcome?.bodyweightKg, filteredSessions, weightLog])

  const bodyweightEntries = useMemo(
    () => mergeBodyweightEntries(weightLog, bodyweightSessions),
    [bodyweightSessions, weightLog],
  )

  const weightTrend = useMemo(
    () => buildBodyweightTrend(bodyweightEntries, analysisWindow.start, analysisWindow.end),
    [analysisWindow.end, analysisWindow.start, bodyweightEntries],
  )

  const dotsTrend = useMemo(() => {
    if (!filteredSessions.length) return null
    type WeekData = { squat: number; bench: number; deadlift: number; bw: number; date: string | null; hasSquat: boolean; hasBench: boolean; hasDeadlift: boolean }
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
    const rows = Array.from(byWeek.entries()).sort(([a], [b]) => a - b).map(([wn, d]) => {
      let bw = d.bw
      if (!bw) bw = latestBodyweightOnOrBefore(bodyweightEntries, d.date ?? analysisWindow.end, fallbackBodyweight) ?? 0
      const total = (d.squat > 0 ? d.squat : 0) + (d.bench > 0 ? d.bench : 0) + (d.deadlift > 0 ? d.deadlift : 0)
      const dots = total > 0 && bw > 0 ? calculateDots(total, bw, sex) : null
      const hasFullSbd = d.hasSquat && d.hasBench && d.hasDeadlift
      const hasBenchOnly = d.hasBench && !d.hasSquat && !d.hasDeadlift
      const ipfGl = bw > 0 && hasFullSbd && total > 0
        ? calculateIpfGl(total, bw, sex, 'classic_powerlifting')
        : bw > 0 && hasBenchOnly && d.bench > 0
          ? calculateIpfGl(d.bench, bw, sex, 'classic_bench')
          : null
      const ipfGlMode: IpfGlMode | null = hasFullSbd && total > 0 ? 'classic_powerlifting' : hasBenchOnly && d.bench > 0 ? 'classic_bench' : null
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
    }).filter((r) => r.squat || r.bench || r.deadlift)
    if (!rows.length) return null
    const withDots = rows.filter(r => r.dots !== null)
    let dotsChange: number | null = null
    if (withDots.length >= 2) {
      dotsChange = Math.round(((withDots[withDots.length - 1].dots! - withDots[0].dots!) / Math.max(1, withDots.length - 1)) * 100) / 100
    }
    return { rows, dotsChange }
  }, [analysisWindow.end, bodyweightEntries, fallbackBodyweight, filteredSessions, sex])

  const ipfGlTrend = useMemo(() => {
    if (!dotsTrend?.rows.length) return null
    const comparable = dotsTrend.rows.filter((r): r is typeof r & { ipfGl: number; ipfGlMode: IpfGlMode } => r.ipfGl !== null && r.ipfGlMode !== null)
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
    let bw = weightTrend?.latest || fallbackBodyweight || 0
    const dots = total > 0 && bw > 0 ? calculateDots(total, bw, sex) : null
    return { squat: squat || null, bench: bench || null, deadlift: deadlift || null, total, dots }
  }, [dotsTrend, fallbackBodyweight, sex, weightTrend?.latest])

  const actualProjectedTotalKg = bundle.historical.competitionOutcome?.results?.total_kg ?? null

  const sleepTrend = useMemo(() => {
    const weeks = nutritionTrend?.weekly.filter(w => w.sleep != null) || []
    if (!weeks.length) return null
    return { avg: nutritionTrend?.avgSleep ?? null, delta: nutritionTrend?.sleepChangePerWeek ?? null, weekly: weeks }
  }, [nutritionTrend])

  return (
    <Stack gap="lg">
      <Group justify="space-between" wrap="wrap">
        <Text fw={500}>Block Analysis Surface</Text>
        <SegmentedControl
          size="xs"
          value={viewMode}
          onChange={(v) => setViewMode(v as 'raw' | 'graph')}
          data={[
            { value: 'raw', label: 'Table' },
            { value: 'graph', label: 'Charts' },
          ]}
        />
      </Group>

      <SimpleGrid cols={{ base: 1, sm: 2, xl: 4 }} spacing="md">
        <Paper withBorder p="md">
          <Group gap="xs" mb="xs"><Dumbbell size={18} /><Text fw={500}>Estimated 1 Rep Maxes</Text></Group>
          {highestMaxes ? (
            <Stack gap="xs">
              <SimpleGrid cols={3}>
                <Stack gap={2} ta="center"><Text fz="xs" c="dimmed">Squat</Text><Text fz="lg" fw={700}>{highestMaxes.squat !== null ? toDisplayUnit(highestMaxes.squat, unit).toFixed(1) : '--'}</Text></Stack>
                <Stack gap={2} ta="center"><Text fz="xs" c="dimmed">Bench</Text><Text fz="lg" fw={700}>{highestMaxes.bench !== null ? toDisplayUnit(highestMaxes.bench, unit).toFixed(1) : '--'}</Text></Stack>
                <Stack gap={2} ta="center"><Text fz="xs" c="dimmed">Deadlift</Text><Text fz="lg" fw={700}>{highestMaxes.deadlift !== null ? toDisplayUnit(highestMaxes.deadlift, unit).toFixed(1) : '--'}</Text></Stack>
              </SimpleGrid>
              {highestMaxes.dots !== null && <Text fz="sm" c="dimmed">Est. DOTS: <Text span fw={500}>{highestMaxes.dots.toFixed(2)}</Text></Text>}
              <Text fz="xs" c="dimmed">via session e1RM</Text>
            </Stack>
          ) : bundle.weekly.current_maxes ? (
            <Stack gap="xs">
              <SimpleGrid cols={3}>
                <Stack gap={2} ta="center"><Text fz="xs" c="dimmed">Squat</Text><Text fz="lg" fw={700}>{bundle.weekly.current_maxes.squat ? toDisplayUnit(bundle.weekly.current_maxes.squat, unit).toFixed(1) : '--'}</Text></Stack>
                <Stack gap={2} ta="center"><Text fz="xs" c="dimmed">Bench</Text><Text fz="lg" fw={700}>{bundle.weekly.current_maxes.bench ? toDisplayUnit(bundle.weekly.current_maxes.bench, unit).toFixed(1) : '--'}</Text></Stack>
                <Stack gap={2} ta="center"><Text fz="xs" c="dimmed">Deadlift</Text><Text fz="lg" fw={700}>{bundle.weekly.current_maxes.deadlift ? toDisplayUnit(bundle.weekly.current_maxes.deadlift, unit).toFixed(1) : '--'}</Text></Stack>
              </SimpleGrid>
              {bundle.weekly.estimated_dots !== null && <Text fz="sm" c="dimmed">Est. DOTS: <Text span fw={500}>{bundle.weekly.estimated_dots.toFixed(2)}</Text></Text>}
            </Stack>
          ) : <Text fz="sm" c="dimmed">No max data available</Text>}
        </Paper>

        <Paper withBorder p="md">
          <Group gap="xs" mb="xs"><CheckCircle size={18} /><Text fw={500}>Compliance</Text></Group>
          {bundle.weekly.compliance ? (
            <Stack gap={2}>
              <Text fz="2rem" fw={700} c={complianceBadgeColor(bundle.weekly.compliance.pct)}>{bundle.weekly.compliance.pct.toFixed(0)}%</Text>
              <Text fz="sm" c="dimmed">{bundle.weekly.compliance.completed}/{bundle.weekly.compliance.planned} sessions</Text>
              <Text fz="xs" c="dimmed">{bundle.weekly.compliance.phase} block</Text>
              <Text fz="xs" c="dimmed">Avg {avgSessionsPerWeek} sessions/wk</Text>
            </Stack>
          ) : <Text fz="sm" c="dimmed">No compliance data</Text>}
        </Paper>

        <Paper withBorder p="md">
          <Group gap="xs" mb="xs"><Activity size={18} /><Text fw={500}>Current Fatigue State</Text></Group>
          <Stack gap={2}>
            <Text fz="2rem" fw={700} c={fatigueBadgeColor(bundle.weekly.fatigue_index)}>{bundle.weekly.fatigue_index !== null ? (bundle.weekly.fatigue_index * 100).toFixed(0) + '%' : 'N/A'}</Text>
            <Text fz="sm" c="dimmed">{fatigueLabel(bundle.weekly.fatigue_index)} current state</Text>
            <Group gap="xs" wrap="wrap">
              {typeof bundle.weekly.fatigue_components?.window_mean_fi === 'number' && <Badge variant="light" color="blue">Window mean {(bundle.weekly.fatigue_components.window_mean_fi * 100).toFixed(0)}%</Badge>}
              {typeof bundle.weekly.fatigue_components?.window_peak_fi === 'number' && <Badge variant="light" color="orange">Window peak {(bundle.weekly.fatigue_components.window_peak_fi * 100).toFixed(0)}%</Badge>}
            </Group>
            <Text fz="xs" c="dimmed" lh="lg">
              Failures: {((bundle.weekly.fatigue_components?.failure_stress ?? 0) * 100).toFixed(0)}%
              &middot; Spike: {((bundle.weekly.fatigue_components?.acute_spike_stress ?? 0) * 100).toFixed(0)}%
              &middot; RPE: {((bundle.weekly.fatigue_components?.rpe_stress ?? 0) * 100).toFixed(0)}%
              &middot; Reservoir: {((bundle.weekly.fatigue_components?.chronic_load_stress ?? 0) * 100).toFixed(0)}%
              &middot; Streak: {((bundle.weekly.fatigue_components?.overload_streak ?? 0) * 100).toFixed(0)}%
              &middot; Intensity: {((bundle.weekly.fatigue_components?.intensity_density_stress ?? 0) * 100).toFixed(0)}%
              &middot; Strain: {((bundle.weekly.fatigue_components?.monotony_stress ?? 0) * 100).toFixed(0)}%
            </Text>
            {bundle.weekly.fatigue_components?.reservoir_dimension_stress && (
              <Group gap={6} wrap="wrap" mt={4}>
                {Object.entries(bundle.weekly.fatigue_components.reservoir_dimension_stress).map(([dim, value]) => (
                  <Badge key={dim} variant="light" color={value >= 0.75 ? 'red' : value >= 0.5 ? 'orange' : 'gray'} style={{ textTransform: 'capitalize' }}>
                    {dim} {(value * 100).toFixed(0)}%
                  </Badge>
                ))}
              </Group>
            )}
            {bundle.weekly.fatigue_components?.fatigue_context_confidence && (
              <Text fz="xs" c="dimmed" mt="xs">
                Context: {typeof bundle.weekly.fatigue_components.fatigue_context_days_used === 'number'
                  ? `${bundle.weekly.fatigue_components.fatigue_context_days_used}d`
                  : `${bundle.weekly.fatigue_components.fatigue_context_weeks_used ?? 0}w`} ({bundle.weekly.fatigue_components.fatigue_context_confidence} confidence)
              </Text>
            )}
          </Stack>
        </Paper>
      </SimpleGrid>

      {bundle.weekly.inol?.avg_inol && (
        <Paper withBorder p="md">
          <Group gap="xs" mb="sm">
            <Text fw={500}>Stimulus-Adjusted INOL (Window Average)</Text>
            <Tooltip label="INOL means intensity-number-of-lifts. Here it is adjusted by your lift-profile stimulus coefficient to reflect how hard the same workload is for you." withArrow multiline w={320}>
              <Info size={14} style={{ cursor: 'help', color: 'var(--mantine-color-gray-6)' }} />
            </Tooltip>
          </Group>
          <SimpleGrid cols={3} mb="sm">
            {Object.entries(bundle.weekly.inol.avg_inol).map(([lift, val]) => {
              const coefficient = bundle.weekly.inol?.stimulus_coefficients?.[lift] ?? 1
              const baseThresholds = getInolThresholds(lift, bundle.weekly.inol?.thresholds)
              const adjusted = bundle.weekly.inol?.phase_adjusted_thresholds?.[lift]
              const displayThresholds = adjusted ? { low: adjusted.display_low, high: adjusted.display_high } : baseThresholds
              const zoneMeta = getInolZoneMeta(val, displayThresholds)
              const raw = bundle.weekly.inol?.raw_avg_inol?.[lift]
              const trend = bundle.weekly.inol?.trend_pressure?.[lift]
              const rampGrace = bundle.weekly.inol?.ramp_up_grace?.[lift]
              return (
                <Stack key={lift} gap={2} ta="center" p="sm" style={{ borderRadius: 'var(--mantine-radius-sm)', background: `var(--mantine-color-${zoneMeta.color}-light)` }}>
                  <Text fz="xs" c="dimmed" tt="capitalize">{lift}</Text>
                  <Text fz="xl" fw={700} c={zoneMeta.color}>{val.toFixed(2)}</Text>
                  {typeof raw === 'number' && <Text fz="xs" c="dimmed">Raw {raw.toFixed(2)}</Text>}
                  <Text fz="xs" c="dimmed">Stimulus x{coefficient.toFixed(2)}</Text>
                  <Text fz="xs" c="dimmed">{zoneMeta.label}</Text>
                  <Text fz="xs" c="dimmed">Target {(adjusted?.low ?? baseThresholds.low).toFixed(1)} - {(adjusted?.high ?? baseThresholds.high).toFixed(1)}</Text>
                  {trend && <Text fz="xs" c="dimmed">Trend {(trend.value * 100).toFixed(0)}%</Text>}
                  {rampGrace && <Badge color="blue" variant="light" size="xs">Ramp-up grace</Badge>}
                </Stack>
              )
            })}
          </SimpleGrid>
        </Paper>
      )}

      {bundle.weekly.acwr && !('status' in bundle.weekly.acwr) && (
        <Paper withBorder p="md">
          <Group justify="space-between" mb="sm">
            <Group gap="xs">
              <Text fw={500}>EWMA ACWR (daily workload ratio)</Text>
              <Tooltip label="EWMA ACWR means exponentially weighted moving average acute:chronic workload ratio. It compares short-term load to longer-term load while weighting recent work more heavily." withArrow multiline w={340}>
                <Info size={14} style={{ cursor: 'help', color: 'var(--mantine-color-gray-6)' }} />
              </Tooltip>
            </Group>
            <Badge color={getAcwrZoneMeta((bundle.weekly.acwr as any).composite_zone).color} variant="light">
              Composite: {(bundle.weekly.acwr as any).composite?.toFixed(2) ?? 'N/A'} ({(bundle.weekly.acwr as any).composite_label ?? getAcwrZoneMeta((bundle.weekly.acwr as any).composite_zone).label})
            </Badge>
          </Group>
          <Text fz="xs" c="dimmed" mb="sm">
            Daily EWMA acute/chronic ratio. The labels describe workload pattern, not validated injury risk.
          </Text>
          <SimpleGrid cols={4} spacing="md">
            {Object.entries((bundle.weekly.acwr as any).dimensions).map(([dim, info]: [string, any]) => {
              const zoneMeta = getAcwrZoneMeta(info.zone)
              return (
                <Stack key={dim} gap={2} ta="center" p="sm" style={{ borderRadius: 'var(--mantine-radius-sm)', background: `var(--mantine-color-${zoneMeta.color}-light)` }}>
                  <Text fz="xs" tt="capitalize">{dim}</Text>
                  <Text fz="xl" fw={700}>{info.value?.toFixed(2) ?? '--'}</Text>
                  <Text fz="xs">{info.label ?? zoneMeta.label}</Text>
                </Stack>
              )
            })}
          </SimpleGrid>
        </Paper>
      )}

      {bundle.weekly.ri_distribution && (
        <Paper withBorder p="md">
          <Text fw={500} mb="sm">Relative Intensity Distribution</Text>
          <SimpleGrid cols={3} mb="md">
            {(['heavy', 'moderate', 'light'] as const).map((bucket) => {
              const info = bundle.weekly.ri_distribution!.overall[bucket]
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
        </Paper>
      )}

      {bundle.weekly.specificity_ratio && (
        <Paper withBorder p="md">
          <Group justify="space-between" align="flex-start" mb="sm">
            <Group gap="xs">
              <Text fw={500}>Specificity Ratio</Text>
              <Tooltip label="Specificity ratio shows how much of your work is directly specific to competition. Narrow counts only SBD sets. Broad counts SBD plus closely related secondary work." withArrow multiline w={320}>
                <Info size={14} style={{ cursor: 'help', color: 'var(--mantine-color-gray-6)' }} />
              </Tooltip>
            </Group>
            {bundle.weekly.specificity_ratio.expected_band ? (
              <Group gap="xs" wrap="wrap" justify="flex-end">
                <Badge variant="light" color={specificityStatusBadgeColor(bundle.weekly.specificity_ratio.narrow_status)}>Narrow {specificityStatusLabel(bundle.weekly.specificity_ratio.narrow_status)}</Badge>
                <Badge variant="light" color={specificityStatusBadgeColor(bundle.weekly.specificity_ratio.broad_status)}>Broad {specificityStatusLabel(bundle.weekly.specificity_ratio.broad_status)}</Badge>
              </Group>
            ) : <Badge variant="light" color="gray">No upcoming comp band</Badge>}
          </Group>
          <SimpleGrid cols={2} spacing="md">
            <Stack gap="xs">
              <Text fz="xs" c="dimmed">Narrow (SBD only)</Text>
              <Progress value={Math.min(bundle.weekly.specificity_ratio.narrow * 100, 100)} />
              <Text fz="sm" fw={500}>{(bundle.weekly.specificity_ratio.narrow * 100).toFixed(1)}%</Text>
            </Stack>
            <Stack gap="xs">
              <Text fz="xs" c="dimmed">Broad (SBD + secondary)</Text>
              <Progress value={Math.min(bundle.weekly.specificity_ratio.broad * 100, 100)} color="blue" />
              <Text fz="sm" fw={500}>{(bundle.weekly.specificity_ratio.broad * 100).toFixed(1)}%</Text>
            </Stack>
          </SimpleGrid>
        </Paper>
      )}

      {bundle.weekly.fatigue_dimensions && Object.keys(bundle.weekly.fatigue_dimensions.weekly).length > 0 && (
        <Paper withBorder p="md">
          <Text fw={500} mb="sm">Fatigue Dimensions (Weekly)</Text>
          <Box style={{ overflowX: 'auto' }}>
            <Table fz="sm">
              <Table.Thead><Table.Tr><Table.Th>Week</Table.Th><Table.Th ta="right">Axial</Table.Th><Table.Th ta="right">Neural</Table.Th><Table.Th ta="right">Peripheral</Table.Th><Table.Th ta="right">Systemic</Table.Th></Table.Tr></Table.Thead>
              <Table.Tbody>
                {Object.entries(bundle.weekly.fatigue_dimensions.weekly).sort(([a], [b]) => Number(a) - Number(b)).slice(-8).map(([week, dims]) => (
                  <Table.Tr key={week}><Table.Td fw={500}>W{week}</Table.Td><Table.Td ta="right">{dims.axial.toFixed(1)}</Table.Td><Table.Td ta="right">{dims.neural.toFixed(1)}</Table.Td><Table.Td ta="right">{dims.peripheral.toFixed(1)}</Table.Td><Table.Td ta="right">{dims.systemic.toFixed(1)}</Table.Td></Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Box>
        </Paper>
      )}

      {bundle.weekly.projections.filter((p) => p && typeof p === 'object').length > 0 ? (
        <Stack gap="sm">
          <Group justify="space-between" align="center">
            <Group gap="xs"><TrendingUp size={18} /><Text fw={500}>Projections</Text></Group>
            {projectionCalibration?.calibrated && <Badge variant="light" color="teal">Calibrated from {projectionCalibration.meets} meet{projectionCalibration.meets === 1 ? '' : 's'}</Badge>}
          </Group>
          <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="md">
            {bundle.weekly.projections.filter((p) => p && typeof p === 'object').map((proj, i) => (
              <Paper key={i} withBorder p="md">
                <Group gap="xs" mb="xs"><TrendingUp size={18} /><Text fw={500}>{proj.comp_name || 'Projected Total'}</Text></Group>
                <Text fz="2rem" fw={700}>{toDisplayUnit(proj.total || 0, unit).toFixed(1)} {unit}</Text>
                <Text fz="sm" c="dimmed" mt="xs">Confidence: {((proj.confidence || 0) * 100).toFixed(0)}%{typeof proj.weeks_to_comp === 'number' && ` (${proj.weeks_to_comp.toFixed(1)} wks out)`}</Text>
                {proj.method && <Text fz="xs" c="dimmed">via {proj.method === 'session_estimated' ? 'session e1RM' : proj.method}</Text>}
                {actualProjectedTotalKg !== null && proj.total !== null && (
                  <Text fz="xs" c={actualProjectedTotalKg - proj.total >= 0 ? 'green' : 'red'} mt={4}>
                    Actual: {toDisplayUnit(actualProjectedTotalKg, unit).toFixed(1)} {unit}
                    {' '}• Delta: {formatSignedDeltaKg(actualProjectedTotalKg - proj.total, unit)}
                  </Text>
                )}
              </Paper>
            ))}
          </SimpleGrid>
        </Stack>
      ) : (
        <Paper withBorder p="md"><Group gap="xs" mb="xs"><TrendingUp size={18} /><Text fw={500}>Projected Total</Text></Group><Text fz="lg" c="dimmed">{bundle.weekly.projection_reason || 'No competition date set'}</Text></Paper>
      )}

      {dotsTrend && dotsTrend.rows.length >= 2 && (
        <Paper withBorder p="md">
          <Group gap="xs" mb="sm">
            <TrendingUp size={18} />
            <Text fw={500}>e1RM Progression &amp; DOTS Trend</Text>
            {dotsTrend.dotsChange !== null && <Badge color={dotsTrend.dotsChange >= 0 ? 'green' : 'red'} variant="light" ml="auto">{dotsTrend.dotsChange >= 0 ? '+' : ''}{dotsTrend.dotsChange} DOTS/wk</Badge>}
            {ipfGlTrend && <Badge color={ipfGlTrend.change >= 0 ? 'green' : 'red'} variant="light" ml="xs">{ipfGlTrend.change >= 0 ? '+' : ''}{ipfGlTrend.change} {getIpfGlModeLabel(ipfGlTrend.mode)} GL/wk</Badge>}
          </Group>
          <Table fz="sm">
            <Table.Thead><Table.Tr><Table.Th>W</Table.Th><Table.Th ta="right">Squat</Table.Th><Table.Th ta="right">Bench</Table.Th><Table.Th ta="right">Deadlift</Table.Th><Table.Th ta="right" visibleFrom="sm">Total</Table.Th><Table.Th ta="right">DOTS</Table.Th><Table.Th ta="right">IPF GL</Table.Th></Table.Tr></Table.Thead>
            <Table.Tbody>{dotsTrend.rows.map((r) => <Table.Tr key={r.week}><Table.Td fw={500}>W{r.week}</Table.Td><Table.Td ta="right">{r.squat !== null ? toDisplayUnit(r.squat, unit).toFixed(1) : '--'}</Table.Td><Table.Td ta="right">{r.bench !== null ? toDisplayUnit(r.bench, unit).toFixed(1) : '--'}</Table.Td><Table.Td ta="right">{r.deadlift !== null ? toDisplayUnit(r.deadlift, unit).toFixed(1) : '--'}</Table.Td><Table.Td ta="right" fw={500} visibleFrom="sm">{r.total !== null ? toDisplayUnit(r.total, unit).toFixed(1) : '--'}</Table.Td><Table.Td ta="right" fw={700} c="blue">{r.dots?.toFixed(2) ?? '--'}</Table.Td><Table.Td ta="right">{r.ipfGl !== null && r.ipfGlMode !== null ? <Stack gap={0} align="flex-end"><Text span fw={700} fz="sm">{r.ipfGl.toFixed(2)}</Text><Text span fz="xs" c="dimmed">{getIpfGlModeLabel(r.ipfGlMode)}</Text></Stack> : <Text span fz="sm" c="dimmed">--</Text>}</Table.Td></Table.Tr>)}</Table.Tbody>
          </Table>
        </Paper>
      )}

      {weightTrend && (
        <Paper withBorder p="md">
          <Group gap="xs" mb="sm"><Scale size={18} /><Text fw={500}>Body Weight Trend</Text></Group>
          <Group align="baseline" gap="md">
            <Text fz="2rem" fw={700}>{toDisplayUnit(weightTrend.latest, unit).toFixed(1)} {unit}</Text>
            <Text fz="sm" fw={500} c={weightTrend.change >= 0 ? 'yellow' : 'green'}>{weightTrend.change >= 0 ? '+' : ''}{toDisplayUnit(Math.abs(weightTrend.change), unit).toFixed(1)} {unit} over {analysisWindow.weeks} wk{analysisWindow.weeks !== 1 ? 's' : ''}</Text>
          </Group>
        </Paper>
      )}

      {sleepTrend && (
        <Paper withBorder p="md">
          <Group gap="xs" mb="sm"><Moon size={18} /><Text fw={500}>Sleep Trend</Text></Group>
          <Group align="baseline" gap="md" mb="sm">
            {sleepTrend.avg !== null && <Text fz="2rem" fw={700}>{sleepTrend.avg} hrs/night avg</Text>}
            {sleepTrend.delta !== null && <Text fz="sm" fw={500} c={sleepTrend.delta >= 0 ? 'green' : 'red'}>{sleepTrend.delta >= 0 ? '+' : ''}{sleepTrend.delta} hrs/wk</Text>}
          </Group>
        </Paper>
      )}

      {nutritionTrend && (
        <Paper withBorder p="md">
          <Group gap="xs" mb="sm"><Utensils size={18} /><Text fw={500}>Nutrition Trend</Text></Group>
          <SimpleGrid cols={{ base: 2, md: 4, lg: 6 }} mb="sm">
            {nutritionTrend.avgCalories !== null && <Stack gap={2} ta="center"><Text fz="xs" c="dimmed">Avg Calories</Text><Text fz="lg" fw={700}>{nutritionTrend.avgCalories.toLocaleString()}</Text></Stack>}
            {nutritionTrend.avgProtein !== null && <Stack gap={2} ta="center"><Group gap={4} justify="center"><Beef size={12} /><Text fz="xs" c="dimmed">Avg Protein</Text></Group><Text fz="lg" fw={700}>{nutritionTrend.avgProtein}g</Text></Stack>}
            {nutritionTrend.avgCarb !== null && <Stack gap={2} ta="center"><Text fz="xs" c="dimmed">Avg Carbs</Text><Text fz="lg" fw={700}>{nutritionTrend.avgCarb}g</Text></Stack>}
            {nutritionTrend.avgFat !== null && <Stack gap={2} ta="center"><Text fz="xs" c="dimmed">Avg Fat</Text><Text fz="lg" fw={700}>{nutritionTrend.avgFat}g</Text></Stack>}
            {nutritionTrend.avgWater !== null && <Stack gap={2} ta="center"><Text fz="xs" c="dimmed">Avg Water</Text><Text fz="lg" fw={700}>{nutritionTrend.avgWater} {nutritionTrend.waterUnit === 'litres' ? 'L' : 'cups'}</Text></Stack>}
            {nutritionTrend.consistencyPct !== null && <Stack gap={2} ta="center"><Text fz="xs" c="dimmed">Consistency</Text><Text fz="lg" fw={700} c={nutritionTrend.consistencyPct >= 80 ? 'green' : nutritionTrend.consistencyPct >= 50 ? 'yellow' : 'red'}>{nutritionTrend.consistencyPct}%</Text></Stack>}
          </SimpleGrid>
        </Paper>
      )}

      <Paper withBorder p="md">
        <Group justify="space-between" mb="sm">
          <Group gap="xs">
            <Brain size={18} />
            <Text fw={500}>Exercise ROI Correlation</Text>
            {correlationReport && (
              <Badge color={correlationReport.cached ? 'blue' : 'green'} variant="light" size="sm">
                {correlationReport.cached ? `Cached ${correlationReport.generated_at ? new Date(correlationReport.generated_at).toLocaleDateString() : ''}` : correlationReport.cache_miss ? 'Not generated' : 'Just generated'}
              </Badge>
            )}
          </Group>
          {analysisWindow.weeks >= 4 && (
            <Button
              variant="subtle"
              size="xs"
              onClick={() => loadCorrelation(true, false)}
              disabled={correlationLoading}
              leftSection={<RefreshCw size={14} style={correlationLoading ? { animation: 'spin 1s linear infinite' } : undefined} />}
            >
              {correlationReport?.cache_miss ? 'Generate' : 'Refresh'}
            </Button>
          )}
        </Group>

        {analysisWindow.weeks < 4 ? (
          <Text size="sm" c="dimmed">Correlation analysis requires at least 4 weeks of data. Select a longer block window.</Text>
        ) : correlationLoading ? (
          <Group gap="xs" py="md">
            <Loader size="xs" />
            <Text size="sm" c="dimmed">Loading block exercise ROI...</Text>
          </Group>
        ) : correlationError ? (
          <Text size="sm" c="red">{correlationError}</Text>
        ) : correlationReport ? (
          <>
            {correlationReport.insufficient_data ? (
              <Text size="sm" c="dimmed">{correlationReport.insufficient_data_reason || 'Insufficient data for meaningful correlation analysis.'}</Text>
            ) : (
              <>
                {correlationReport.summary && (
                  <Text size="sm" c="dimmed" mb="md" p="sm" fs="italic" style={{ background: 'var(--mantine-color-default-hover)', borderRadius: 'var(--mantine-radius-sm)' }}>{correlationReport.summary}</Text>
                )}
                {correlationReport.findings.length > 0 ? (
                  <Box style={{ overflowX: 'auto' }}>
                    <Table fz="sm">
                      <Table.Thead>
                        <Table.Tr>
                          <Table.Th ta="left">Exercise</Table.Th>
                          <Table.Th ta="left">→ Lift</Table.Th>
                          <Table.Th ta="left" w={{ base: 'auto', sm: 100 }}>Direction</Table.Th>
                          <Table.Th ta="left" w={{ base: 'auto', sm: 100 }}>Strength</Table.Th>
                          <Table.Th ta="left" visibleFrom="sm">Reasoning</Table.Th>
                          <Table.Th ta="left" visibleFrom="sm">Caveat</Table.Th>
                        </Table.Tr>
                      </Table.Thead>
                      <Table.Tbody>
                        {correlationReport.findings.map((finding, index) => (
                          <Table.Tr key={index} style={{ verticalAlign: 'top' }}>
                            <Table.Td fw={500}>{finding.exercise}</Table.Td>
                            <Table.Td>{finding.lift}</Table.Td>
                            <Table.Td>
                              <Badge size="xs" variant="light" color={finding.correlation_direction === 'positive' ? 'green' : finding.correlation_direction === 'negative' ? 'red' : 'gray'} style={{ textTransform: 'capitalize' }}>
                                {finding.correlation_direction}
                              </Badge>
                            </Table.Td>
                            <Table.Td>
                              <Badge size="xs" variant="light" color={finding.strength === 'strong' ? 'violet' : finding.strength === 'moderate' ? 'blue' : 'gray'} style={{ textTransform: 'capitalize' }}>
                                {finding.strength}
                              </Badge>
                            </Table.Td>
                            <Table.Td fz="xs" visibleFrom="sm">{finding.reasoning}</Table.Td>
                            <Table.Td c="dimmed" fz="xs" fs="italic" visibleFrom="sm">{finding.caveat}</Table.Td>
                          </Table.Tr>
                        ))}
                      </Table.Tbody>
                    </Table>
                  </Box>
                ) : (
                  <Text size="sm" c="dimmed">No significant anatomically-relevant correlations found in this block.</Text>
                )}
              </>
            )}
          </>
        ) : null}
      </Paper>

      {(program?.meta?.height_cm || program?.meta?.arm_wingspan_cm || program?.meta?.leg_length_cm) && (
        <Paper withBorder p="md">
          <Group gap="xs" mb="sm"><Ruler size={18} /><Text fw={500}>Athlete Measurements</Text></Group>
          <SimpleGrid cols={3} spacing="md">
            {program?.meta.height_cm && <Stack gap={2} ta="center"><Text fz="xs" c="dimmed">Height</Text><Text fz="lg" fw={700}>{program.meta.height_cm} cm</Text></Stack>}
            {program?.meta.arm_wingspan_cm && <Stack gap={2} ta="center"><Text fz="xs" c="dimmed">Arm Wingspan</Text><Text fz="lg" fw={700}>{program.meta.arm_wingspan_cm} cm</Text></Stack>}
            {program?.meta.leg_length_cm && <Stack gap={2} ta="center"><Text fz="xs" c="dimmed">Leg Length</Text><Text fz="lg" fw={700}>{program.meta.leg_length_cm} cm</Text></Stack>}
          </SimpleGrid>
        </Paper>
      )}

      {program?.lift_profiles && program.lift_profiles.length > 0 && (
        <Paper withBorder p="md">
          <Group gap="xs" mb="sm"><Dumbbell size={18} /><Text fw={500}>Lift Style Profiles</Text></Group>
          <SimpleGrid cols={{ base: 1, lg: 3 }}>
            {program.lift_profiles.map((profile) => (
              <Stack key={profile.lift} gap="xs" p="sm" style={{ borderRadius: 'var(--mantine-radius-sm)', background: 'var(--mantine-color-default-hover)' }}>
                <Text fw={500} fz="sm" tt="capitalize" pb="xs" style={{ borderBottom: '1px solid var(--mantine-color-default-border)' }}>{profile.lift}</Text>
                <Badge color={profile.volume_tolerance === 'low' ? 'red' : profile.volume_tolerance === 'moderate' ? 'yellow' : 'green'} variant="light" tt="capitalize">{profile.volume_tolerance} volume tolerance</Badge>
              </Stack>
            ))}
          </SimpleGrid>
        </Paper>
      )}

      <WeeklyData
        data={bundle.weekly as WeeklyAnalysis}
        viewMode={viewMode}
        perLiftDetails={perLiftDetails}
        muscleGroupAvgWeekly={muscleGroupAvgWeekly}
        analysisWeeks={analysisWindow.weeks}
        unit={unit}
      />
    </Stack>
  )
}
