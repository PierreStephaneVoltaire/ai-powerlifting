import express, { type Request, type Response } from 'express'
import { analyticsRouter } from './routes/analytics'
import { operationScope } from './utils/operationScope'
import { blocksGetPath } from './analyticsOperationPaths'
import { relayResponse } from './analyticsRelay'

const app = express()
const port = Number(process.env.ANALYTICS_NODE_PORT || 8091)
const token = process.env.ANALYTICS_NODE_TOKEN || process.env.INTERNAL_API_TOKEN || ''

app.use(express.json({ limit: '10mb' }))
app.use((req: Request, res: Response, next) => {
  if (!token || req.get('X-Internal-Token') !== token) {
    res.status(401).json({ data: null, error: 'Invalid internal token' })
    return
  }
  req.mapped_pk = req.get('X-Athlete-Pk') || undefined
  req.actor_mapped_pk = req.get('X-Person-Pk') || req.mapped_pk
  req.readOnly = req.get('X-Read-Only') === 'true'
  operationScope.run({ athlete: req.mapped_pk || '', person: req.actor_mapped_pk || '', ifJobId: req.get('X-IF-Turn-Id') || req.get('X-IF-Job-Id') || undefined }, next)
})

const operationPaths: Record<string, (args: Record<string, unknown>) => { method: string; path: string; body?: unknown }> = {
  'analytics.manifest': args => ({ method: 'GET', path: `/analysis/manifest?asOfDate=${encodeURIComponent(String(args.asOfDate || ''))}&window=${encodeURIComponent(String(args.window || 'current'))}` }),
  'analytics.sections_queue': args => ({ method: 'POST', path: '/analysis/sections/queue', body: args }),
  'analytics.sections_get': args => ({ method: 'GET', path: `/analysis/sections/${encodeURIComponent(String(args.sectionKey || ''))}?asOfDate=${encodeURIComponent(String(args.asOfDate || ''))}&window=${encodeURIComponent(String(args.window || 'current'))}` }),
  'analytics.sections_invalidate': args => ({ method: 'POST', path: '/analysis/sections/invalidate', body: args }),
  'analytics.weekly': args => ({ method: 'GET', path: `/analysis/weekly?weeks=${encodeURIComponent(String(args.weeks || 1))}&block=${encodeURIComponent(String(args.block || 'current'))}&windowStart=${encodeURIComponent(String(args.windowStart || ''))}&windowEnd=${encodeURIComponent(String(args.windowEnd || ''))}&refDate=${encodeURIComponent(String(args.refDate || ''))}&weekStart=${encodeURIComponent(String(args.weekStart || ''))}&weekEnd=${encodeURIComponent(String(args.weekEnd || ''))}` }),
  'analytics.bundle': args => ({ method: 'GET', path: `/analysis/weekly-bundle?asOfDate=${encodeURIComponent(String(args.asOfDate || ''))}&refresh=${args.refresh === true}` }),
  'analytics.regenerate': args => ({ method: 'POST', path: '/analysis/regenerate', body: args }),
  'analytics.markdown': args => ({ method: 'GET', path: `/analysis/markdown?refresh=${args.refresh === true}&cacheOnly=${args.cache_only === true}` }),
  'analytics.blocks_list': () => ({ method: 'GET', path: '/blocks' }),
  'analytics.blocks_get': args => ({ method: 'GET', path: blocksGetPath(args) }),
  'analytics.blocks_regenerate': args => ({ method: 'POST', path: `/blocks/${encodeURIComponent(String(args.blockKey || ''))}/regenerate`, body: args }),
  'analytics.block_evaluation': args => ({ method: 'GET', path: `/blocks/${encodeURIComponent(String(args.blockKey || ''))}/program-evaluation?refresh=${args.refresh === true}&cacheOnly=${args.cacheOnly === true}` }),
  'analytics.correlation': args => ({ method: 'GET', path: `/blocks/${encodeURIComponent(String(args.blockKey || ''))}/correlation?refresh=${args.refresh === true}&cacheOnly=${args.cacheOnly === true}` }),
  'analytics.export': args => ({ method: 'GET', path: `/blocks/${encodeURIComponent(String(args.blockKey || ''))}/export/${encodeURIComponent(String(args.format || 'markdown'))}` }),
  'analytics.compare': args => ({ method: 'POST', path: '/block-comparison', body: args }),
  'analytics.compare_ai': args => ({ method: 'POST', path: '/block-comparison/ai', body: args }),
}

app.post('/internal/analytics/operations/:operation', async (req, res) => {
  try {
    const operation = operationPaths[req.params.operation]
    if (!operation) {
      res.status(404).json({ data: null, error: 'Unknown analytics operation' })
      return
    }
    const target = operation(req.body || {})
    const response = await fetch(`http://127.0.0.1:${port}/internal/analytics${target.path}`, {
      method: target.method,
      headers: {
        'X-Internal-Token': token,
        'X-Athlete-Pk': req.get('X-Athlete-Pk') || '',
        'X-Person-Pk': req.get('X-Person-Pk') || '',
        'X-Read-Only': req.get('X-Read-Only') || 'false',
        ...(req.get('X-IF-Turn-Id') || req.get('X-IF-Job-Id') ? { 'X-IF-Job-Id': req.get('X-IF-Turn-Id') || req.get('X-IF-Job-Id') as string } : {}),
        ...(target.body === undefined ? {} : { 'Content-Type': 'application/json' }),
      },
      ...(target.body === undefined ? {} : { body: JSON.stringify(target.body) }),
    })
    await relayResponse(response, res)
  } catch (error) {
    res.status(502).json({ data: null, error: String(error) })
  }
})

app.use('/internal/analytics', analyticsRouter)

app.listen(port, '127.0.0.1', () => {
  process.stdout.write(`Analytics Node sidecar listening on 127.0.0.1:${port}\n`)
})
