import { Router } from 'express'
import { invokeToolDirect } from '../utils/agent'
import { logger } from '../utils/logger'
import * as programController from '../controllers/programController'
import * as weightController from '../controllers/weightController'
import type { Program, WeightEntry } from '@powerlifting/types'
import {
  ALL_WINDOW_KEYS,
  CORRELATION_WINDOW_KEYS,
  buildAnalysisWindows,
  putAllCachedWindowAnalyses,
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
  getCachedBlockCorrelationReport,
  getCachedBlockProgramEvaluationReport,
  getOrCreateAiBlockComparison,
  getOrCreateBlockAnalysisBundle,
  getOrCreateBlockCorrelationReport,
  getOrCreateBlockProgramEvaluation,
} from '../services/blockAnalytics'
import {
  blockAnalysisExportContentType,
  blockAnalysisExportFilename,
  buildBlockAnalysisMarkdownExport,
  buildBlockAnalysisWorkbookExport,
} from '../services/blockAnalysisExport'

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
    logger.warn({ error, pk }, 'Failed to load weight log for analytics context')
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
    logger.warn({ err: snapshotErr, pk, date }, 'Failed to snapshot competition projections before weekly analysis')
  }
}

async function runTargetedRegeneration(
  pk: string,
  asOfDate: string,
  targetWindows?: AnalysisWindowKey[],
): Promise<{ generatedAt: string; windows: ReturnType<typeof buildAnalysisWindows> }> {
  const program = await getProgramWithWeightLog(pk, 'current')
  const windows = buildAnalysisWindows(program, asOfDate)
  const sessions = program.sessions ?? []
  const keys = targetWindows ?? ALL_WINDOW_KEYS
  const needCorrelation = keys.some((k) => CORRELATION_WINDOW_KEYS.includes(k))

  const results = {} as Record<AnalysisWindowKey, unknown>
  for (const key of keys) {
    const window = windows[key]
    logger.info({ pk, window: key, weeks: window.weeks }, 'Computing weekly analysis window')
    results[key] = await invokeToolDirect('weekly_analysis', {
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
  }

  await putAllCachedWindowAnalyses(pk, results)

  for (const key of keys.filter((k) => CORRELATION_WINDOW_KEYS.includes(k))) {
    try {
      await invokeToolDirect('correlation_analysis', {
        weeks: windows[key].weeks,
        block: 'current',
        refresh: true,
        cache_only: false,
        pk,
      })
    } catch (err) {
      logger.warn({ err, pk, window: key }, 'Correlation analysis failed for window')
    }
  }

  if (needCorrelation) {
    try {
      await getOrCreateBlockCorrelationReport(pk, program, 'current', invokeToolDirect, true, false)
    } catch (err) {
      logger.warn({ err, pk }, 'block_correlation#v1#current regeneration failed')
    }
  }

  try {
    await getOrCreateBlockAnalysisBundle(pk, program, 'current', invokeToolDirect, true, false)
  } catch (err) {
    logger.warn({ err, pk }, 'block_analysis#v1#current regeneration failed')
  }

  const generatedAt = new Date().toISOString()
  logger.info({ pk, generatedAt, windows: keys }, 'Targeted regeneration complete')
  return { generatedAt, windows }
}

async function runFullCurrentBlockRegeneration(
  pk: string,
  asOfDate: string,
): Promise<{ generatedAt: string; windows: ReturnType<typeof buildAnalysisWindows> }> {
  await snapshotCompetitionProjection(pk, asOfDate)
  const program = await getProgramWithWeightLog(pk, 'current')
  const { generatedAt, windows } = await runTargetedRegeneration(pk, asOfDate)

  try {
    await invokeToolDirect('program_evaluation', { refresh: true, cache_only: false, pk })
  } catch (err) {
    logger.warn({ err, pk }, 'Program evaluation failed during regeneration')
  }

  try {
    await getOrCreateBlockProgramEvaluation(pk, program, 'current', invokeToolDirect, true, false)
  } catch (err) {
    logger.warn({ err, pk }, 'block_program_eval#v1#current regeneration failed')
  }

  try {
    const markdownResult = await invokeToolDirect('export_program_markdown', {
      version: 'current',
      include_analysis: true,
      analysis_weeks: windows.block.weeks,
      pk,
    }) as { markdown?: string; content?: string } | null
    const markdown = markdownResult?.markdown ?? markdownResult?.content ?? ''
    if (markdown) {
      const { putCachedMarkdownExport } = await import('../services/analysisCache')
      await putCachedMarkdownExport(pk, markdown, 'current')
    }
  } catch (err) {
    logger.warn({ err, pk }, 'Markdown export failed during regeneration')
  }

  logger.info({ pk, generatedAt }, 'Full current block regeneration complete')
  return { generatedAt, windows }
}

analyticsRouter.post('/e1rm-multiplier/suggestions', async (req, res) => {
  try {
    const result = await invokeToolDirect('health_suggest_e1rm_multipliers', {})
    res.json({ data: result })
  } catch (error) {
    res.status(500).json({ error: String(error) })
  }
})

analyticsRouter.get('/analysis/weekly-bundle', async (req, res) => {
  try {
    const pk = req.mapped_pk!
    const requestedAsOfDate = req.query.asOfDate as string | undefined
    const asOfDate = isIsoDate(requestedAsOfDate) ? requestedAsOfDate : todayIso()
    const forceRefresh = req.query.refresh === 'true'

    if (!forceRefresh) {
      const cached = await import('../services/analysisCache').then(m => m.getCachedAllWindowAnalyses(pk))
      if (cached) {
        const program = await getProgramWithWeightLog(pk, 'current')
        const windows = buildAnalysisWindows(program, asOfDate)
        const bundle = makeWeeklyAnalysisBundle(asOfDate, windows, cached.results)
        return res.json({ data: { ...bundle, cached: true, generatedAt: cached.generatedAt }, error: null })
      }
    }

    logger.info({ pk, asOfDate, forceRefresh }, 'Computing weekly bundle')
    const { generatedAt, windows } = await runFullCurrentBlockRegeneration(pk, asOfDate)
    const fresh = await import('../services/analysisCache').then(m => m.getCachedAllWindowAnalyses(pk))
    if (fresh) {
      const bundle = makeWeeklyAnalysisBundle(asOfDate, windows, fresh.results)
      return res.json({ data: { ...bundle, cached: false, generatedAt }, error: null })
    }
    return res.status(502).json({ data: null, error: 'Analysis generation failed: cache write error' })
  } catch (err) {
    logger.error({ err }, 'Weekly bundle computation failed')
    res.status(502).json({ data: null, error: `Analysis error: ${err}` })
  }
})

analyticsRouter.post('/analysis/regenerate', async (req, res) => {
  try {
    const pk = req.mapped_pk!
    const asOfDate = todayIso()
    const requestedWindows = req.body?.windows
    if (Array.isArray(requestedWindows) && requestedWindows.length > 0) {
      const valid = requestedWindows.filter((w: string) => ALL_WINDOW_KEYS.includes(w as AnalysisWindowKey)) as AnalysisWindowKey[]
      const { generatedAt } = await runTargetedRegeneration(pk, asOfDate, valid)
      return res.json({ data: { success: true, generatedAt, windowsRegenerated: valid.length }, error: null })
    }
    const { generatedAt } = await runFullCurrentBlockRegeneration(pk, asOfDate)
    res.json({ data: { success: true, generatedAt, windowsRegenerated: ALL_WINDOW_KEYS.length }, error: null })
  } catch (err) {
    res.status(502).json({ data: null, error: `Regeneration error: ${err}` })
  }
})

analyticsRouter.get('/analysis/markdown', async (req, res) => {
  try {
    const pk = req.mapped_pk!

    const markdownResult = await invokeToolDirect('get_analysis_markdown', {
      pk,
    }) as { markdown?: string; generated_at?: string; cached?: boolean } | null

    const markdown = markdownResult?.markdown ?? ''
    if (!markdown) {
      return res.status(502).json({ data: null, error: 'Markdown export returned empty content' })
    }
    
    return res.json({ 
      data: { 
        markdown, 
        generatedAt: markdownResult?.generated_at ?? new Date().toISOString(), 
        cached: markdownResult?.cached ?? false 
      }, 
      error: null 
    })
  } catch (err) {
    res.status(502).json({ data: null, error: `Markdown export error: ${err}` })
  }
})

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
    await snapshotCompetitionProjection(req.mapped_pk!, projectionDate)
    const program = await getProgramWithWeightLog(req.mapped_pk!, 'current')
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
      pk: req.mapped_pk,
    })
    res.json({ data, error: null })
  } catch (err) {
    res.status(502).json({ data: null, error: `Tool invocation error: ${err}` })
  }
})

analyticsRouter.get('/blocks', async (req, res) => {
  try {
    const program = await getProgramWithWeightLog(req.mapped_pk!, 'current')
    const blocks = await buildCurrentProgramBlockIndex(req.mapped_pk!, program)
    res.json({ data: blocks, error: null })
  } catch (err: any) {
    if (err?.statusCode === 404) {
      return res.json({ data: [], error: null })
    }
    res.status(502).json({ data: null, error: `Block analytics error: ${err}` })
  }
})

analyticsRouter.get('/blocks/:blockKey/analysis', async (req, res) => {
  try {
    const pk = req.mapped_pk!
    const { blockKey } = req.params
    const program = await getProgramWithWeightLog(pk, 'current')
    const blocks = await buildCurrentProgramBlockIndex(pk, program)
    const blockEntry = blocks.find((b) => b.blockKey === blockKey)
    const isCurrent = blockEntry?.isCurrent ?? (blockKey === 'current')

    const refresh = req.query.refresh === 'true'

    if (isCurrent) {
      const bundle = await getOrCreateBlockAnalysisBundle(pk, program, blockKey, invokeToolDirect, refresh, false)
      if (!bundle) {
        return res.status(404).json({ data: null, error: `Block ${blockKey} not found` })
      }
      return res.json({ data: bundle, error: null })
    }

    const bundle = await getOrCreateBlockAnalysisBundle(pk, program, blockKey, invokeToolDirect, refresh, false)
    if (!bundle) {
      return res.status(404).json({ data: null, error: `Block ${blockKey} not found` })
    }
    res.json({ data: bundle, error: null })
  } catch (err) {
    logger.error({ err, blockKey: req.params.blockKey }, 'Block analysis error')
    res.status(502).json({ data: null, error: `Block analysis error: ${err}` })
  }
})

analyticsRouter.post('/blocks/:blockKey/regenerate', async (req, res) => {
  try {
    const pk = req.mapped_pk!
    const { blockKey } = req.params
    const program = await getProgramWithWeightLog(pk, 'current')

    let bundle: Awaited<ReturnType<typeof getOrCreateBlockAnalysisBundle>> = null
    let corrReport: Awaited<ReturnType<typeof getOrCreateBlockCorrelationReport>> = null
    let evalReport: Awaited<ReturnType<typeof getOrCreateBlockProgramEvaluation>> = null

    try {
      bundle = await getOrCreateBlockAnalysisBundle(pk, program, blockKey, invokeToolDirect, true, false)
    } catch (err) {
      return res.status(404).json({ data: null, error: `Block ${blockKey} not found or regeneration failed` })
    }

    try {
      corrReport = await getOrCreateBlockCorrelationReport(pk, program, blockKey, invokeToolDirect, true, false)
    } catch (err) {
      logger.warn({ err, pk, blockKey }, 'Block correlation regeneration failed')
    }

    try {
      evalReport = await getOrCreateBlockProgramEvaluation(pk, program, blockKey, invokeToolDirect, true, false)
    } catch (err) {
      logger.warn({ err, pk, blockKey }, 'Block program evaluation regeneration failed')
    }

    if (!bundle) {
      return res.status(404).json({ data: null, error: `Block ${blockKey} not found or regeneration failed` })
    }

    try {
      const markdownResult = await invokeToolDirect('export_program_markdown', {
        version: 'current',
        include_analysis: false,
        pk,
      }) as { markdown?: string; content?: string } | null
      const markdown = markdownResult?.markdown ?? markdownResult?.content ?? ''
      if (markdown) {
        const { putCachedMarkdownExport } = await import('../services/analysisCache')
        await putCachedMarkdownExport(pk, markdown, blockKey)
      }
    } catch (mdErr) {
      logger.warn({ err: mdErr, pk, blockKey }, 'Markdown export failed for block regeneration')
    }

    res.json({
      data: {
        success: true,
        blockKey,
        generatedAt: new Date().toISOString(),
        correlationRegenerated: corrReport !== null,
        evaluationRegenerated: evalReport !== null,
      },
      error: null,
    })
  } catch (err) {
    res.status(502).json({ data: null, error: `Block regeneration error: ${err}` })
  }
})

analyticsRouter.get('/blocks/:blockKey/program-evaluation', async (req, res) => {
  try {
    const program = await getProgramWithWeightLog(req.mapped_pk!, 'current')
    const refresh = req.query.refresh === 'true'
    const cacheOnly = req.query.cacheOnly === 'true'
    const report = await getOrCreateBlockProgramEvaluation(
      req.mapped_pk!,
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

analyticsRouter.put('/blocks/:blockKey/start-maxes', async (req, res) => {
  try {
    const program = await getProgramWithWeightLog(req.mapped_pk!, 'current')
    const blocks = await buildCurrentProgramBlockIndex(req.mapped_pk!, program)
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
      req.mapped_pk!,
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

analyticsRouter.get('/blocks/:blockKey/correlation', async (req, res) => {
  try {
    const program = await getProgramWithWeightLog(req.mapped_pk!, 'current')
    const refresh = req.query.refresh === 'true'
    const cacheOnly = req.query.cacheOnly === 'true'
    const data = await getOrCreateBlockCorrelationReport(
      req.mapped_pk!,
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

analyticsRouter.get('/blocks/:blockKey/export/:format', async (req, res) => {
  try {
    const pk = req.mapped_pk!
    const { blockKey, format } = req.params
    if (format !== 'xlsx' && format !== 'markdown') {
      return res.status(400).json({ data: null, error: 'Unsupported export format. Use xlsx or markdown.' })
    }

    const bundle = await getCachedBlockAnalysisBundle(pk, blockKey)
    if (!bundle) {
      return res.status(404).json({
        data: null,
        error: `No cached block analysis found for ${blockKey}. Open or generate the past block analysis before exporting.`,
      })
    }

    if (bundle.block.isCurrent) {
      return res.status(400).json({
        data: null,
        error: 'Use the existing current-block program export for current analysis.',
      })
    }

    const [programEvaluation, correlation] = await Promise.all([
      getCachedBlockProgramEvaluationReport(pk, blockKey),
      getCachedBlockCorrelationReport(pk, blockKey),
    ])
    const filename = blockAnalysisExportFilename(bundle, format)

    res.setHeader('Content-Type', blockAnalysisExportContentType(format))
    res.setHeader('Content-Disposition', `attachment; filename="${filename}"`)

    if (format === 'markdown') {
      res.send(buildBlockAnalysisMarkdownExport(bundle, programEvaluation, correlation))
      return
    }

    res.end(buildBlockAnalysisWorkbookExport(bundle, programEvaluation, correlation))
  } catch (err) {
    logger.error({ err, blockKey: req.params.blockKey }, 'Block analysis export failed')
    res.status(502).json({ data: null, error: `Block analysis export error: ${err}` })
  }
})

analyticsRouter.post('/block-comparison', async (req, res) => {
  try {
    const program = await getProgramWithWeightLog(req.mapped_pk!, 'current')
    const blocks = await buildCurrentProgramBlockIndex(req.mapped_pk!, program)
    const requestedKeys = Array.isArray(req.body?.blockKeys)
      ? req.body.blockKeys.filter((key: unknown): key is string => typeof key === 'string')
      : []

    const defaultKeys = blocks.filter((block) => !block.isCurrent).map((block) => block.blockKey)
    const selected = new Set(requestedKeys.length ? requestedKeys : defaultKeys)
    const current = blocks.find((block) => block.isCurrent)
    if (current) selected.add(current.blockKey)

    const selectedBlocks = blocks.filter((block) => selected.has(block.blockKey))
    const bundles = []
    const correlationReports = new Map<string, Record<string, unknown> | null>()
    const contexts = new Map()
    for (const rawBlock of selectedBlocks) {
      const block = analysisScopedBlockEntry(program, rawBlock)
      contexts.set(block.blockKey, buildBlockComparisonContext(program, rawBlock))
      const bundle = await getOrCreateBlockAnalysisBundle(
          req.mapped_pk!,
          program,
          block.blockKey,
          invokeToolDirect,
          block.isCurrent,
        )
      if (bundle) bundles.push(bundle)
      correlationReports.set(block.blockKey, await getOrCreateBlockCorrelationReport(
        req.mapped_pk!,
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

analyticsRouter.post('/block-comparison/ai', async (req, res) => {
  try {
    const program = await getProgramWithWeightLog(req.mapped_pk!, 'current')
    const blocks = await buildCurrentProgramBlockIndex(req.mapped_pk!, program)
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
      const bundle = await getCachedBlockAnalysisBundle(req.mapped_pk!, block.blockKey)
      if (bundle) bundles.push(bundle)
      if (bundle) {
        correlationReports.set(block.blockKey, await getOrCreateBlockCorrelationReport(
          req.mapped_pk!,
          program,
          block.blockKey,
          invokeToolDirect,
          false,
          true,
        ))
        programEvaluationReports.set(block.blockKey, await getOrCreateBlockProgramEvaluation(
          req.mapped_pk!,
          program,
          block.blockKey,
          invokeToolDirect,
          false,
          true,
        ))
      }
    }

    const comparison = await getOrCreateAiBlockComparison(
      req.mapped_pk!,
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

analyticsRouter.get('/correlation', async (req, res) => {
  try {
    const weeks = parseInt(req.query.weeks as string) || 4
    const block = (req.query.block as string) || 'current'
    const refresh = req.query.refresh === 'true'
    const cacheOnly = req.query.cacheOnly === 'true'
    const data = await invokeToolDirect('correlation_analysis', { weeks, block, refresh, cache_only: cacheOnly, pk: req.mapped_pk })
    res.json({ data, error: null })
  } catch (err) {
    res.status(502).json({ data: null, error: `Tool invocation error: ${err}` })
  }
})

analyticsRouter.post('/fatigue-profile/estimate', async (req, res) => {
  try {
    const exercise = req.body?.exercise ?? req.body
    const data = await invokeToolDirect('fatigue_profile_estimate', { exercise, pk: req.mapped_pk })
    res.json({ data, error: null })
  } catch (err) {
    res.status(502).json({ data: null, error: `Tool invocation error: ${err}` })
  }
})

analyticsRouter.post('/muscle-groups/estimate', async (req, res) => {
  try {
    const body = req.body ?? {}
    const exercise = body.exercise ?? body
    const lift_profiles = Array.isArray(body.lift_profiles) ? body.lift_profiles : undefined
    const data = await invokeToolDirect('muscle_group_estimate', {
      exercise,
      ...(lift_profiles ? { lift_profiles } : {}),
      pk: req.mapped_pk,
    })
    res.json({ data, error: null })
  } catch (err) {
    res.status(502).json({ data: null, error: `Tool invocation error: ${err}` })
  }
})

analyticsRouter.post('/glossary/text/generate', async (req, res) => {
  try {
    const body = req.body ?? {}
    const exercise = body.exercise ?? body
    if (!exercise?.name) {
      return res.status(400).json({ data: null, error: 'Exercise name is required' })
    }
    const lift_profiles = Array.isArray(body.lift_profiles) ? body.lift_profiles : undefined
    const data = await invokeToolDirect('glossary_generate_text', {
      exercise,
      ...(lift_profiles ? { lift_profiles } : {}),
      pk: req.mapped_pk,
    })
    res.json({ data, error: null })
  } catch (err) {
    res.status(502).json({ data: null, error: `Tool invocation error: ${err}` })
  }
})

analyticsRouter.post('/lift-profile/review', async (req, res) => {
  try {
    const profile = req.body?.profile ?? req.body
    const data = await invokeToolDirect('lift_profile_review', { profile, pk: req.mapped_pk })
    res.json({ data, error: null })
  } catch (err) {
    res.status(502).json({ data: null, error: `Tool invocation error: ${err}` })
  }
})

analyticsRouter.post('/lift-profile/rewrite', async (req, res) => {
  try {
    const profile = req.body?.profile ?? req.body
    const data = await invokeToolDirect('lift_profile_rewrite', { profile, pk: req.mapped_pk })
    res.json({ data, error: null })
  } catch (err) {
    res.status(502).json({ data: null, error: `Tool invocation error: ${err}` })
  }
})

analyticsRouter.post('/lift-profile/estimate-stimulus', async (req, res) => {
  try {
    const profile = req.body?.profile ?? req.body
    const data = await invokeToolDirect('lift_profile_estimate_stimulus', { profile, pk: req.mapped_pk })
    res.json({ data, error: null })
  } catch (err) {
    res.status(502).json({ data: null, error: `Tool invocation error: ${err}` })
  }
})

analyticsRouter.post('/lift-profile/rewrite-and-estimate', async (req, res) => {
  try {
    const profile = req.body?.profile ?? req.body
    const data = await invokeToolDirect('lift_profile_rewrite_and_estimate', { profile, pk: req.mapped_pk })
    res.json({ data, error: null })
  } catch (err) {
    res.status(502).json({ data: null, error: `Tool invocation error: ${err}` })
  }
})

analyticsRouter.get('/program-evaluation', async (req, res) => {
  try {
    const refresh = req.query.refresh === 'true'
    const cacheOnly = req.query.cacheOnly === 'true'
    const data = await invokeToolDirect('program_evaluation', { refresh, cache_only: cacheOnly, pk: req.mapped_pk })
    res.json({ data, error: null })
  } catch (err) {
    res.status(502).json({ data: null, error: `Tool invocation error: ${err}` })
  }
})
