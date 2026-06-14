import { Router } from 'express'
import * as supplementController from '../controllers/supplementController'
import type { SupplementPhase } from '@powerlifting/types'

export const supplementsRouter = Router({ mergeParams: true })

// GET /api/supplements/:version - Get supplement phases
supplementsRouter.get('/:version', async (req, res, next) => {
  try {
    const phases = await supplementController.getSupplementPhases(req.mapped_pk!, req.params.version)
    res.json({ data: phases, error: null })
  } catch (err) {
    next(err)
  }
})

// PUT /api/supplements/:version - Update all supplement phases
supplementsRouter.put('/:version', async (req, res, next) => {
  try {
    const { phases } = req.body

    if (!Array.isArray(phases)) {
      return res.status(400).json({
        data: null,
        error: 'phases must be an array',
      })
    }

    await supplementController.updateSupplementPhases(
      req.mapped_pk!,
      req.params.version,
      phases as SupplementPhase[]
    )
    res.json({ data: { success: true }, error: null })
  } catch (err) {
    next(err)
  }
})
