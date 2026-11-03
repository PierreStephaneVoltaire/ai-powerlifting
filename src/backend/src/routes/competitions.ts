import { Router } from 'express'
import * as competitionController from '../controllers/competitionController'
import { cacheGet, invalidateAfter } from '../utils/cacheMiddleware'
import type { LiftResults, PostMeetReport, UserCompetitionUpdate } from '@powerlifting/types'
import { AppError } from '../middleware/errorHandler'

function mutationEnvelope(body: unknown): competitionController.CompetitionMutationEnvelope {
  const input = body && typeof body === 'object' ? body as Record<string, unknown> : {}
  if (typeof input.expected_revision !== 'number' || !Number.isInteger(input.expected_revision) || input.expected_revision < 0) throw new AppError('expected_revision must be a nonnegative integer', 400)
  if (typeof input.idempotency_key !== 'string' || !input.idempotency_key.trim()) throw new AppError('idempotency_key must be a nonempty string', 400)
  return { expected_revision: input.expected_revision, idempotency_key: input.idempotency_key }
}

const USER_UPDATE_FIELDS = new Set([
  'units', 'user_status', 'weight_class_kg', 'body_weight_kg', 'targets', 'results', 'post_meet_report',
  'hotel_required', 'counts_toward_federation_ids', 'between_comp_plan', 'comp_day_protocol', 'decision_date',
  'attempt_selection', 'attempt_strategy_mode', 'qualifying_standard_id', 'qualifying_total_kg',
  'projected_at_t_minus_1w', 'projection_snapshot_date', 'notes',
])

function userCompetitionUpdates(body: unknown): UserCompetitionUpdate {
  const input = body && typeof body === 'object' ? body as Record<string, unknown> : {}
  const updates: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(input)) {
    if (key === 'expected_revision' || key === 'idempotency_key') continue
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
      updates,
      mutationEnvelope(req.body),
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
      mutationEnvelope(req.body),
      postMeetReport as PostMeetReport | undefined,
    )
    res.json({ data: updated, error: null })
  } catch (err) {
    next(err)
  }
})

competitionsRouter.get('/:version', cacheGet((req) => [`competitions:${req.params.version}`, 'program:current']), async (req, res, next) => {
  try {
    const competitions = await competitionController.getCompetitions(req.mapped_pk!, req.params.version)
    res.json({ data: competitions, error: null })
  } catch (err) {
    next(err)
  }
})

competitionsRouter.put('/:version', invalidateAfter((req) => [`competitions:${req.params.version}`, 'program:current']), async (req, res, next) => {
  try {
    const { competitions } = req.body

    if (!Array.isArray(competitions)) {
      return res.status(400).json({ data: null, error: 'competitions must be an array' })
    }

    const result = await competitionController.updateCompetitions(req.mapped_pk!, req.params.version, competitions, mutationEnvelope(req.body))
    res.json({ data: { success: true, ...result }, error: null })
  } catch (err) {
    next(err)
  }
})

competitionsRouter.patch('/:version/:date/complete', invalidateAfter((req) => [`competitions:${req.params.version}`, 'program:current']), async (req, res, next) => {
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
      mutationEnvelope(req.body),
      postMeetReport as PostMeetReport | undefined,
    )

    res.json({ data: updatedCompetition, error: null })
  } catch (err) {
    next(err)
  }
})
