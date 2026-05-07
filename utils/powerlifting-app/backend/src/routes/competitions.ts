import { Router } from 'express'
import * as competitionController from '../controllers/competitionController'
import type { Competition, LiftResults, PostMeetReport } from '@powerlifting/types'
import { invokeToolDirect } from '../utils/agent'

export const competitionsRouter = Router({ mergeParams: true })

// GET /api/competitions/:version - Get competitions
competitionsRouter.get('/:version', async (req, res, next) => {
  try {
    const competitions = await competitionController.getCompetitions(req.effectivePk!, req.params.version)
    res.json({ data: competitions, error: null })
  } catch (err) {
    next(err)
  }
})

// PUT /api/competitions/:version - Update all competitions
competitionsRouter.put('/:version', async (req, res, next) => {
  try {
    const { competitions } = req.body

    if (!Array.isArray(competitions)) {
      return res.status(400).json({
        data: null,
        error: 'competitions must be an array',
      })
    }

    await competitionController.updateCompetitions(
      req.effectivePk!,
      req.params.version,
      competitions as Competition[]
    )
    res.json({ data: { success: true }, error: null })
  } catch (err) {
    next(err)
  }
})

// POST /api/competitions/:version/migrate - Migrate last_comp into competitions
competitionsRouter.post('/:version/migrate', async (req, res, next) => {
  try {
    const competitions = await competitionController.migrateLastComp(req.effectivePk!, req.params.version)
    res.json({ data: competitions, error: null })
  } catch (err) {
    next(err)
  }
})

// PATCH /api/competitions/:version/:date/complete - Mark competition as completed
competitionsRouter.patch('/:version/:date/complete', async (req, res, next) => {
  try {
    const { results, bodyWeightKg, postMeetReport } = req.body

    if (!results || typeof bodyWeightKg !== 'number') {
      return res.status(400).json({
        data: null,
        error: 'Missing results or bodyWeightKg in request body',
      })
    }

    const compDate = new Date(`${req.params.date}T00:00:00Z`)
    compDate.setUTCDate(compDate.getUTCDate() - 7)
    const snapshotDate = compDate.toISOString().slice(0, 10)

    try {
      await invokeToolDirect('health_snapshot_competition_projection', {
        date: snapshotDate,
        version: req.params.version,
        allow_retrospective: true,
        pk: req.effectivePk,
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
      pk: req.effectivePk,
    })

    res.json({ data: updatedCompetition, error: null })
  } catch (err) {
    next(err)
  }
})
