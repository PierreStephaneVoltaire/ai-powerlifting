import { Router } from 'express'
import * as competitionController from '../controllers/competitionController'
import { cacheGet, invalidateAfter } from '../utils/cacheMiddleware'
import type { LiftResults, PostMeetReport, UserCompetitionUpdate } from '@powerlifting/types'

export const competitionsRouter = Router({ mergeParams: true })

competitionsRouter.get('/', cacheGet(['competitions']), async (req, res, next) => {
  try {
    const competitions = await competitionController.getUserCompetitions(req.mapped_pk!, {
      country: typeof req.query.country === 'string' ? req.query.country : undefined,
      state: typeof req.query.state === 'string' ? req.query.state : undefined,
    })
    res.json({ data: competitions, error: null })
  } catch (err) {
    next(err)
  }
})

competitionsRouter.patch('/:masterId', invalidateAfter(['competitions']), async (req, res, next) => {
  try {
    const updates = (req.body ?? {}) as UserCompetitionUpdate
    const updated = await competitionController.patchUserCompetition(
      req.mapped_pk!,
      req.params.masterId,
      updates,
    )
    res.json({ data: updated, error: null })
  } catch (err) {
    next(err)
  }
})

competitionsRouter.post('/:masterId/complete', invalidateAfter(['competitions']), async (req, res, next) => {
  try {
    const { results, bodyWeightKg, postMeetReport } = req.body ?? {}
    if (!results || typeof bodyWeightKg !== 'number') {
      return res.status(400).json({ data: null, error: 'Missing results or bodyWeightKg' })
    }
    const updated = await competitionController.completeUserCompetition(
      req.mapped_pk!,
      req.params.masterId,
      results as LiftResults,
      bodyWeightKg,
      postMeetReport as PostMeetReport | undefined,
    )
    res.json({ data: updated, error: null })
  } catch (err) {
    next(err)
  }
})

competitionsRouter.get('/:version', cacheGet((req) => [`competitions:${req.params.version}`]), async (req, res, next) => {
  try {
    const competitions = await competitionController.getCompetitions(req.mapped_pk!, req.params.version)
    res.json({ data: competitions, error: null })
  } catch (err) {
    next(err)
  }
})

competitionsRouter.put('/:version', invalidateAfter((req) => [`competitions:${req.params.version}`]), async (req, res, next) => {
  try {
    const { competitions } = req.body

    if (!Array.isArray(competitions)) {
      return res.status(400).json({ data: null, error: 'competitions must be an array' })
    }

    await competitionController.updateCompetitions(req.mapped_pk!, req.params.version, competitions)
    res.json({ data: { success: true }, error: null })
  } catch (err) {
    next(err)
  }
})

competitionsRouter.patch('/:version/:date/complete', invalidateAfter((req) => [`competitions:${req.params.version}`]), async (req, res, next) => {
  try {
    const { results, bodyWeightKg, postMeetReport } = req.body

    if (!results || typeof bodyWeightKg !== 'number') {
      return res.status(400).json({ data: null, error: 'Missing results or bodyWeightKg' })
    }

    const updatedCompetition = await competitionController.completeCompetition(
      req.mapped_pk!,
      req.params.version,
      req.params.date,
      results as LiftResults,
      bodyWeightKg,
      postMeetReport as PostMeetReport | undefined,
    )

    res.json({ data: updatedCompetition, error: null })
  } catch (err) {
    next(err)
  }
})
