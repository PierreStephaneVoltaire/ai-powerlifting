import { Router } from 'express'
import * as competitionController from '../controllers/competitionController'
import type { LiftResults, PostMeetReport, UserCompetitionUpdate } from '@powerlifting/types'
import { invokeToolDirect } from '../utils/agent'

export const competitionsRouter = Router({ mergeParams: true })

// ─── New unversioned routes ────────────────────────────────────────────────

// GET /api/competitions - List user competitions (new UserCompetition shape)
competitionsRouter.get('/', async (req, res, next) => {
  try {
    const country = req.query.country as string | undefined
    const state = req.query.state as string | undefined
    const competitions = await competitionController.listUserCompetitions(req.mapped_pk!, { country, state })
    res.json({ data: competitions, error: null })
  } catch (err) {
    next(err)
  }
})

// PATCH /api/competitions/:masterId - Patch a single competition (user-owned fields only)
competitionsRouter.patch('/:masterId', async (req, res, next) => {
  try {
    const updates = req.body as UserCompetitionUpdate
    if (!updates || typeof updates !== 'object') {
      return res.status(400).json({ data: null, error: 'Request body must be an object' })
    }
    await competitionController.patchUserCompetition(req.mapped_pk!, req.params.masterId, updates)
    res.json({ data: { success: true }, error: null })
  } catch (err) {
    next(err)
  }
})

// POST /api/competitions/:masterId/complete - Mark competition as completed
competitionsRouter.post('/:masterId/complete', async (req, res, next) => {
  try {
    const { results, bodyWeightKg, postMeetReport } = req.body

    if (!results || typeof bodyWeightKg !== 'number') {
      return res.status(400).json({ data: null, error: 'Missing results or bodyWeightKg' })
    }

    await competitionController.completeUserCompetition(
      req.mapped_pk!,
      req.params.masterId,
      results as LiftResults,
      bodyWeightKg,
      postMeetReport as PostMeetReport | undefined,
    )
    res.json({ data: { success: true }, error: null })
  } catch (err) {
    next(err)
  }
})

// ─── Legacy versioned routes (kept for backward compat) ────────────────────

// GET /api/competitions/:version - Get competitions (legacy Competition[] shape)
competitionsRouter.get('/:version', async (req, res, next) => {
  try {
    // Only match if :version looks like a version string (v020, current, etc.)
    const version = req.params.version
    if (version.startsWith('v') || version === 'current') {
      const competitions = await competitionController.getCompetitions(req.mapped_pk!, version)
      res.json({ data: competitions, error: null })
    } else {
      // It's a masterId — fall through to the unversioned GET
      const competitions = await competitionController.listUserCompetitions(req.mapped_pk!)
      const match = competitions.find(c => c.master_id === version)
      if (!match) return res.status(404).json({ data: null, error: 'Not found' })
      res.json({ data: match, error: null })
    }
  } catch (err) {
    next(err)
  }
})

// PUT /api/competitions/:version - Update all competitions (legacy)
competitionsRouter.put('/:version', async (req, res, next) => {
  try {
    const { competitions } = req.body

    if (!Array.isArray(competitions)) {
      return res.status(400).json({ data: null, error: 'competitions must be an array' })
    }

    await competitionController.updateCompetitions(
      req.mapped_pk!,
      req.params.version,
      competitions,
    )
    res.json({ data: { success: true }, error: null })
  } catch (err) {
    next(err)
  }
})

// POST /api/competitions/:version/migrate - Migrate last_comp into competitions (legacy)
competitionsRouter.post('/:version/migrate', async (req, res, next) => {
  try {
    const competitions = await competitionController.migrateLastComp(req.mapped_pk!, req.params.version)
    res.json({ data: competitions, error: null })
  } catch (err) {
    next(err)
  }
})

// PATCH /api/competitions/:version/:date/complete - Mark competition as completed (legacy)
competitionsRouter.patch('/:version/:date/complete', async (req, res, next) => {
  try {
    const { results, bodyWeightKg, postMeetReport } = req.body

    if (!results || typeof bodyWeightKg !== 'number') {
      return res.status(400).json({ data: null, error: 'Missing results or bodyWeightKg' })
    }

    const compDate = new Date(`${req.params.date}T00:00:00Z`)
    compDate.setUTCDate(compDate.getUTCDate() - 7)
    const snapshotDate = compDate.toISOString().slice(0, 10)

    try {
      await invokeToolDirect('health_snapshot_competition_projection', {
        date: snapshotDate,
        version: req.params.version,
        allow_retrospective: true,
        pk: req.mapped_pk,
      })
    } catch (snapshotErr) {
      console.warn('Failed to snapshot competition projection before completion:', snapshotErr)
    }

    const updatedCompetition = await invokeToolDirect('health_complete_competition', {
      date: req.params.date,
      results: results as LiftResults,
      body_weight_kg: bodyWeightKg,
      post_meet_report: postMeetReport as PostMeetReport | undefined,
      version: req.params.version,
      allow_retrospective: true,
      pk: req.mapped_pk,
    })

    res.json({ data: updatedCompetition, error: null })
  } catch (err) {
    next(err)
  }
})

