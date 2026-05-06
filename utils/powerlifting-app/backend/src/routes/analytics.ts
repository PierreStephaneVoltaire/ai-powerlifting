import { Router } from 'express'
import { invokeToolDirect } from '../utils/agent'
import * as programController from '../controllers/programController'
import {
  analysisSourceFingerprint,
  buildAnalysisWindows,
  getCachedWeeklyAnalysisBundle,
  isIsoDate,
  makeWeeklyAnalysisBundle,
  putCachedWeeklyAnalysisBundle,
  type AnalysisWindowKey,
} from '../services/analysisCache'

export const analyticsRouter = Router()

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
    let program = await programController.getProgram(pk, 'current')
    let sourceFingerprint = analysisSourceFingerprint(program)

    const cached = await getCachedWeeklyAnalysisBundle(pk, asOfDate, sourceFingerprint)
    if (cached) {
      return res.json({ data: cached, error: null })
    }

    await snapshotCompetitionProjection(pk, asOfDate)
    program = await programController.getProgram(pk, 'current')
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
    const program = await programController.getProgram(req.effectivePk!, 'current')
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

// GET /api/analytics/correlation?weeks=N&block=X&refresh=bool
analyticsRouter.get('/correlation', async (req, res) => {
  try {
    const weeks = parseInt(req.query.weeks as string) || 4
    const block = (req.query.block as string) || 'current'
    const refresh = req.query.refresh === 'true'
    const data = await invokeToolDirect('correlation_analysis', { weeks, block, refresh, pk: req.effectivePk })
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
    const data = await invokeToolDirect('program_evaluation', { refresh, pk: req.effectivePk })
    res.json({ data, error: null })
  } catch (err) {
    res.status(502).json({ data: null, error: `Tool invocation error: ${err}` })
  }
})
