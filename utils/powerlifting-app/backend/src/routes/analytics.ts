import { Router } from 'express'
import { invokeToolDirect } from '../utils/agent'
import * as programController from '../controllers/programController'
import * as weightController from '../controllers/weightController'
import type { Program, WeightEntry } from '@powerlifting/types'
import {
  ALL_WINDOW_KEYS,
  CORRELATION_WINDOW_KEYS,
  buildAnalysisWindows,
  getCachedAllWindowAnalyses,
  putAllCachedWindowAnalyses,
  getCachedMarkdownExport,
  putCachedMarkdownExport,
  isIsoDate,
  makeWeeklyAnalysisBundle,
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

/**
 * Core regeneration function: computes all 6 analysis windows, their AI reports,
 * and the markdown export, then stores everything in the current-block cache.
 * Also regenerates block_analysis#v1#current, block_correlation#v1#current, and
 * block_program_eval#v1#current so the Dashboard and Lifetime Compare exerciseRoi
 * section stay in sync after regeneration.
 * NEVER touches past-block or lifetime-compare (AI comparison) caches.
 */
async function runFullCurrentBlockRegeneration(
  pk: string,
  asOfDate: string,
): Promise<{ generatedAt: string; windows: ReturnType<typeof buildAnalysisWindows> }> {
  await snapshotCompetitionProjection(pk, asOfDate)
  const program = await getProgramWithWeightLog(pk, 'current')

  const windows = buildAnalysisWindows(program, asOfDate)
  const sessions = program.sessions ?? []

  // Compute all 6 deterministic windows in parallel
  const windowResults = await Promise.all(
    ALL_WINDOW_KEYS.map(async (key) => {
      const window = windows[key]
      const result = await invokeToolDirect('weekly_analysis', {
        weeks: window.weeks,
        block: 'current',
        window_start: window.start,
        window_end: window.end,
        ref_date: asOfDate,
        week_start: window.weekStart,
        week_end: window.weekEnd,
        refresh_program: false,
        program,
        sessions,
        pk,
      })
      return { key, result }
    }),
  )

  const results = {} as Record<AnalysisWindowKey, unknown>
  for (const { key, result } of windowResults) {
    results[key] = result
  }

  // Store window results
  await putAllCachedWindowAnalyses(pk, results)

  // Compute AI correlation for applicable windows (4w, 8w, full block) in parallel
  await Promise.all(
    CORRELATION_WINDOW_KEYS.map(async (key) => {
      try {
        await invokeToolDirect('correlation_analysis', {
          weeks: windows[key].weeks,
          block: 'current',
          refresh: true,
          cache_only: false,
          pk,
        })
      } catch (err) {
        console.warn(`Correlation analysis failed for window ${key}:`, err)
      }
    }),
  )

  // Compute full-block program evaluation
  try {
    await invokeToolDirect('program_evaluation', { refresh: true, cache_only: false, pk })
  } catch (err) {
    console.warn('Program evaluation failed during regeneration:', err)
  }

  // Regenerate block_analysis#v1#current (Dashboard reads this — not weekly_analysis#*)
  // Regenerate block_correlation#v1#current (Lifetime Compare exerciseRoi reads this)
  // Regenerate block_program_eval#v1#current (Lifetime Compare per-block eval reads this)
  // These three run in parallel — they write to independent DynamoDB SKs.
  const [blockBundleResult, blockCorrResult, blockEvalResult] = await Promise.allSettled([
    getOrCreateBlockAnalysisBundle(pk, program, 'current', invokeToolDirect, true, false),
    getOrCreateBlockCorrelationReport(pk, program, 'current', invokeToolDirect, true, false),
    getOrCreateBlockProgramEvaluation(pk, program, 'current', invokeToolDirect, true, false),
  ])
  if (blockBundleResult.status === 'rejected') {
    console.warn('block_analysis#v1#current regeneration failed:', blockBundleResult.reason)
  }
  if (blockCorrResult.status === 'rejected') {
    console.warn('block_correlation#v1#current regeneration failed:', blockCorrResult.reason)
  }
  if (blockEvalResult.status === 'rejected') {
    console.warn('block_program_eval#v1#current regeneration failed:', blockEvalResult.reason)
  }

  // Generate and cache markdown export (uses the full-block analysis as context)
  try {
    const markdownResult = await invokeToolDirect('export_program_markdown', {
      version: 'current',
      include_analysis: true,
      analysis_weeks: windows.block.weeks,
      pk,
    }) as { markdown?: string; content?: string } | null
    const markdown = markdownResult?.markdown ?? markdownResult?.content ?? ''
    if (markdown) {
      await putCachedMarkdownExport(pk, markdown, 'current')
    }
  } catch (err) {
    console.warn('Markdown export failed during regeneration:', err)
  }

  const generatedAt = new Date().toISOString()
  return { generatedAt, windows }
}

// POST /api/analytics/e1rm-multiplier/suggestions
analyticsRouter.post('/e1rm-multiplier/suggestions', async (req, res) => {
  try {
    const result = await invokeToolDirect('health_suggest_e1rm_multipliers', {})
    res.json({ data: result })
  } catch (error) {
    res.status(500).json({ error: String(error) })
  }
})

// GET /api/analytics/analysis/weekly-bundle?asOfDate=YYYY-MM-DD
// Returns all 6 window analyses from cache. On any miss, regenerates all windows first.
analyticsRouter.get('/analysis/weekly-bundle', async (req, res) => {
  try {
    const pk = req.effectivePk!
    const requestedAsOfDate = req.query.asOfDate as string | undefined
    const asOfDate = isIsoDate(requestedAsOfDate) ? requestedAsOfDate : todayIso()

    // Check if all 6 windows are cached
    const cached = await getCachedAllWindowAnalyses(pk)
    if (cached) {
      const program = await getProgramWithWeightLog(pk, 'current')
      const windows = buildAnalysisWindows(program, asOfDate)
      const bundle = makeWeeklyAnalysisBundle(asOfDate, windows, cached.results)
      return res.json({ data: { ...bundle, cached: true, generatedAt: cached.generatedAt }, error: null })
    }

    // Cache miss — regenerate everything
    const { generatedAt, windows } = await runFullCurrentBlockRegeneration(pk, asOfDate)
    const fresh = await getCachedAllWindowAnalyses(pk)
    if (!fresh) {
      return res.status(502).json({ data: null, error: 'Analysis generation failed: cache write error' })
    }
    const bundle = makeWeeklyAnalysisBundle(asOfDate, windows, fresh.results)
    return res.json({ data: { ...bundle, cached: false, generatedAt }, error: null })
  } catch (err) {
    res.status(502).json({ data: null, error: `Analysis error: ${err}` })
  }
})

// POST /api/analytics/analysis/regenerate
// Force-regenerates all current-block window analyses + AI reports + markdown.
// NEVER touches past-block or lifetime-compare caches.
analyticsRouter.post('/analysis/regenerate', async (req, res) => {
  try {
    const pk = req.effectivePk!
    const asOfDate = todayIso()
    const { generatedAt } = await runFullCurrentBlockRegeneration(pk, asOfDate)
    res.json({ data: { success: true, generatedAt, windowsRegenerated: ALL_WINDOW_KEYS.length }, error: null })
  } catch (err) {
    res.status(502).json({ data: null, error: `Regeneration error: ${err}` })
  }
})

// GET /api/analytics/analysis/markdown
// Returns cached markdown export for current block (used by powerlifting coach).
// If not cached, generates and caches before returning.
analyticsRouter.get('/analysis/markdown', async (req, res) => {
  try {
    const pk = req.effectivePk!

    const cached = await getCachedMarkdownExport(pk)
    if (cached) {
      return res.json({ data: { markdown: cached.markdown, generatedAt: cached.generatedAt, cached: true }, error: null })
    }

    // Generate on the fly (no full analysis context — just program state)
    const markdownResult = await invokeToolDirect('export_program_markdown', {
      version: 'current',
      include_analysis: false,
      pk,
    }) as { markdown?: string; content?: string } | null
    const markdown = markdownResult?.markdown ?? markdownResult?.content ?? ''
    if (!markdown) {
      return res.status(502).json({ data: null, error: 'Markdown export returned empty content' })
    }
    const generatedAt = new Date().toISOString()
    await putCachedMarkdownExport(pk, markdown, 'current')
    return res.json({ data: { markdown, generatedAt, cached: false }, error: null })
  } catch (err) {
    res.status(502).json({ data: null, error: `Markdown export error: ${err}` })
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
    const projectionDate = isIsoDate(refDate) ? refDate : todayIso()
    await snapshotCompetitionProjection(req.effectivePk!, projectionDate)
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

// POST /api/analytics/blocks/:blockKey/regenerate
// Portal-only: force-regenerates a specific past-block analysis, correlation, and program eval.
analyticsRouter.post('/blocks/:blockKey/regenerate', async (req, res) => {
  try {
    const pk = req.effectivePk!
    const { blockKey } = req.params
    const program = await getProgramWithWeightLog(pk, 'current')

    const [bundle, corrReport, evalReport] = await Promise.allSettled([
      getOrCreateBlockAnalysisBundle(pk, program, blockKey, invokeToolDirect, true, false),
      getOrCreateBlockCorrelationReport(pk, program, blockKey, invokeToolDirect, true, false),
      getOrCreateBlockProgramEvaluation(pk, program, blockKey, invokeToolDirect, true, false),
    ])

    if (bundle.status === 'rejected' || !('value' in bundle) || !bundle.value) {
      return res.status(404).json({ data: null, error: `Block ${blockKey} not found or regeneration failed` })
    }

    // Generate and cache block markdown
    try {
      const markdownResult = await invokeToolDirect('export_program_markdown', {
        version: 'current',
        include_analysis: false,
        pk,
      }) as { markdown?: string; content?: string } | null
      const markdown = markdownResult?.markdown ?? markdownResult?.content ?? ''
      if (markdown) {
        await putCachedMarkdownExport(pk, markdown, blockKey)
      }
    } catch (mdErr) {
      console.warn('Markdown export failed for block regeneration:', mdErr)
    }

    res.json({
      data: {
        success: true,
        blockKey,
        generatedAt: new Date().toISOString(),
        correlationRegenerated: corrReport.status === 'fulfilled',
        evaluationRegenerated: evalReport.status === 'fulfilled',
      },
      error: null,
    })
  } catch (err) {
    res.status(502).json({ data: null, error: `Block regeneration error: ${err}` })
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
        ? await getCachedBlockAnalysisBundle(req.effectivePk!, block.blockKey)
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
// Lifetime compare — strictly on-demand. Never regenerated by /analysis/regenerate.
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
      // Always read from cache for lifetime compare — never regenerates block analyses
      const bundle = await getCachedBlockAnalysisBundle(req.effectivePk!, block.blockKey)
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
