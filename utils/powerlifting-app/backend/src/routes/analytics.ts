import { Router } from 'express'
import { invokeToolDirect } from '../utils/agent'
import * as programController from '../controllers/programController'
import * as weightController from '../controllers/weightController'
import type { Program, WeightEntry } from '@powerlifting/types'
import {
  analysisSourceFingerprint,
  buildAnalysisWindows,
  getCachedWeeklyAnalysisBundle,
  isIsoDate,
  makeWeeklyAnalysisBundle,
  putCachedWeeklyAnalysisBundle,
  type AnalysisWindowKey,
} from '../services/analysisCache'
import {
  analysisScopedBlockEntry,
  buildBlockComparison,
  buildBlockComparisonContext,
  buildCurrentProgramBlockIndex,
  getCachedBlockAnalysisBundle,
  getOrCreateAiBlockComparison,
  getOrCreateBlockAnalysisBundle,
  getOrCreateBlockCorrelationReport,
  getOrCreateBlockProgramEvaluation,
} from '../services/blockAnalytics'

export const analyticsRouter = Router()

type ProgramWithWeightLog = Program & { weight_log: WeightEntry[] }

const WINDOW_KEYS: AnalysisWindowKey[] = [
  'current',
  'previous_1',
  'previous_2',
  'previous_4',
  'previous_8',
  'block',
]

function todayIso(): string {
  return new Date().toISOString().slice(0, 10)
}

async function getProgramWithWeightLog(pk: string, version = 'current'): Promise<ProgramWithWeightLog> {
  const program = await programController.getProgram(pk, version)
  try {
    const log = await weightController.getWeightLog(pk, version)
    return {
      ...program,
      weight_log: Array.isArray(log.entries) ? log.entries : [],
    }
  } catch (error) {
    console.warn('Failed to load weight log for analytics context:', error)
    return { ...program, weight_log: [] }
  }
}

async function snapshotCompetitionProjection(pk: string, date: string): Promise<void> {
  try {
    await invokeToolDirect('health_snapshot_competition_projection', {
      date,
      version: 'current',
      allow_retrospective: false,
      pk,
    })
  } catch (snapshotErr) {
    console.warn('Failed to snapshot competition projections before weekly analysis:', snapshotErr)
  }
}

// GET /api/analytics/analysis/weekly-bundle?asOfDate=YYYY-MM-DD
analyticsRouter.get('/analysis/weekly-bundle', async (req, res) => {
  try {
    const pk = req.effectivePk!
    const requestedAsOfDate = req.query.asOfDate as string | undefined
    const asOfDate = isIsoDate(requestedAsOfDate) ? requestedAsOfDate : todayIso()
    let program = await getProgramWithWeightLog(pk, 'current')
    let sourceFingerprint = analysisSourceFingerprint(program)

    const cached = await getCachedWeeklyAnalysisBundle(pk, asOfDate, sourceFingerprint)
    if (cached) {
      return res.json({ data: cached, error: null })
    }

    await snapshotCompetitionProjection(pk, asOfDate)
    program = await getProgramWithWeightLog(pk, 'current')
    sourceFingerprint = analysisSourceFingerprint(program)

    const windows = buildAnalysisWindows(program, asOfDate)
    const sessions = program.sessions ?? []

    const results = {} as Record<AnalysisWindowKey, unknown>
    for (const key of WINDOW_KEYS) {
      const window = windows[key]
      results[key] = await invokeToolDirect('weekly_analysis', {
        weeks: window.weeks,
        block: 'current',
        window_start: window.start,
        window_end: window.end,
        ref_date: window.end,
        week_start: window.weekStart,
        week_end: window.weekEnd,
        refresh_program: false,
        program,
        sessions,
        pk,
      })
    }

    const bundle = makeWeeklyAnalysisBundle(asOfDate, windows, results, sourceFingerprint)
    await putCachedWeeklyAnalysisBundle(pk, bundle)
    res.json({ data: bundle, error: null })
  } catch (err) {
    res.status(502).json({ data: null, error: `Tool invocation error: ${err}` })
  }
})

// GET /api/analytics/analysis/weekly?weeks=N&block=X
analyticsRouter.get('/analysis/weekly', async (req, res) => {
  try {
    const weeks = parseInt(req.query.weeks as string) || 1
    const block = (req.query.block as string) || 'current'
    const windowStart = (req.query.windowStart as string) || undefined
    const windowEnd = (req.query.windowEnd as string) || undefined
    const refDate = (req.query.refDate as string) || undefined
    const weekStartRaw = parseInt(req.query.weekStart as string)
    const weekEndRaw = parseInt(req.query.weekEnd as string)
    const weekStart = Number.isFinite(weekStartRaw) && weekStartRaw > 0 ? weekStartRaw : undefined
    const weekEnd = Number.isFinite(weekEndRaw) && weekEndRaw > 0 ? weekEndRaw : undefined
    const today = todayIso()
    await snapshotCompetitionProjection(req.effectivePk!, today)
    const program = await getProgramWithWeightLog(req.effectivePk!, 'current')
    const data = await invokeToolDirect('weekly_analysis', {
      weeks,
      block,
      window_start: windowStart,
      window_end: windowEnd,
      ref_date: refDate,
      week_start: weekStart,
      week_end: weekEnd,
      refresh_program: false,
      program,
      sessions: program.sessions ?? [],
      pk: req.effectivePk,
    })
    res.json({ data, error: null })
  } catch (err) {
    res.status(502).json({ data: null, error: `Tool invocation error: ${err}` })
  }
})

// GET /api/analytics/blocks
analyticsRouter.get('/blocks', async (req, res) => {
  try {
    const program = await getProgramWithWeightLog(req.effectivePk!, 'current')
    const blocks = await buildCurrentProgramBlockIndex(req.effectivePk!, program)
    res.json({ data: blocks, error: null })
  } catch (err) {
    res.status(502).json({ data: null, error: `Block analytics error: ${err}` })
  }
})

// GET /api/analytics/blocks/:blockKey/analysis?refresh=false
analyticsRouter.get('/blocks/:blockKey/analysis', async (req, res) => {
  try {
    const program = await getProgramWithWeightLog(req.effectivePk!, 'current')
    const refresh = req.query.refresh === 'true'
    const cacheOnly = req.query.cacheOnly === 'true'
    const bundle = await getOrCreateBlockAnalysisBundle(
      req.effectivePk!,
      program,
      req.params.blockKey,
      invokeToolDirect,
      refresh,
      cacheOnly,
    )
    if (!bundle) {
      return res.status(404).json({ data: null, error: `Block ${req.params.blockKey} not found` })
    }
    res.json({ data: bundle, error: null })
  } catch (err) {
    res.status(502).json({ data: null, error: `Block analysis error: ${err}` })
  }
})

// GET /api/analytics/blocks/:blockKey/program-evaluation?refresh=false
analyticsRouter.get('/blocks/:blockKey/program-evaluation', async (req, res) => {
  try {
    const program = await getProgramWithWeightLog(req.effectivePk!, 'current')
    const refresh = req.query.refresh === 'true'
    const cacheOnly = req.query.cacheOnly === 'true'
    const report = await getOrCreateBlockProgramEvaluation(
      req.effectivePk!,
      program,
      req.params.blockKey,
      invokeToolDirect,
      refresh,
      cacheOnly,
    )
    if (!report) {
      return res.status(404).json({ data: null, error: `Block ${req.params.blockKey} not found` })
    }
    res.json({ data: report, error: null })
  } catch (err) {
    res.status(502).json({ data: null, error: `Block program evaluation error: ${err}` })
  }
})

// PUT /api/analytics/blocks/:blockKey/start-maxes
analyticsRouter.put('/blocks/:blockKey/start-maxes', async (req, res) => {
  try {
    const program = await getProgramWithWeightLog(req.effectivePk!, 'current')
    const blocks = await buildCurrentProgramBlockIndex(req.effectivePk!, program)
    const block = blocks.find((entry) => entry.blockKey === req.params.blockKey)
    if (!block) {
      return res.status(404).json({ data: null, error: `Block ${req.params.blockKey} not found` })
    }

    const parseKg = (value: unknown): number | null => {
      if (value === null || value === undefined || value === '') return null
      const numberValue = Number(value)
      if (!Number.isFinite(numberValue) || numberValue < 0) {
        throw new Error('Start maxes must be positive kg values or null')
      }
      return Math.round(numberValue * 10) / 10
    }

    const squat = parseKg(req.body?.squat_kg)
    const bench = parseKg(req.body?.bench_kg)
    const deadlift = parseKg(req.body?.deadlift_kg)
    const total = squat != null && bench != null && deadlift != null
      ? Math.round((squat + bench + deadlift) * 10) / 10
      : null
    const startMaxes = {
      squat_kg: squat,
      bench_kg: bench,
      deadlift_kg: deadlift,
      total_kg: total,
      source: 'manual' as const,
      updated_at: new Date().toISOString(),
    }

    const currentStartMaxes = (program.meta as { block_start_maxes?: Record<string, unknown> }).block_start_maxes || {}
    await programController.updateMetaField(
      req.effectivePk!,
      'current',
      'block_start_maxes',
      {
        ...currentStartMaxes,
        [block.blockKey]: startMaxes,
      },
    )

    res.json({ data: startMaxes, error: null })
  } catch (err) {
    res.status(400).json({ data: null, error: `Block start max update error: ${err}` })
  }
})

// GET /api/analytics/blocks/:blockKey/correlation
analyticsRouter.get('/blocks/:blockKey/correlation', async (req, res) => {
  try {
    const program = await getProgramWithWeightLog(req.effectivePk!, 'current')
    const refresh = req.query.refresh === 'true'
    const cacheOnly = req.query.cacheOnly === 'true'
    const data = await getOrCreateBlockCorrelationReport(
      req.effectivePk!,
      program,
      req.params.blockKey,
      invokeToolDirect,
      refresh,
      cacheOnly,
    )
    if (!data) {
      return res.status(404).json({ data: null, error: `Block ${req.params.blockKey} not found` })
    }
    res.json({ data, error: null })
  } catch (err) {
    res.status(502).json({ data: null, error: `Block correlation error: ${err}` })
  }
})

// POST /api/analytics/block-comparison
analyticsRouter.post('/block-comparison', async (req, res) => {
  try {
    const program = await getProgramWithWeightLog(req.effectivePk!, 'current')
    const blocks = await buildCurrentProgramBlockIndex(req.effectivePk!, program)
    const requestedKeys = Array.isArray(req.body?.blockKeys)
      ? req.body.blockKeys.filter((key: unknown): key is string => typeof key === 'string')
      : []

    const defaultKeys = blocks.filter((block) => !block.isCurrent).map((block) => block.blockKey)
    const selected = new Set(requestedKeys.length ? requestedKeys : defaultKeys)
    const current = blocks.find((block) => block.isCurrent)
    if (current) selected.add(current.blockKey)

    const selectedBlocks = blocks.filter((block) => selected.has(block.blockKey))
    const cacheOnly = req.body?.cacheOnly === true
    const bundles = []
    const correlationReports = new Map<string, Record<string, unknown> | null>()
    const contexts = new Map()
    for (const rawBlock of selectedBlocks) {
      const block = analysisScopedBlockEntry(program, rawBlock)
      contexts.set(block.blockKey, buildBlockComparisonContext(program, rawBlock))
      const bundle = cacheOnly
        ? await getCachedBlockAnalysisBundle(
            req.effectivePk!,
            block.blockKey,
            block.sourceFingerprint,
            { allowStale: !block.isCurrent },
          )
        : await getOrCreateBlockAnalysisBundle(
            req.effectivePk!,
            program,
            block.blockKey,
            invokeToolDirect,
            false,
          )
      if (bundle) bundles.push(bundle)
      correlationReports.set(block.blockKey, await getOrCreateBlockCorrelationReport(
        req.effectivePk!,
        program,
        block.blockKey,
        invokeToolDirect,
        false,
        true,
      ))
    }

    res.json({ data: buildBlockComparison(bundles, correlationReports, contexts), error: null })
  } catch (err) {
    res.status(502).json({ data: null, error: `Block comparison error: ${err}` })
  }
})

// POST /api/analytics/block-comparison/ai
analyticsRouter.post('/block-comparison/ai', async (req, res) => {
  try {
    const program = await getProgramWithWeightLog(req.effectivePk!, 'current')
    const blocks = await buildCurrentProgramBlockIndex(req.effectivePk!, program)
    const requestedKeys = Array.isArray(req.body?.blockKeys)
      ? req.body.blockKeys.filter((key: unknown): key is string => typeof key === 'string')
      : []
    const defaultKeys = blocks.filter((block) => !block.isCurrent).map((block) => block.blockKey)
    const selected = new Set(requestedKeys.length ? requestedKeys : defaultKeys)
    const current = blocks.find((block) => block.isCurrent)
    if (current) selected.add(current.blockKey)

    const selectedBlocks = blocks.filter((block) => selected.has(block.blockKey))
    const cacheOnly = req.body?.cacheOnly === true
    const bundles = []
    const correlationReports = new Map<string, Record<string, unknown> | null>()
    const programEvaluationReports = new Map<string, Record<string, unknown> | null>()
    const contexts = new Map()
    for (const rawBlock of selectedBlocks) {
      const block = analysisScopedBlockEntry(program, rawBlock)
      contexts.set(block.blockKey, buildBlockComparisonContext(program, rawBlock))
      const bundle = await getCachedBlockAnalysisBundle(
        req.effectivePk!,
        block.blockKey,
        block.sourceFingerprint,
        { allowStale: !block.isCurrent },
      )
      if (bundle) bundles.push(bundle)
      if (bundle) {
        correlationReports.set(block.blockKey, await getOrCreateBlockCorrelationReport(
          req.effectivePk!,
          program,
          block.blockKey,
          invokeToolDirect,
          false,
          true,
        ))
        programEvaluationReports.set(block.blockKey, await getOrCreateBlockProgramEvaluation(
          req.effectivePk!,
          program,
          block.blockKey,
          invokeToolDirect,
          false,
          true,
        ))
      }
    }

    const comparison = await getOrCreateAiBlockComparison(
      req.effectivePk!,
      bundles,
      invokeToolDirect,
      req.body?.refresh === true,
      cacheOnly,
      correlationReports,
      programEvaluationReports,
      contexts,
    )
    res.json({ data: comparison, error: null })
  } catch (err) {
    res.status(502).json({ data: null, error: `AI block comparison error: ${err}` })
  }
})

// GET /api/analytics/correlation?weeks=N&block=X&refresh=bool
analyticsRouter.get('/correlation', async (req, res) => {
  try {
    const weeks = parseInt(req.query.weeks as string) || 4
    const block = (req.query.block as string) || 'current'
    const refresh = req.query.refresh === 'true'
    const cacheOnly = req.query.cacheOnly === 'true'
    const data = await invokeToolDirect('correlation_analysis', { weeks, block, refresh, cache_only: cacheOnly, pk: req.effectivePk })
    res.json({ data, error: null })
  } catch (err) {
    res.status(502).json({ data: null, error: `Tool invocation error: ${err}` })
  }
})

// POST /api/analytics/fatigue-profile/estimate
analyticsRouter.post('/fatigue-profile/estimate', async (req, res) => {
  try {
    const exercise = req.body?.exercise ?? req.body
    const data = await invokeToolDirect('fatigue_profile_estimate', { exercise, pk: req.effectivePk })
    res.json({ data, error: null })
  } catch (err) {
    res.status(502).json({ data: null, error: `Tool invocation error: ${err}` })
  }
})

// POST /api/analytics/muscle-groups/estimate
analyticsRouter.post('/muscle-groups/estimate', async (req, res) => {
  try {
    const body = req.body ?? {}
    const exercise = body.exercise ?? body
    const lift_profiles = Array.isArray(body.lift_profiles) ? body.lift_profiles : undefined
    const data = await invokeToolDirect('muscle_group_estimate', {
      exercise,
      ...(lift_profiles ? { lift_profiles } : {}),
      pk: req.effectivePk,
    })
    res.json({ data, error: null })
  } catch (err) {
    res.status(502).json({ data: null, error: `Tool invocation error: ${err}` })
  }
})

// POST /api/analytics/lift-profile/review
analyticsRouter.post('/lift-profile/review', async (req, res) => {
  try {
    const profile = req.body?.profile ?? req.body
    const data = await invokeToolDirect('lift_profile_review', { profile, pk: req.effectivePk })
    res.json({ data, error: null })
  } catch (err) {
    res.status(502).json({ data: null, error: `Tool invocation error: ${err}` })
  }
})

// POST /api/analytics/lift-profile/rewrite
analyticsRouter.post('/lift-profile/rewrite', async (req, res) => {
  try {
    const profile = req.body?.profile ?? req.body
    const data = await invokeToolDirect('lift_profile_rewrite', { profile, pk: req.effectivePk })
    res.json({ data, error: null })
  } catch (err) {
    res.status(502).json({ data: null, error: `Tool invocation error: ${err}` })
  }
})

// POST /api/analytics/lift-profile/estimate-stimulus
analyticsRouter.post('/lift-profile/estimate-stimulus', async (req, res) => {
  try {
    const profile = req.body?.profile ?? req.body
    const data = await invokeToolDirect('lift_profile_estimate_stimulus', { profile, pk: req.effectivePk })
    res.json({ data, error: null })
  } catch (err) {
    res.status(502).json({ data: null, error: `Tool invocation error: ${err}` })
  }
})

// POST /api/analytics/lift-profile/rewrite-and-estimate
analyticsRouter.post('/lift-profile/rewrite-and-estimate', async (req, res) => {
  try {
    const profile = req.body?.profile ?? req.body
    const data = await invokeToolDirect('lift_profile_rewrite_and_estimate', { profile, pk: req.effectivePk })
    res.json({ data, error: null })
  } catch (err) {
    res.status(502).json({ data: null, error: `Tool invocation error: ${err}` })
  }
})

// GET /api/analytics/program-evaluation?refresh=bool
analyticsRouter.get('/program-evaluation', async (req, res) => {
  try {
    const refresh = req.query.refresh === 'true'
    const cacheOnly = req.query.cacheOnly === 'true'
    const data = await invokeToolDirect('program_evaluation', { refresh, cache_only: cacheOnly, pk: req.effectivePk })
    res.json({ data, error: null })
  } catch (err) {
    res.status(502).json({ data: null, error: `Tool invocation error: ${err}` })
  }
})
