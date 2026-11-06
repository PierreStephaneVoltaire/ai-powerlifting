import { Router } from 'express'
import * as competitionController from '../controllers/competitionController'
import { cacheGet, invalidateAfter } from '../utils/cacheMiddleware'
import type { LiftResults, PostMeetReport, UserCompetitionUpdate } from '@powerlifting/types'
import { AppError } from '../middleware/errorHandler'

const USER_UPDATE_FIELDS = new Set([
  'units', 'user_status', 'weight_class_kg', 'body_weight_kg', 'targets', 'results', 'post_meet_report',
  'hotel_required', 'counts_toward_federation_ids', 'between_comp_plan', 'comp_day_protocol', 'decision_date',
  'attempt_selection',
  'projected_at_t_minus_1w', 'projection_snapshot_date', 'notes',
])

function userCompetitionUpdates(body: unknown): UserCompetitionUpdate {
  const input = body && typeof body === 'object' ? body as Record<string, unknown> : {}
  const updates: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(input)) {
    if (!USER_UPDATE_FIELDS.has(key)) throw new AppError(`competition field is not editable: ${key}`, 400)
    updates[key] = value
  }
  return updates as UserCompetitionUpdate
}

export const competitionsRouter = Router({ mergeParams: true })

competitionsRouter.get('/', cacheGet(['competitions', 'program:current']), async (req, res, next) => {
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

competitionsRouter.patch('/:masterId', invalidateAfter(['competitions', 'program:current']), async (req, res, next) => {
  try {
    const updates = userCompetitionUpdates(req.body)
    const updated = await competitionController.patchUserCompetition(
      req.mapped_pk!,
      req.params.masterId,
      updates
    )
    res.json({ data: updated, error: null })
  } catch (err) {
    next(err)
  }
})

competitionsRouter.post('/:masterId/complete', invalidateAfter(['competitions', 'program:current']), async (req, res, next) => {
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
