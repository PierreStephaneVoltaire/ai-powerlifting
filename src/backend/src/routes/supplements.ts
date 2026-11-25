import { Router } from 'express'
import * as supplementController from '../controllers/supplementController'
import { cacheGet, invalidateAfter } from '../utils/cacheMiddleware'
import type { SupplementPhase } from '@powerlifting/types'

export const supplementsRouter = Router({ mergeParams: true })

// GET /api/supplements/current - Get supplement phases
supplementsRouter.get('/current', cacheGet((req) => [`supplements:current`]), async (req, res, next) => {
  try {
    const phases = await supplementController.getSupplementPhases(req.mapped_pk!)
    res.json({ data: phases, error: null })
  } catch (err) {
    next(err)
  }
})

// PUT /api/supplements/current - Update all supplement phases
supplementsRouter.put('/current', invalidateAfter((req) => [`supplements:current`]), async (req, res, next) => {
  try {
    const { phases } = req.body

    if (!Array.isArray(phases)) {
      return res.status(400).json({
        data: null,
        error: 'phases must be an array',
      })
    }

    const result = await supplementController.updateSupplementPhases(
      req.mapped_pk!,
      phases as SupplementPhase[]
    )
    res.json({ data: result, error: null })
  } catch (err) {
    next(err)
  }
})
