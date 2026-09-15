import { Router, type Request, type Response } from 'express'
import { invokeAnalyticsOperation } from '../services/analyticsGateway'
import { isIsoDate, normalizeAnalysisSectionKeys, normalizeAnalysisWindowKey, type AnalysisSectionKey } from '../services/analysisCache'

export const analyticsServiceRouter = Router()

function todayIso(): string {
  return new Date().toISOString().slice(0, 10)
}

function statusFor(error: unknown): number {
  if (typeof (error as { statusCode?: unknown })?.statusCode === 'number') return (error as { statusCode: number }).statusCode
  const match = String(error).match(/service error (\d+)/i)
  return match ? Number(match[1]) : 502
}

function failed(res: Response, error: unknown, message: string): void {
  res.status(statusFor(error)).json({ data: null, error: `${message}: ${error}` })
}

analyticsServiceRouter.get('/analysis/manifest', async (req: Request, res: Response) => {
  try {
    const asOfDate = isIsoDate(req.query.asOfDate as string) ? req.query.asOfDate as string : todayIso()
    const data = await invokeAnalyticsOperation('analytics.manifest', req.mapped_pk!, { asOfDate, window: normalizeAnalysisWindowKey(req.query.window) })
    res.json({ data, error: null })
  } catch (error) { failed(res, error, 'Analysis manifest error') }
})

analyticsServiceRouter.post('/analysis/sections/queue', async (req: Request, res: Response) => {
  try {
    const sections = normalizeAnalysisSectionKeys(req.body?.sections)
    if (req.readOnly && sections.some((section: AnalysisSectionKey) => section.startsWith('ai_') || section === 'program_evaluation')) {
      res.status(403).json({ data: null, error: 'Read-only users can only queue deterministic analysis sections.' })
      return
    }
    const data = await invokeAnalyticsOperation('analytics.sections_queue', req.mapped_pk!, {
      asOfDate: isIsoDate(req.body?.asOfDate) ? req.body.asOfDate : todayIso(),
      window: normalizeAnalysisWindowKey(req.body?.window),
      sections,
      read_only: req.readOnly === true,
    })
    res.status(202).json({ data, error: null })
  } catch (error) { failed(res, error, 'Analysis queue error') }
})

analyticsServiceRouter.get('/analysis/sections/:sectionKey', async (req: Request, res: Response) => {
  try {
    const sectionKey = normalizeAnalysisSectionKeys([req.params.sectionKey], [])[0]
    if (!sectionKey) { res.status(400).json({ data: null, error: `Unknown analysis section: ${req.params.sectionKey}` }); return }
    const data = await invokeAnalyticsOperation('analytics.sections_get', req.mapped_pk!, {
      sectionKey,
      asOfDate: isIsoDate(req.query.asOfDate as string) ? req.query.asOfDate as string : todayIso(),
      window: normalizeAnalysisWindowKey(req.query.window),
    })
    res.json({ data, error: null })
  } catch (error) { failed(res, error, 'Analysis section error') }
})

analyticsServiceRouter.post('/analysis/sections/invalidate', async (req: Request, res: Response) => {
  try {
    const data = await invokeAnalyticsOperation('analytics.sections_invalidate', req.mapped_pk!, {
      asOfDate: isIsoDate(req.body?.asOfDate) ? req.body.asOfDate : todayIso(),
      window: normalizeAnalysisWindowKey(req.body?.window),
      sections: normalizeAnalysisSectionKeys(req.body?.sections),
    })
    res.status(202).json({ data, error: null })
  } catch (error) { failed(res, error, 'Analysis invalidation error') }
})

analyticsServiceRouter.get('/analysis/weekly-bundle', async (req: Request, res: Response) => {
  try {
    const data = await invokeAnalyticsOperation('analytics.bundle', req.mapped_pk!, {
      asOfDate: isIsoDate(req.query.asOfDate as string) ? req.query.asOfDate as string : todayIso(),
      refresh: req.query.refresh === 'true',
    })
    res.json({ data, error: null })
  } catch (error) { failed(res, error, 'Analysis error') }
})

analyticsServiceRouter.post('/analysis/regenerate', async (req: Request, res: Response) => {
  try {
    const window = normalizeAnalysisWindowKey(req.body?.window ?? (Array.isArray(req.body?.windows) ? req.body.windows[0] : undefined))
    const data = await invokeAnalyticsOperation('analytics.regenerate', req.mapped_pk!, {
      asOfDate: isIsoDate(req.body?.asOfDate) ? req.body.asOfDate : todayIso(),
      window,
      sections: normalizeAnalysisSectionKeys(req.body?.sections),
      windows: Array.isArray(req.body?.windows) ? req.body.windows : [],
    })
    res.status(202).json({ data, error: null })
  } catch (error) { failed(res, error, 'Regeneration error') }
})

analyticsServiceRouter.get('/analysis/markdown', async (req: Request, res: Response) => {
  try {
    const cacheOnly = req.readOnly === true || req.query.cacheOnly === 'true' || req.query.cache_only === 'true'
    const result = await invokeAnalyticsOperation<{ markdown?: string; generated_at?: string; cached?: boolean }>('analytics.markdown', req.mapped_pk!, {
      refresh: req.readOnly ? false : req.query.refresh === 'true',
      cache_only: cacheOnly,
      max_age_hours: Number(req.query.maxAgeHours) || undefined,
    })
    if (!result.markdown) { res.status(404).json({ data: null, error: 'Markdown export cache miss' }); return }
    res.json({ data: { markdown: result.markdown, generatedAt: result.generated_at ?? new Date().toISOString(), cached: result.cached ?? false }, error: null })
  } catch (error) { failed(res, error, 'Markdown export error') }
})

analyticsServiceRouter.get('/analysis/weekly', async (req: Request, res: Response) => {
  try {
    const data = await invokeAnalyticsOperation('analytics.weekly', req.mapped_pk!, {
      weeks: Number(req.query.weeks) || 1,
      block: String(req.query.block || 'current'),
      windowStart: req.query.windowStart,
      windowEnd: req.query.windowEnd,
      refDate: isIsoDate(req.query.refDate as string) ? req.query.refDate as string : todayIso(),
      weekStart: Number(req.query.weekStart) || undefined,
      weekEnd: Number(req.query.weekEnd) || undefined,
    })
    res.json({ data, error: null })
  } catch (error) { failed(res, error, 'Tool invocation error') }
})

analyticsServiceRouter.get('/blocks', async (req: Request, res: Response) => {
  try { res.json({ data: await invokeAnalyticsOperation('analytics.blocks_list', req.mapped_pk!), error: null }) }
  catch (error) { failed(res, error, 'Block analytics error') }
})

analyticsServiceRouter.get('/blocks/:blockKey/analysis', async (req: Request, res: Response) => {
  try { res.json({ data: await invokeAnalyticsOperation('analytics.blocks_get', req.mapped_pk!, { blockKey: req.params.blockKey, refresh: req.query.refresh === 'true', cacheOnly: req.readOnly || req.query.cacheOnly === 'true' }), error: null }) }
  catch (error) { failed(res, error, 'Block analysis error') }
})

analyticsServiceRouter.post('/blocks/:blockKey/regenerate', async (req: Request, res: Response) => {
  try { res.json({ data: await invokeAnalyticsOperation('analytics.blocks_regenerate', req.mapped_pk!, { blockKey: req.params.blockKey }), error: null }) }
  catch (error) { failed(res, error, 'Block regeneration error') }
})

analyticsServiceRouter.get('/blocks/:blockKey/program-evaluation', async (req: Request, res: Response) => {
  try { res.json({ data: await invokeAnalyticsOperation('analytics.block_evaluation', req.mapped_pk!, { blockKey: req.params.blockKey, refresh: req.query.refresh === 'true', cacheOnly: req.query.cacheOnly === 'true' }), error: null }) }
  catch (error) { failed(res, error, 'Block program evaluation error') }
})

analyticsServiceRouter.get('/blocks/:blockKey/correlation', async (req: Request, res: Response) => {
  try { res.json({ data: await invokeAnalyticsOperation('analytics.correlation', req.mapped_pk!, { blockKey: req.params.blockKey, refresh: req.query.refresh === 'true', cacheOnly: req.query.cacheOnly === 'true' }), error: null }) }
  catch (error) { failed(res, error, 'Block correlation error') }
})

analyticsServiceRouter.get('/blocks/:blockKey/export/:format', async (req: Request, res: Response) => {
  try {
    if (req.params.format !== 'xlsx' && req.params.format !== 'markdown') { res.status(400).json({ data: null, error: 'Unsupported export format. Use xlsx or markdown.' }); return }
    const result = await invokeAnalyticsOperation<{ content_base64: string; content_type: string; content_disposition: string }>('analytics.export', req.mapped_pk!, { blockKey: req.params.blockKey, format: req.params.format })
    res.setHeader('Content-Type', result.content_type)
    if (result.content_disposition) res.setHeader('Content-Disposition', result.content_disposition)
    res.send(Buffer.from(result.content_base64, 'base64'))
  } catch (error) { failed(res, error, 'Block analysis export error') }
})

analyticsServiceRouter.post('/block-comparison', async (req: Request, res: Response) => {
  try { res.json({ data: await invokeAnalyticsOperation('analytics.compare', req.mapped_pk!, { blockKeys: Array.isArray(req.body?.blockKeys) ? req.body.blockKeys : [] }), error: null }) }
  catch (error) { failed(res, error, 'Block comparison error') }
})

analyticsServiceRouter.post('/block-comparison/ai', async (req: Request, res: Response) => {
  try { res.json({ data: await invokeAnalyticsOperation('analytics.compare_ai', req.mapped_pk!, { blockKeys: Array.isArray(req.body?.blockKeys) ? req.body.blockKeys : [], refresh: req.readOnly ? false : req.body?.refresh === true, cacheOnly: req.readOnly ? true : req.body?.cacheOnly === true, read_only: req.readOnly === true }), error: null }) }
  catch (error) { failed(res, error, 'AI block comparison error') }
})
