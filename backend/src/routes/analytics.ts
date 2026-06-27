import { Router } from 'express'
import { invokeToolDirect } from '../utils/agent'
import { invokeLambda } from '../utils/lambda'
import { logger } from '../utils/logger'
import * as programController from '../controllers/programController'
import * as competitionController from '../controllers/competitionController'
import * as federationsController from '../controllers/federationsController'
import * as weightController from '../controllers/weightController'
import type { AthleteGoal, Program, WeightEntry } from '@powerlifting/types'
import {
  ALL_WINDOW_KEYS,
  ALL_SECTION_KEYS,
  AI_SECTION_KEYS,
  DETERMINISTIC_SECTION_KEYS,
  buildAnalysisWindows,
  buildAnalysisSourceFingerprint,
  analysisSectionStatus,
  claimAnalysisSectionJob,
  completeAnalysisSectionJob,
  failAnalysisSectionJob,
  getCachedAnalysisSection,
  invalidateAnalysisSections,
  putAllCachedWindowAnalyses,
  isIsoDate,
  makeWeeklyAnalysisBundle,
  normalizeAnalysisSectionKeys,
  normalizeAnalysisWindowKey,
  putCachedAnalysisSection,
  queueAnalysisSectionJobs,
  type AnalysisWindowKey,
  type AnalysisSectionKey,
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
  loadGoals,
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
    await invokeLambda('health_snapshot_competition_projection', {
      date,
      version: 'current',
      allow_retrospective: false,
      pk,
    })
  } catch (snapshotErr) {
    logger.warn({ err: snapshotErr, pk, date }, 'Failed to snapshot competition projections before weekly analysis')
  }
}

type AnalysisContext = {
  pk: string
  asOfDate: string
  windowKey: AnalysisWindowKey
  program: ProgramWithWeightLog
  windows: ReturnType<typeof buildAnalysisWindows>
  sourceFingerprint: string
}

const DETERMINISTIC_SECTION_SET = new Set<AnalysisSectionKey>(DETERMINISTIC_SECTION_KEYS)

async function buildAnalysisContext(
  pk: string,
  asOfDate: string,
  windowKey: AnalysisWindowKey,
): Promise<AnalysisContext> {
  const program = await getProgramWithWeightLog(pk, 'current')
  const windows = buildAnalysisWindows(program, asOfDate)
  const sourceFingerprint = await buildAnalysisSourceFingerprint(program, windows[windowKey], pk)
  return { pk, asOfDate, windowKey, program, windows, sourceFingerprint }
}

async function queueMissingSections(
  context: AnalysisContext,
  sectionKeys: AnalysisSectionKey[],
  force = false,
): Promise<AnalysisSectionKey[]> {
  const missing: AnalysisSectionKey[] = []
  for (const sectionKey of sectionKeys) {
    const cached = force
      ? null
      : await getCachedAnalysisSection(
        context.pk,
        context.asOfDate,
        context.windowKey,
        sectionKey,
        context.sourceFingerprint,
      )
    if (!cached) missing.push(sectionKey)
  }
  if (missing.length) {
    await queueAnalysisSectionJobs(
      context.pk,
      context.asOfDate,
      context.windowKey,
      missing,
      context.sourceFingerprint,
    )
  }
  return missing
}

async function computeDeterministicSection(
  context: AnalysisContext,
  sectionKey: AnalysisSectionKey,
): Promise<void> {
  if (!DETERMINISTIC_SECTION_SET.has(sectionKey)) return
  const didClaim = await claimAnalysisSectionJob(
    context.pk,
    context.asOfDate,
    context.windowKey,
    sectionKey,
    context.sourceFingerprint,
  )
  if (!didClaim) return

  try {
    if (sectionKey === 'overview' || sectionKey === 'alerts') {
      await snapshotCompetitionProjection(context.pk, context.asOfDate)
    }
    const window = context.windows[context.windowKey]
    const payload = await invokeLambda('analysis_section', {
      section: sectionKey,
      weeks: window.weeks,
      block: 'current',
      window_start: window.start,
      window_end: window.end,
      ref_date: context.asOfDate,
      week_start: window.weekStart,
      week_end: window.weekEnd,
      refresh_program: false,
      program: context.program,
      sessions: context.program.sessions ?? [],
      pk: context.pk,
    }) as Record<string, unknown>
    await putCachedAnalysisSection(
      context.pk,
      context.asOfDate,
      context.windowKey,
      sectionKey,
      context.sourceFingerprint,
      payload,
    )
    await completeAnalysisSectionJob(
      context.pk,
      context.asOfDate,
      context.windowKey,
      sectionKey,
      context.sourceFingerprint,
    )
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error)
    await failAnalysisSectionJob(
      context.pk,
      context.asOfDate,
      context.windowKey,
      sectionKey,
      context.sourceFingerprint,
      message,
    ).catch((err) => logger.warn({ err, sectionKey }, 'Failed to mark analysis section job failed'))
  }
}

async function computeAiSection(
  context: AnalysisContext,
  sectionKey: AnalysisSectionKey,
): Promise<void> {
  const didClaim = await claimAnalysisSectionJob(
    context.pk,
    context.asOfDate,
    context.windowKey,
    sectionKey,
    context.sourceFingerprint,
  )
  if (!didClaim) return

  try {
    const window = context.windows[context.windowKey]
    let payload: unknown
    if (sectionKey === 'ai_correlation') {
      if (window.weeks < 4) {
        payload = {
          insufficient_data: true,
          insufficient_data_reason: 'Correlation analysis requires at least 4 weeks of data.',
          cache_miss: false,
        }
      } else {
        payload = await invokeToolDirect('correlation_analysis', {
          weeks: window.weeks,
          block: 'current',
          refresh: true,
          cache_only: false,
          pk: context.pk,
        })
      }
    } else if (sectionKey === 'program_evaluation') {
      if (context.windowKey !== 'block') {
        payload = {
          insufficient_data: true,
          insufficient_data_reason: 'Program evaluation is only available for the full block.',
          cache_miss: false,
        }
      } else {
        payload = await invokeToolDirect('program_evaluation', {
          refresh: true,
          cache_only: false,
          pk: context.pk,
        })
      }
    } else {
      payload = {}
    }
    await putCachedAnalysisSection(
      context.pk,
      context.asOfDate,
      context.windowKey,
      sectionKey,
      context.sourceFingerprint,
      payload,
    )
    await completeAnalysisSectionJob(
      context.pk,
      context.asOfDate,
      context.windowKey,
      sectionKey,
      context.sourceFingerprint,
    )
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error)
    await failAnalysisSectionJob(
      context.pk,
      context.asOfDate,
      context.windowKey,
      sectionKey,
      context.sourceFingerprint,
      message,
    ).catch((err) => logger.warn({ err, sectionKey }, 'Failed to mark AI analysis section failed'))
  }
}

async function runQueuedAnalysisSections(
  context: AnalysisContext,
  sectionKeys: AnalysisSectionKey[],
): Promise<void> {
  for (const sectionKey of sectionKeys.filter((key) => DETERMINISTIC_SECTION_SET.has(key))) {
    await computeDeterministicSection(context, sectionKey)
  }
  for (const sectionKey of sectionKeys.filter((key) => AI_SECTION_KEYS.includes(key))) {
    await computeAiSection(context, sectionKey)
  }
}

function startAnalysisSectionWorker(context: AnalysisContext, sectionKeys: AnalysisSectionKey[]): void {
  void runQueuedAnalysisSections(context, sectionKeys).catch((error) => {
    logger.warn({ err: error, pk: context.pk, asOfDate: context.asOfDate, windowKey: context.windowKey, sectionKeys }, 'Analysis section worker failed')
  })
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

  const results = {} as Record<AnalysisWindowKey, unknown>
  for (const key of keys) {
    const window = windows[key]
    logger.info({ pk, window: key, weeks: window.weeks }, 'Computing weekly analysis window from sections')
    const merged: Record<string, unknown> = {}
    for (const sectionKey of DETERMINISTIC_SECTION_KEYS) {
      const sectionPayload = await invokeLambda('analysis_section', {
        section: sectionKey,
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
      }) as Record<string, unknown>
      Object.assign(merged, sectionPayload)
    }
    results[key] = merged
  }

  await putAllCachedWindowAnalyses(pk, results)

  try {
    await getOrCreateBlockAnalysisBundle(pk, program, 'current', invokeLambda, true, false)
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
  const { generatedAt, windows } = await runTargetedRegeneration(pk, asOfDate)

  try {
    const markdownResult = await invokeLambda('export_program_markdown', {
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

analyticsRouter.get('/analysis/manifest', async (req, res) => {
  try {
    const pk = req.mapped_pk!
    const requestedAsOfDate = req.query.asOfDate as string | undefined
    const asOfDate = isIsoDate(requestedAsOfDate) ? requestedAsOfDate : todayIso()
    const windowKey = normalizeAnalysisWindowKey(req.query.window)
    const context = await buildAnalysisContext(pk, asOfDate, windowKey)
    const statuses = await Promise.all(ALL_SECTION_KEYS.map(async (sectionKey) => {
      const status = await analysisSectionStatus(
        pk,
        asOfDate,
        windowKey,
        sectionKey,
        context.sourceFingerprint,
      )
      const { payload: _payload, ...withoutPayload } = status
      return withoutPayload
    }))
    res.json({
      data: {
        schemaVersion: 6,
        asOfDate,
        windowKey,
        windows: context.windows,
        sourceFingerprint: context.sourceFingerprint,
        sections: Object.fromEntries(statuses.map((status) => [status.sectionKey, status])),
      },
      error: null,
    })
  } catch (err) {
    logger.error({ err }, 'Analysis manifest failed')
    res.status(502).json({ data: null, error: `Analysis manifest error: ${err}` })
  }
})

analyticsRouter.post('/analysis/sections/queue', async (req, res) => {
  try {
    const pk = req.mapped_pk!
    const asOfDate = isIsoDate(req.body?.asOfDate) ? req.body.asOfDate : todayIso()
    const windowKey = normalizeAnalysisWindowKey(req.body?.window)
    const sectionKeys = normalizeAnalysisSectionKeys(req.body?.sections)
    const unsafeReadOnlySections = req.readOnly
      ? sectionKeys.filter((sectionKey) => !DETERMINISTIC_SECTION_SET.has(sectionKey))
      : []
    if (unsafeReadOnlySections.length) {
      return res.status(403).json({
        data: null,
        error: 'Read-only users can only queue deterministic analysis sections.',
      })
    }
    const force = req.readOnly ? false : req.body?.force === true
    const context = await buildAnalysisContext(pk, asOfDate, windowKey)
    if (force) {
      await invalidateAnalysisSections(pk, asOfDate, windowKey, sectionKeys)
    }
    const queued = await queueMissingSections(context, sectionKeys, force)
    startAnalysisSectionWorker(context, queued.length ? queued : sectionKeys)
    res.status(202).json({
      data: {
        accepted: true,
        asOfDate,
        windowKey,
        queued,
        sourceFingerprint: context.sourceFingerprint,
      },
      error: null,
    })
  } catch (err) {
    logger.error({ err }, 'Analysis section queue failed')
    res.status(502).json({ data: null, error: `Analysis queue error: ${err}` })
  }
})

analyticsRouter.get('/analysis/sections/:sectionKey', async (req, res) => {
  try {
    const pk = req.mapped_pk!
    const sectionKey = normalizeAnalysisSectionKeys([req.params.sectionKey], [])[0]
    if (!sectionKey) {
      return res.status(400).json({ data: null, error: `Unknown analysis section: ${req.params.sectionKey}` })
    }
    const requestedAsOfDate = req.query.asOfDate as string | undefined
    const asOfDate = isIsoDate(requestedAsOfDate) ? requestedAsOfDate : todayIso()
    const windowKey = normalizeAnalysisWindowKey(req.query.window)
    const context = await buildAnalysisContext(pk, asOfDate, windowKey)
    const status = await analysisSectionStatus(
      pk,
      asOfDate,
      windowKey,
      sectionKey,
      context.sourceFingerprint,
    )
    res.json({
      data: {
        ...status,
        asOfDate,
        windowKey,
        sourceFingerprint: status.sourceFingerprint ?? context.sourceFingerprint,
      },
      error: null,
    })
  } catch (err) {
    logger.error({ err, sectionKey: req.params.sectionKey }, 'Analysis section read failed')
    res.status(502).json({ data: null, error: `Analysis section error: ${err}` })
  }
})

analyticsRouter.post('/analysis/sections/invalidate', async (req, res) => {
  try {
    const pk = req.mapped_pk!
    const asOfDate = isIsoDate(req.body?.asOfDate) ? req.body.asOfDate : todayIso()
    const windowKey = normalizeAnalysisWindowKey(req.body?.window)
    const sectionKeys = normalizeAnalysisSectionKeys(req.body?.sections)
    const context = await buildAnalysisContext(pk, asOfDate, windowKey)
    await invalidateAnalysisSections(pk, asOfDate, windowKey, sectionKeys)
    const queued = await queueMissingSections(context, sectionKeys, true)
    startAnalysisSectionWorker(context, queued)
    res.status(202).json({
      data: {
        accepted: true,
        invalidated: sectionKeys,
        queued,
        asOfDate,
        windowKey,
        sourceFingerprint: context.sourceFingerprint,
      },
      error: null,
    })
  } catch (err) {
    logger.error({ err }, 'Analysis section invalidation failed')
    res.status(502).json({ data: null, error: `Analysis invalidation error: ${err}` })
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
    const asOfDate = isIsoDate(req.body?.asOfDate) ? req.body.asOfDate : todayIso()
    const requestedWindows = Array.isArray(req.body?.windows) ? req.body.windows : []
    const windowKey = normalizeAnalysisWindowKey(req.body?.window ?? requestedWindows[0])
    const sectionKeys = normalizeAnalysisSectionKeys(req.body?.sections)
    const context = await buildAnalysisContext(pk, asOfDate, windowKey)
    await invalidateAnalysisSections(pk, asOfDate, windowKey, sectionKeys)
    const queued = await queueMissingSections(context, sectionKeys, true)
    startAnalysisSectionWorker(context, queued)
    res.status(202).json({
      data: {
        success: true,
        accepted: true,
        asOfDate,
        windowKey,
        queued,
        generatedAt: new Date().toISOString(),
        windowsRegenerated: windowKey ? 1 : 0,
      },
      error: null,
    })
  } catch (err) {
    res.status(502).json({ data: null, error: `Regeneration error: ${err}` })
  }
})

analyticsRouter.get('/analysis/markdown', async (req, res) => {
  try {
    const pk = req.mapped_pk!

    const markdownResult = await invokeLambda('get_analysis_markdown', {
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
    const data: Record<string, unknown> = {}
    for (const sectionKey of DETERMINISTIC_SECTION_KEYS) {
      const sectionPayload = await invokeLambda('analysis_section', {
        section: sectionKey,
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
      }) as Record<string, unknown>
      Object.assign(data, sectionPayload)
    }
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
      const bundle = await getOrCreateBlockAnalysisBundle(pk, program, blockKey, invokeLambda, refresh, false)
      if (!bundle) {
        return res.status(404).json({ data: null, error: `Block ${blockKey} not found` })
      }
      return res.json({ data: bundle, error: null })
    }

    const bundle = await getOrCreateBlockAnalysisBundle(pk, program, blockKey, invokeLambda, refresh, false)
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
      bundle = await getOrCreateBlockAnalysisBundle(pk, program, blockKey, invokeLambda, true, false)
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
      const markdownResult = await invokeLambda('export_program_markdown', {
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
    const allGoals = await loadGoals(req.mapped_pk!)
    const blocks = await buildCurrentProgramBlockIndex(req.mapped_pk!, program, allGoals)
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
      contexts.set(block.blockKey, buildBlockComparisonContext(program, rawBlock, allGoals))
      const bundle = await getOrCreateBlockAnalysisBundle(
          req.mapped_pk!,
          program,
          block.blockKey,
          invokeLambda,
          block.isCurrent,
          false,
          allGoals,
        )
      if (bundle) bundles.push(bundle)
      correlationReports.set(block.blockKey, await getOrCreateBlockCorrelationReport(
        req.mapped_pk!,
        program,
        block.blockKey,
        invokeToolDirect,
        false,
        true,
        allGoals,
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
    const allGoals = await loadGoals(req.mapped_pk!)
    const blocks = await buildCurrentProgramBlockIndex(req.mapped_pk!, program, allGoals)
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
    const programEvaluationReports = new Map<string, Record<string, unknown> | null>()
    const contexts = new Map()
    const cacheOnly = req.readOnly ? true : req.body?.cacheOnly === true
    const refresh = req.readOnly ? false : req.body?.refresh === true
    for (const rawBlock of selectedBlocks) {
      const block = analysisScopedBlockEntry(program, rawBlock)
      contexts.set(block.blockKey, buildBlockComparisonContext(program, rawBlock, allGoals))
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
          allGoals,
        ))
        programEvaluationReports.set(block.blockKey, await getOrCreateBlockProgramEvaluation(
          req.mapped_pk!,
          program,
          block.blockKey,
          invokeToolDirect,
          false,
          true,
          allGoals,
        ))
      }
    }

    const comparison = await getOrCreateAiBlockComparison(
      req.mapped_pk!,
      bundles,
      invokeToolDirect,
      refresh,
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

analyticsRouter.post('/budget/timeline', async (req, res) => {
  try {
    const body = req.body ?? {}
    const pk = req.mapped_pk!

    let competitions: unknown[] = []
    let federation_memberships: unknown[] = []
    try {
      const userComps = await competitionController.listUserCompetitions(pk)
      competitions = userComps
        .filter((c) => c.user_status !== 'completed' && c.user_status !== 'skipped')
        .map((c) => ({
          master_id: c.master_id,
          name: c.name,
          start_date: c.start_date,
          user_status: c.user_status,
        }))
    } catch (compErr) {
      logger.warn({ err: compErr, pk }, 'Failed to load competitions for budget timeline')
    }
    try {
      const library = await federationsController.getFederationLibrary(pk)
      const masterFeds = await federationsController.listFederations()
      const byAbbr = new Map(masterFeds.filter((f) => f.abbreviation).map((f) => [f.abbreviation!, f]))
      federation_memberships = library.federations
        .filter((f) => f.membership_paid || f.membership_cost != null)
        .map((f) => {
          const master = f.abbreviation ? byAbbr.get(f.abbreviation) : undefined
          return {
            abbreviation: f.abbreviation,
            parent_federation_abbr: master?.parent_federation_abbr ?? null,
            membership_group: master?.membership_group ?? [],
            membership_paid: f.membership_paid ?? false,
            membership_cost: f.membership_cost ?? null,
            membership_paid_date: f.membership_paid_date ?? null,
            membership_expiry_date: f.membership_expiry_date ?? null,
          }
        })
    } catch (fedErr) {
      logger.warn({ err: fedErr, pk }, 'Failed to load federation memberships for budget timeline')
    }

    const data = await invokeToolDirect('budget_priority_timeline', {
      ...body,
      competitions,
      federation_memberships,
      pk,
    })
    res.json({ data, error: null })
  } catch (err) {
    res.status(502).json({ data: null, error: `Tool invocation error: ${err}` })
  }
})
