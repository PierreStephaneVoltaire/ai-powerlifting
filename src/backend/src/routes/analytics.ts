import { Router, type Request } from 'express'
import { invokeToolDirect } from '../utils/agent'
import { callOperation, readGeneration } from '../utils/operations'
import { readAnalysisRecord, writeAnalysisRecord } from '../services/analysisRecords'
import { logger } from '../utils/logger'
import { operationScope } from '../utils/operationScope'
import * as programController from '../controllers/programController'
import * as competitionController from '../controllers/competitionController'
import * as federationsController from '../controllers/federationsController'
import * as weightController from '../controllers/weightController'
import type { Program, WeightEntry } from '@powerlifting/types'
import { ALL_BLOCKS, scopeProgramToBlock } from '../utils/blockScope'
import {
  ALL_WINDOW_KEYS,
  CACHE_SCHEMA_VERSION,
  ALL_SECTION_KEYS,
  DETERMINISTIC_SECTION_KEYS,
  buildAnalysisWindows,
  analysisSourceKey,
  analysisVersion,
  isIsoDate,
  makeWeeklyAnalysisBundle,
  normalizeAnalysisSectionKeys,
  normalizeAnalysisWindowKey,
  type AnalysisWindowKey,
  type AnalysisSectionKey,
} from '../services/analysisCache'
import {
  analysisScopedBlockEntry,
  buildBlockComparison,
  buildBlockComparisonContext,
  buildCurrentProgramBlockIndex,
  getOrCreateAiBlockComparison,
  getOrCreateBlockAnalysisBundle,
  getOrCreateBlockCorrelationReport,
  getOrCreateBlockProgramEvaluation,
  loadGoals,
  type BlockAnalysisBundle,
  type ProgramBlockIndexEntry,
} from '../services/blockAnalytics'
import {
  blockAnalysisExportContentType,
  blockAnalysisExportFilename,
  buildBlockAnalysisMarkdownExport,
  buildBlockAnalysisWorkbookExport,
} from '../services/blockAnalysisExport'
import { singleFlight } from '../services/programRequestCache'

export const analyticsRouter = Router()

type ProgramWithWeightLog = Program & { weight_log: WeightEntry[] }

const POD_ANALYSIS_SUBFUNCTIONS = new Set([
  'weekly_analysis',
  'analysis_section',
  'analyze_powerlifting_stats',
  'analyze_progression',
  'analyze_rpe_drift',
  'block_correlation_analysis',
  'block_program_evaluation',
  'correlation_analysis',
  'multi_block_comparison_analysis',
  'powerlifting_filter_categories',
  'powerlifting_ranking_percentile',
  'program_evaluation',
])

async function invokeAnalysisTool(
  toolName: string,
  args: Record<string, unknown>,
): Promise<unknown> {
  if (POD_ANALYSIS_SUBFUNCTIONS.has(toolName)) {
    const { pk, ...rest } = args
    return callOperation(toolName, { ...rest, pk }, Boolean(operationScope.getStore()?.ifJobId) || !['correlation_analysis', 'program_evaluation', 'block_correlation_analysis', 'block_program_evaluation', 'multi_block_comparison_analysis'].includes(toolName))
  }
  // Non-pod_analysis tools (e.g. health_rag_search) go through invokeToolDirect.
  return invokeToolDirect(toolName, args)
}

function todayIso(): string {
  return new Date().toISOString().slice(0, 10)
}

function viewsOwnAthlete(req: Request): boolean {
  const own = req.settings?.mapped_pk || req.settings?.pk
  return Boolean(own) && own === req.mapped_pk
}

async function getProgramWithWeightLog(
  pk: string,
  version = 'current',
  block: string = ALL_BLOCKS,
  window?: { start?: string; end?: string },
): Promise<ProgramWithWeightLog> {
  const key = [pk, block, window?.start || '', window?.end || ''].join('|')
  return singleFlight(key, async () => {
    const program = await programController.getProgram(pk, version, {
      block,
      windowStart: window?.start,
      windowEnd: window?.end,
    })
    let weightLog: WeightEntry[] = []
    try {
      const log = await weightController.getWeightLog(pk, version, block === ALL_BLOCKS ? ALL_BLOCKS : undefined)
      weightLog = Array.isArray(log.entries) ? log.entries : []
    } catch (error) {
      logger.warn({ error, pk }, 'Failed to load weight log for analytics context')
    }
    return scopeProgramToBlock({ ...program, weight_log: weightLog }, block)
  })
}

function requestedWindow(value: Record<string, unknown> = {}): { start?: string; end?: string } {
  const start = isIsoDate(value.window_start as string) ? value.window_start as string : undefined
  const end = isIsoDate(value.window_end as string) ? value.window_end as string : undefined
  return { start, end }
}

const SNAPSHOT_SECTION_KEYS = new Set<AnalysisSectionKey>(['overview', 'alerts'])

async function snapshotCompetitionProjection(pk: string, date: string): Promise<void> {
  try {
    await callOperation('health_snapshot_competition_projection', { date,
      version: 'current',
      allow_retrospective: false,
      pk,
    })
  } catch (snapshotErr) {
    logger.warn({ err: snapshotErr, pk, date }, 'Failed to snapshot competition projections before weekly analysis')
  }
}

type AnalysisKey = {
  pk: string
  asOfDate: string
  windowKey: AnalysisWindowKey
  window: { start?: string; end?: string }
  sourceFingerprint: string
}

type AnalysisWindows = ReturnType<typeof buildAnalysisWindows>

type AnalysisContext = AnalysisKey & {
  program: ProgramWithWeightLog
  windows: AnalysisWindows
}

const DETERMINISTIC_SECTION_SET = new Set<AnalysisSectionKey>(DETERMINISTIC_SECTION_KEYS)

async function resolveAnalysisKey(
  pk: string,
  asOfDate: string,
  windowKey: AnalysisWindowKey,
  window: { start?: string; end?: string },
): Promise<AnalysisKey> {
  return { pk, asOfDate, windowKey, window, sourceFingerprint: analysisSourceKey(await analysisVersion(pk), window) }
}

async function buildAnalysisContext(key: AnalysisKey): Promise<AnalysisContext> {
  const program = await getProgramWithWeightLog(key.pk, 'current', 'current', key.window)
  return { ...key, program, windows: buildAnalysisWindows(program, key.asOfDate) }
}

async function analysisWindows(key: AnalysisKey): Promise<AnalysisWindows> {
  const recordKey = `native_windows#${key.asOfDate}#${key.sourceFingerprint}`
  const saved = await readAnalysisRecord<AnalysisWindows>(key.pk, recordKey)
  if (saved) return saved
  const { windows } = await buildAnalysisContext(key)
  await writeAnalysisRecord(key.pk, recordKey, windows)
  return windows
}

type AnalysisSectionStatusShape = {
  sectionKey: AnalysisSectionKey
  status: 'complete' | 'error' | 'missing' | 'running'
  generation_id?: string
  generatedAt?: string
  updatedAt?: string
  error?: string
  sourceFingerprint?: string
  cached: boolean
  payload?: unknown
}

async function computeSection(
  context: AnalysisContext,
  sectionKey: AnalysisSectionKey,
): Promise<AnalysisSectionStatusShape> {
  const nowIso = new Date().toISOString()
  try {
    let payload: unknown
    if (DETERMINISTIC_SECTION_SET.has(sectionKey)) {
      const window = context.windows[context.windowKey]
      payload = await callOperation('analysis_section', { section: sectionKey,
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
    } else if (sectionKey === 'ai_correlation') {
      const window = context.windows[context.windowKey]
      if (window.weeks < 4) {
        payload = {
          insufficient_data: true,
          insufficient_data_reason: 'Correlation analysis requires at least 4 weeks of data.',
          cache_miss: false,
        }
      } else {
        payload = await callOperation('block_correlation_analysis', {
          weeks: window.weeks,
          program: { ...context.program, sessions: (context.program.sessions ?? []).filter(session => session.date >= window.start && session.date <= window.end) },
          sessions: (context.program.sessions ?? []).filter(session => session.date >= window.start && session.date <= window.end),
          window_start: window.start, window_end: window.end,
          refresh: true, cache_only: false, pk: context.pk,
        }, Boolean(operationScope.getStore()?.ifJobId))
      }
    } else if (sectionKey === 'program_evaluation') {
      if (context.windowKey !== 'block') {
        payload = {
          insufficient_data: true,
          insufficient_data_reason: 'Program evaluation is only available for the full block.',
          cache_miss: false,
        }
      } else {
        payload = await callOperation('block_program_evaluation', { program: { ...context.program, sessions: (context.program.sessions ?? []).filter(session => session.date <= context.asOfDate) }, refresh: true, cache_only: false, pk: context.pk }, Boolean(operationScope.getStore()?.ifJobId))
      }
    } else {
      payload = {}
    }
    const generation = payload as { generation_id?: string; status?: string } | undefined
    return {
      sectionKey,
      status: generation?.generation_id ? 'running' : 'complete',
      ...(generation?.generation_id ? { generation_id: generation.generation_id } : {}),
      generatedAt: nowIso,
      updatedAt: nowIso,
      sourceFingerprint: context.sourceFingerprint,
      cached: false,
      payload,
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error)
    return { sectionKey, status: 'error', error: message, cached: false }
  }
}

function sectionRecordKey(context: Pick<AnalysisKey, 'pk' | 'asOfDate' | 'windowKey' | 'sourceFingerprint'>, sectionKey: AnalysisSectionKey): string {
  return `native_section#${context.asOfDate}#${context.windowKey}#${sectionKey}#${context.sourceFingerprint}`
}

export async function analysisSectionStatusDirect(context: Pick<AnalysisKey, 'pk' | 'asOfDate' | 'windowKey' | 'sourceFingerprint'>, sectionKey: AnalysisSectionKey): Promise<AnalysisSectionStatusShape> {
  const record = await readAnalysisRecord<AnalysisSectionStatusShape>(context.pk, sectionRecordKey(context, sectionKey))
  if (!record) return { sectionKey, status: 'missing', cached: false, sourceFingerprint: context.sourceFingerprint }
  if (record.generation_id) {
    const generation = await readGeneration(record.generation_id, context.pk)
    if (generation.status === 'succeeded') return { ...record, status: 'complete', cached: true, payload: generation.result }
    if (['failed', 'cancelled', 'uncertain'].includes(generation.status)) return { ...record, status: 'error', cached: false, error: generation.error?.message || String(generation.error || 'Generation interrupted; explicitly retry.') }
    return record
  }
  if (record.status === 'running' && Date.now() - Date.parse(record.updatedAt || '') > 900000) {
    return { ...record, status: 'error', error: 'Generation interrupted; explicitly retry.' }
  }
  return { ...record, cached: record.status === 'complete' }
}

async function blockViewKey(pk: string, blockKey: string): Promise<string> {
  return `native_block_view#${CACHE_SCHEMA_VERSION}#${blockKey}#${await analysisVersion(pk)}`
}

type SectionQueueMode = 'missing' | 'regenerate'

async function queueSections(context: AnalysisKey, sectionKeys: AnalysisSectionKey[], mode: SectionQueueMode): Promise<AnalysisSectionKey[]> {
  const accepted: AnalysisSectionKey[] = []
  for (const sectionKey of sectionKeys) {
    const status = await analysisSectionStatusDirect(context, sectionKey)
    if (status.status === 'running' || (status.status === 'complete' && mode === 'missing')) continue
    const record = { sectionKey, status: 'running', cached: false, sourceFingerprint: context.sourceFingerprint, updatedAt: new Date().toISOString() }
    if (await writeAnalysisRecord(context.pk, sectionRecordKey(context, sectionKey), record, status.status === 'missing')) accepted.push(sectionKey)
  }
  return accepted
}

async function runAnalysisSections(key: AnalysisKey, sectionKeys: AnalysisSectionKey[]): Promise<void> {
  if (sectionKeys.length === 0) return
  if (sectionKeys.some((sectionKey) => SNAPSHOT_SECTION_KEYS.has(sectionKey))) {
    await snapshotCompetitionProjection(key.pk, key.asOfDate)
  }
  const context = await buildAnalysisContext(key)
  for (const sectionKey of sectionKeys) {
    const status = await computeSection(context, sectionKey)
    await writeAnalysisRecord(context.pk, sectionRecordKey(context, sectionKey), status)
  }
}

async function runTargetedRegeneration(
  pk: string,
  asOfDate: string,
  targetWindows?: AnalysisWindowKey[],
): Promise<{ generatedAt: string; windows: ReturnType<typeof buildAnalysisWindows>; results: Record<AnalysisWindowKey, unknown> }> {
  const program = await getProgramWithWeightLog(pk, 'current', 'current')
  const windows = buildAnalysisWindows(program, asOfDate)
  const sessions = program.sessions ?? []
  const keys = targetWindows ?? ALL_WINDOW_KEYS

  const results = {} as Record<AnalysisWindowKey, unknown>
  for (const key of keys) {
    const window = windows[key]
    logger.info({ pk, window: key, weeks: window.weeks }, 'Computing weekly analysis window from sections')
    const merged: Record<string, unknown> = {}
    for (const sectionKey of DETERMINISTIC_SECTION_KEYS) {
      const sectionPayload = await callOperation('analysis_section', { section: sectionKey,
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

  try {
    const bundle = await getOrCreateBlockAnalysisBundle(pk, program, 'current', invokeAnalysisTool, true, false)
    if (bundle) await writeAnalysisRecord(pk, await blockViewKey(pk, 'current'), bundle)
  } catch (err) {
    logger.warn({ err, pk }, 'block_analysis#v1#current regeneration failed')
  }

  const generatedAt = new Date().toISOString()
  logger.info({ pk, generatedAt, windows: keys }, 'Targeted regeneration complete')
  return { generatedAt, windows, results }
}

async function runFullCurrentBlockRegeneration(
  pk: string,
  asOfDate: string,
): Promise<{ generatedAt: string; windows: ReturnType<typeof buildAnalysisWindows>; results: Record<AnalysisWindowKey, unknown> }> {
  await snapshotCompetitionProjection(pk, asOfDate)
  const { generatedAt, windows, results } = await runTargetedRegeneration(pk, asOfDate)

  try {
    await callOperation('export_program_markdown', { version: 'current',
      include_analysis: true,
      analysis_weeks: windows.block.weeks,
      pk,
    })
  } catch (err) {
    logger.warn({ err, pk }, 'Markdown export failed during regeneration')
  }

  logger.info({ pk, generatedAt }, 'Full current block regeneration complete')
  return { generatedAt, windows, results }
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
    const context = await resolveAnalysisKey(pk, asOfDate, windowKey, requestedWindow(req.query as Record<string, unknown>))
    const statuses = await Promise.allSettled(ALL_SECTION_KEYS.map(async (sectionKey) => {
      const status = await analysisSectionStatusDirect(context, sectionKey)
      const { payload: _payload, ...withoutPayload } = status
      return withoutPayload
    }))
    res.json({
      data: {
        schemaVersion: 6,
        asOfDate,
        windowKey,
        windows: await analysisWindows(context),
        sourceFingerprint: context.sourceFingerprint,
        sections: Object.fromEntries(statuses.map((result, index) => [
          ALL_SECTION_KEYS[index],
          result.status === 'fulfilled' ? result.value : { sectionKey: ALL_SECTION_KEYS[index], status: 'error' },
        ])),
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
      ? sectionKeys.filter((sectionKey: AnalysisSectionKey) => !DETERMINISTIC_SECTION_SET.has(sectionKey))
      : []
    if (unsafeReadOnlySections.length) {
      return res.status(403).json({
        data: null,
        error: 'Read-only users can only queue deterministic analysis sections.',
      })
    }
    const context = await resolveAnalysisKey(pk, asOfDate, windowKey, requestedWindow(req.body as Record<string, unknown>))
    const queued = await queueSections(context, sectionKeys, 'missing')
    await runAnalysisSections(context, queued)
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
    const context = await resolveAnalysisKey(pk, asOfDate, windowKey, requestedWindow(req.query as Record<string, unknown>))
    const status = await analysisSectionStatusDirect(context, sectionKey)
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
    const context = await resolveAnalysisKey(pk, asOfDate, windowKey, requestedWindow(req.body as Record<string, unknown>))
    const queued = await queueSections(context, sectionKeys, 'regenerate')
    await runAnalysisSections(context, queued)
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

    logger.info({ pk, asOfDate, forceRefresh }, 'Computing weekly bundle')
    const { generatedAt, windows, results } = await runFullCurrentBlockRegeneration(pk, asOfDate)
    const bundle = makeWeeklyAnalysisBundle(asOfDate, windows, results)
    return res.json({ data: { ...bundle, cached: false, generatedAt }, error: null })
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
    const context = await resolveAnalysisKey(pk, asOfDate, windowKey, requestedWindow(req.body as Record<string, unknown>))
    const queued = await queueSections(context, sectionKeys, 'regenerate')
    await runAnalysisSections(context, queued)
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
    const cacheOnly = req.readOnly === true || req.query.cacheOnly === 'true' || req.query.cache_only === 'true'

    const markdownResult = await callOperation('get_analysis_markdown', {
      pk,
      refresh: req.readOnly ? false : req.query.refresh === 'true',
      cache_only: cacheOnly,
    }) as { markdown?: string; generated_at?: string; cached?: boolean } | null

    const markdown = markdownResult?.markdown ?? ''
    if (!markdown) {
      return res.status(404).json({ data: null, error: 'Markdown export cache miss' })
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
    const snapshot = viewsOwnAthlete(req) ? await getProgramWithWeightLog(req.mapped_pk!, 'current', block) : null
    const data: Record<string, unknown> = {}
    for (const sectionKey of DETERMINISTIC_SECTION_KEYS) {
      const sectionPayload = await callOperation('analysis_section', { section: sectionKey,
        weeks,
        block,
        window_start: windowStart,
        window_end: windowEnd,
        ref_date: refDate,
        week_start: weekStart,
        week_end: weekEnd,
        refresh_program: false,
        ...(snapshot ? { program: snapshot, sessions: snapshot.sessions ?? [] } : {}),
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
    const pk = req.mapped_pk!
    const recordKey = `native_block_index#${CACHE_SCHEMA_VERSION}#${await analysisVersion(pk)}`
    const saved = await readAnalysisRecord<ProgramBlockIndexEntry[]>(pk, recordKey)
    if (saved) return res.json({ data: saved, error: null })
    const program = await getProgramWithWeightLog(pk, 'current')
    const blocks = await buildCurrentProgramBlockIndex(pk, program)
    await writeAnalysisRecord(pk, recordKey, blocks)
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
    const refresh = req.query.refresh === 'true'
    const cacheOnly = req.readOnly === true || req.query.cacheOnly === 'true' || req.query.cache_only === 'true'
    const recordKey = await blockViewKey(pk, blockKey)
    const saved = refresh && !cacheOnly ? null : await readAnalysisRecord<BlockAnalysisBundle>(pk, recordKey)
    if (saved) return res.json({ data: { ...saved, cached: true }, error: null })

    const program = await getProgramWithWeightLog(pk, 'current')
    const bundle = await getOrCreateBlockAnalysisBundle(pk, program, blockKey, invokeAnalysisTool, refresh, cacheOnly)
    if (!bundle) {
      return res.status(404).json({ data: null, error: `Block ${blockKey} not found` })
    }
    await writeAnalysisRecord(pk, recordKey, bundle)
    res.json({ data: bundle, error: null })
  } catch (err) {
    logger.error({ err, blockKey: req.params.blockKey }, 'Block analysis error')
    const statusCode = typeof (err as { statusCode?: unknown })?.statusCode === 'number' ? (err as { statusCode: number }).statusCode : 502
    res.status(statusCode).json({ data: null, error: `Block analysis error: ${err}` })
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
      bundle = await getOrCreateBlockAnalysisBundle(pk, program, blockKey, invokeAnalysisTool, true, false)
    } catch (err) {
      return res.status(404).json({ data: null, error: `Block ${blockKey} not found or regeneration failed` })
    }

    try {
      corrReport = await getOrCreateBlockCorrelationReport(pk, program, blockKey, invokeAnalysisTool, true, false)
    } catch (err) {
      logger.warn({ err, pk, blockKey }, 'Block correlation regeneration failed')
    }

    try {
      evalReport = await getOrCreateBlockProgramEvaluation(pk, program, blockKey, invokeAnalysisTool, true, false)
    } catch (err) {
      logger.warn({ err, pk, blockKey }, 'Block program evaluation regeneration failed')
    }

    if (!bundle) {
      return res.status(404).json({ data: null, error: `Block ${blockKey} not found or regeneration failed` })
    }
    await writeAnalysisRecord(pk, await blockViewKey(pk, blockKey), bundle)

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

analyticsRouter.get('/generations/:generationId', async (req, res) => {
  try {
    res.json({ data: await readGeneration(req.params.generationId, req.mapped_pk!), error: null })
  } catch (err) {
    res.status(502).json({ data: null, error: String(err) })
  }
})

analyticsRouter.get('/blocks/:blockKey/program-evaluation', async (req, res) => {
  try {
    const program = await getProgramWithWeightLog(req.mapped_pk!, 'current')
    const refresh = req.query.refresh === 'true'
    const cacheOnly = req.readOnly || req.query.cacheOnly === 'true'
    const report = await getOrCreateBlockProgramEvaluation(
      req.mapped_pk!,
      program,
      req.params.blockKey,
      invokeAnalysisTool,
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

    const blockId = block.blockKey === 'current' ? program.meta.current_block_id ?? 'current' : block.blockKey
    const records = program.meta.blocks ?? []
    if (!records.some((record) => String(record.id ?? record.block_id ?? '') === blockId)) {
      return res.status(404).json({ data: null, error: `Block ${req.params.blockKey} has no block record` })
    }
    const startMaxesKg = Object.fromEntries(Object.entries({ squat, bench, deadlift }).filter((entry): entry is [string, number] => entry[1] != null))
    await programController.updateMetaField(
      req.mapped_pk!,
      'current',
      'blocks',
      records.map((record) => String(record.id ?? record.block_id ?? '') === blockId ? { ...record, start_maxes_kg: startMaxesKg } : record),
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
    const cacheOnly = req.readOnly || req.query.cacheOnly === 'true'
    const data = await getOrCreateBlockCorrelationReport(
      req.mapped_pk!,
      program,
      req.params.blockKey,
      invokeAnalysisTool,
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

    const program = await getProgramWithWeightLog(pk, 'current')
    const bundle = await getOrCreateBlockAnalysisBundle(pk, program, blockKey, invokeAnalysisTool, false, false)
    if (!bundle) {
      return res.status(404).json({
        data: null,
        error: `No block analysis found for ${blockKey}. Open or generate the past block analysis before exporting.`,
      })
    }

    if (bundle.block.isCurrent) {
      return res.status(400).json({
        data: null,
        error: 'Use the existing current-block program export for current analysis.',
      })
    }

    const [programEvaluation, correlation] = await Promise.all([
      getOrCreateBlockProgramEvaluation(pk, program, blockKey, invokeAnalysisTool, false, true),
      getOrCreateBlockCorrelationReport(pk, program, blockKey, invokeAnalysisTool, false, true),
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
          invokeAnalysisTool,
          block.isCurrent,
          false,
          allGoals,
        )
      if (bundle) bundles.push(bundle)
      correlationReports.set(block.blockKey, await getOrCreateBlockCorrelationReport(
        req.mapped_pk!,
        program,
        block.blockKey,
        invokeAnalysisTool,
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
      const bundle = await getOrCreateBlockAnalysisBundle(req.mapped_pk!, program, block.blockKey, invokeAnalysisTool, false, cacheOnly)
      if (bundle) bundles.push(bundle)
      if (bundle) {
        correlationReports.set(block.blockKey, await getOrCreateBlockCorrelationReport(
          req.mapped_pk!,
          program,
          block.blockKey,
          invokeAnalysisTool,
          false,
          true,
          allGoals,
        ))
        programEvaluationReports.set(block.blockKey, await getOrCreateBlockProgramEvaluation(
          req.mapped_pk!,
          program,
          block.blockKey,
          invokeAnalysisTool,
          false,
          true,
          allGoals,
        ))
      }
    }

    if (cacheOnly && bundles.length !== selectedBlocks.length) {
      return res.json({ data: { schemaVersion: 6, generatedAt: '', cached: false, selectedBlockKeys: selectedBlocks.map((block) => block.blockKey), sourceFingerprint: '', report: { cache_miss: true, insufficient_data: true, insufficient_data_reason: 'Generate the selected block analyses before requesting a comparison.' }, deterministic: buildBlockComparison(bundles, correlationReports, contexts) }, error: null })
    }
    const comparison = await getOrCreateAiBlockComparison(
      req.mapped_pk!,
      bundles,
      invokeAnalysisTool,
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
    const cacheOnly = req.readOnly || req.query.cacheOnly === 'true'
    const data = await invokeAnalysisTool('correlation_analysis', { weeks, block, refresh, cache_only: cacheOnly, pk: req.mapped_pk })
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

analyticsRouter.post('/lift-profile/estimate-stimulus', async (req, res) => {
  try {
    const profile = req.body?.profile ?? req.body
    const data = await invokeToolDirect('lift_profile_estimate_stimulus', { profile, pk: req.mapped_pk })
    res.json({ data, error: null })
  } catch (err) {
    res.status(502).json({ data: null, error: `Tool invocation error: ${err}` })
  }
})

analyticsRouter.post('/lift-profile/suggest', async (req, res) => {
  try {
    const { lift, description, profile } = req.body ?? {}
    const data = await invokeToolDirect('lift_profile_suggest', { lift, description, ...(profile ? { profile } : {}), pk: req.mapped_pk })
    res.json({ data, error: null })
  } catch (err) {
    res.status(502).json({ data: null, error: `Tool invocation error: ${err}` })
  }
})

analyticsRouter.get('/program-evaluation', async (req, res) => {
  try {
    const refresh = req.query.refresh === 'true'
    const cacheOnly = req.readOnly || req.query.cacheOnly === 'true'
    const data = await invokeAnalysisTool('program_evaluation', { refresh, cache_only: cacheOnly, pk: req.mapped_pk })
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
      const comps = await competitionController.getUserCompetitions(pk)
      competitions = comps
        .filter((c) => c.user_status === 'confirmed' || c.user_status === 'optional')
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
